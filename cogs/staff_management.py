
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import config
import uuid
import time


DIVISIONS = {
    "main_staff": [
        "trial_moderator", "junior_moderator", "moderator",
        "senior_moderator", "head_moderator",
        "trial_administrator", "junior_administrator",
        "administrator", "head_administrator",
        "assistant_to_owner", "owner"
    ],
    "operations_support": [
        "trial", "junior", "regular", "senior",
        "head_of_operations"
    ],
    "ticket_support": [
        "trial", "junior", "regular", "senior",
        "head_of_ticket_support"
    ],
    "staff_managers": [
        "trial", "junior", "regular", "senior",
        "head_of_staff_management"
    ]
}


class ApprovalView(discord.ui.View):
    def __init__(self, bot, request_id, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.request_id = request_id
        self.guild_id = guild_id

        approve = discord.ui.Button(
            label="Approve",
            style=discord.ButtonStyle.success,
            custom_id=f"teamy:approve:{request_id}"
        )
        deny = discord.ui.Button(
            label="Deny",
            style=discord.ButtonStyle.danger,
            custom_id=f"teamy:deny:{request_id}"
        )

        approve.callback = self.approve
        deny.callback = self.deny

        self.add_item(approve)
        self.add_item(deny)

    async def process(self, interaction, approved):
        guild = self.bot.get_guild(self.guild_id)

        if guild is None:
            return await interaction.response.send_message(
                "I cannot find the server for this request.",
                ephemeral=True
            )

        if interaction.user.id != guild.owner_id:
            return await interaction.response.send_message(
                "Only the actual server owner can decide this request.",
                ephemeral=True
            )

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute(
                "SELECT * FROM staff_requests WHERE request_id = ?",
                (self.request_id,)
            ) as cursor:
                request = await cursor.fetchone()

            if not request or request[9] != "pending":
                return await interaction.response.send_message(
                    "This request has already been handled or no longer exists.",
                    ephemeral=True
                )

            (
                request_id, guild_id, requester_id, target_id,
                division, action, old_role_id, new_role_id,
                reason, status, created_at, reviewed_at,
                reviewed_by, review_reason
            ) = request

            if approved:
                try:
                    member = guild.get_member(target_id)
                    if member is None:
                        member = await guild.fetch_member(target_id)

                    if action in ("promotion", "demotion"):
                        if not new_role_id:
                            raise ValueError("The requested role is missing.")

                        new_role = guild.get_role(new_role_id)
                        if new_role is None:
                            raise ValueError("The new role no longer exists.")

                        if new_role >= guild.me.top_role:
                            raise ValueError(
                                "My bot role must be above the requested role."
                            )

                        if old_role_id:
                            old_role = guild.get_role(old_role_id)
                            if old_role and old_role in member.roles:
                                await member.remove_roles(
                                    old_role,
                                    reason=f"Owner-approved staff change: {request_id}"
                                )

                        await member.add_roles(
                            new_role,
                            reason=f"Owner-approved staff change: {request_id}"
                        )

                    elif action == "strike":
                        await db.execute("""
                            INSERT INTO staff_strikes
                            (guild_id, user_id, issued_by, request_id, reason, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            guild_id, target_id, requester_id,
                            request_id, reason, time.time()
                        ))

                    elif action == "note":
                        await db.execute("""
                            INSERT INTO division_notes
                            (guild_id, user_id, added_by, division, note, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            guild_id, target_id, requester_id,
                            division, reason, time.time()
                        ))

                except (discord.HTTPException, ValueError) as error:
                    await db.rollback()
                    return await interaction.response.send_message(
                        f"Could not apply this request: {error}",
                        ephemeral=True
                    )

            await db.execute("""
                UPDATE staff_requests
                SET status = ?, reviewed_at = ?, reviewed_by = ?
                WHERE request_id = ? AND status = 'pending'
            """, (
                "approved" if approved else "denied",
                time.time(),
                interaction.user.id,
                self.request_id
            ))
            await db.commit()

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content=(
                f"{'APPROVED' if approved else 'DENIED'} — "
                f"Request `{self.request_id}`"
            ),
            view=self
        )

        requester = guild.get_member(requester_id)
        target = guild.get_member(target_id)

        if requester:
            try:
                await requester.send(
                    f"Your staff request `{request_id}` was "
                    f"{'approved' if approved else 'denied'} by the server owner."
                )
            except discord.HTTPException:
                pass

        if target and approved:
            try:
                await target.send(
                    f"A staff action concerning you was approved: **{action}** "
                    f"in **{division.replace('_', ' ').title()}**."
                )
            except discord.HTTPException:
                pass

    async def approve(self, interaction):
        await self.process(interaction, True)

    async def deny(self, interaction):
        await self.process(interaction, False)


class StaffRequestModal(discord.ui.Modal):
    def __init__(self, cog):
        super().__init__(title="Submit Staff Request")
        self.cog = cog

        self.target = discord.ui.TextInput(
            label="Member ID",
            placeholder="Enter the member's Discord ID"
        )

        self.division = discord.ui.TextInput(
            label="Division",
            placeholder="main_staff / operations_support / ticket_support / staff_managers"
        )

        self.action = discord.ui.TextInput(
            label="Action",
            placeholder="promotion / demotion / strike / note"
        )

        self.role_id = discord.ui.TextInput(
            label="New role ID (promotions/demotions only)",
            required=False
        )

        self.reason = discord.ui.TextInput(
            label="Reason",
            style=discord.TextStyle.paragraph,
            max_length=1000
        )

        for item in (
            self.target, self.division, self.action,
            self.role_id, self.reason
        ):
            self.add_item(item)

    async def on_submit(self, interaction):
        await self.cog.create_request(
            interaction,
            self.target.value,
            self.division.value,
            self.action.value,
            self.role_id.value,
            self.reason.value
        )


class StaffPanelView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    @discord.ui.button(
        label="New staff request",
        style=discord.ButtonStyle.primary,
        emoji="📋"
    )
    async def new_request(self, interaction, button):
        await interaction.response.send_modal(
            StaffRequestModal(self.cog)
        )

    @discord.ui.button(
        label="My requests",
        style=discord.ButtonStyle.secondary,
        emoji="📂"
    )
    async def my_requests(self, interaction, button):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT request_id, action, division, status
                FROM staff_requests
                WHERE guild_id = ? AND requester_id = ?
                ORDER BY created_at DESC LIMIT 10
            """, (
                interaction.guild_id,
                interaction.user.id
            )) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return await interaction.response.send_message(
                "You haven't submitted any staff requests yet.",
                ephemeral=True
            )

        description = "\n".join(
            f"`{row[0]}` — **{row[1]}** / {row[2]} — {row[3]}"
            for row in rows
        )

        await interaction.response.send_message(
            embed=discord.Embed(
                title="Your Staff Requests",
                description=description,
                colour=discord.Colour.blurple()
            ),
            ephemeral=True
        )


class StaffManagement(commands.Cog):
    staffmngr = app_commands.Group(
        name="staffmngr",
        description="Staff management and approval system"
    )

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT request_id, guild_id
                FROM staff_requests
                WHERE status = 'pending'
            """) as cursor:
                rows = await cursor.fetchall()

        for request_id, guild_id in rows:
            self.bot.add_view(
                ApprovalView(self.bot, request_id, guild_id)
            )

    async def is_manager(self, member):
        if member.id == member.guild.owner_id:
            return True

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT role_id FROM staff_role_config
                WHERE guild_id = ? AND division = 'staff_managers'
            """, (member.guild.id,)) as cursor:
                rows = await cursor.fetchall()

        manager_roles = {row[0] for row in rows}
        return any(role.id in manager_roles for role in member.roles)

    async def create_request(
        self, interaction, target_text, division,
        action, role_text, reason
    ):
        if not await self.is_manager(interaction.user):
            return await interaction.response.send_message(
                "You do not have permission to submit staff requests.",
                ephemeral=True
            )

        if division not in DIVISIONS:
            return await interaction.response.send_message(
                "Invalid division name.",
                ephemeral=True
            )

        if action not in ("promotion", "demotion", "strike", "note"):
            return await interaction.response.send_message(
                "Invalid action. Use promotion, demotion, strike or note.",
                ephemeral=True
            )

        try:
            target_id = int(target_text.strip())
        except ValueError:
            return await interaction.response.send_message(
                "The member ID must be a number.",
                ephemeral=True
            )

        guild = interaction.guild
        target = guild.get_member(target_id)

        if target is None:
            try:
                target = await guild.fetch_member(target_id)
            except discord.NotFound:
                return await interaction.response.send_message(
                    "That member is not in this server.",
                    ephemeral=True
                )

        if target.id == guild.owner_id:
            return await interaction.response.send_message(
                "You cannot submit staff actions against the server owner.",
                ephemeral=True
            )

        old_role_id = None
        new_role_id = None

        if action in ("promotion", "demotion"):
            try:
                new_role_id = int(role_text.strip())
            except ValueError:
                return await interaction.response.send_message(
                    "Enter a valid new role ID.",
                    ephemeral=True
                )

            new_role = guild.get_role(new_role_id)
            if new_role is None:
                return await interaction.response.send_message(
                    "That role does not exist in this server.",
                    ephemeral=True
                )

            async with aiosqlite.connect(config.DATABASE) as db:
                async with db.execute("""
                    SELECT role_id FROM staff_role_config
                    WHERE guild_id = ? AND division = ?
                    ORDER BY id
                """, (guild.id, division)) as cursor:
                    configured_roles = {
                        row[0] for row in await cursor.fetchall()
                    }

            if new_role_id not in configured_roles:
                return await interaction.response.send_message(
                    "That role hasn't been configured for this division.",
                    ephemeral=True
                )

            current_roles = [
                role for role in target.roles
                if role.id in configured_roles
            ]

            if current_roles:
                old_role_id = current_roles[0].id

        request_id = uuid.uuid4().hex[:10].upper()

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT INTO staff_requests (
                    request_id, guild_id, requester_id, target_id,
                    division, action, old_role_id, new_role_id,
                    reason, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """, (
                request_id, guild.id, interaction.user.id,
                target.id, division, action, old_role_id,
                new_role_id, reason, time.time()
            ))
            await db.commit()

        owner = guild.get_member(guild.owner_id)

        if owner is None:
            try:
                owner = await guild.fetch_member(guild.owner_id)
            except discord.HTTPException:
                owner = None

        if owner is None:
            return await interaction.response.send_message(
                f"Request `{request_id}` was saved, but I couldn't find the owner to DM.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="Teamy — Staff Approval Required",
            colour=discord.Colour.orange(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Request ID", value=request_id, inline=False)
        embed.add_field(name="Requested by", value=interaction.user.mention)
        embed.add_field(name="Target member", value=target.mention)
        embed.add_field(name="Division", value=division.replace("_", " ").title())
        embed.add_field(name="Action", value=action.title())
        embed.add_field(name="Reason", value=reason, inline=False)

        if new_role_id:
            embed.add_field(
                name="Proposed role",
                value=f"<@&{new_role_id}>"
            )

        try:
            await owner.send(
                embed=embed,
                view=ApprovalView(self.bot, request_id, guild.id)
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                f"Request `{request_id}` was saved, but I couldn't DM you. "
                "Please enable server-member DMs and contact an administrator.",
                ephemeral=True
            )

        self.bot.add_view(
            ApprovalView(self.bot, request_id, guild.id)
        )

        await interaction.response.send_message(
            f"Your request `{request_id}` has been sent to the server owner "
            "for approval. No changes have been made yet.",
            ephemeral=True
        )

    @staffmngr.command(
        name="panel",
        description="Open the staff management panel"
    )
    async def panel(self, interaction: discord.Interaction):
        if not await self.is_manager(interaction.user):
            return await interaction.response.send_message(
                "You don't have permission to access this panel.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="Teamy | Staff Management",
            description=(
                "Welcome to your staff management dashboard.\n\n"
                "Use the buttons below to submit and review your requests.\n\n"
                "All staff actions require server-owner approval."
            ),
            colour=discord.Colour.blurple()
        )

        embed.add_field(
            name="Available functions",
            value=(
                "📈 Promotions\n"
                "📉 Demotions\n"
                "⚠️ Strikes\n"
                "📝 Staff notes\n"
                "📂 Request history"
            ),
            inline=False
        )

        await interaction.response.send_message(
            embed=embed,
            view=StaffPanelView(self),
            ephemeral=True
        )

    @staffmngr.command(
        name="request",
        description="Submit a staff action request"
    )
    @app_commands.describe(
        member="The staff member",
        division="The staff division",
        action="The action to request",
        reason="Why this action is being requested",
        new_role="New role for a promotion or demotion"
    )
    @app_commands.choices(
        division=[
            app_commands.Choice(name="Main Staff", value="main_staff"),
            app_commands.Choice(name="Operations Support", value="operations_support"),
            app_commands.Choice(name="Ticket Support", value="ticket_support"),
            app_commands.Choice(name="Staff Managers", value="staff_managers")
        ],
        action=[
            app_commands.Choice(name="Promotion", value="promotion"),
            app_commands.Choice(name="Demotion", value="demotion"),
            app_commands.Choice(name="Strike", value="strike"),
            app_commands.Choice(name="Staff Note", value="note")
        ]
    )
    async def request(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        division: app_commands.Choice[str],
        action: app_commands.Choice[str],
        reason: str,
        new_role: discord.Role = None
    ):
        await self.create_request(
            interaction,
            str(member.id),
            division.value,
            action.value,
            str(new_role.id) if new_role else "",
            reason
        )

    @staffmngr.command(
        name="setrole",
        description="Configure a role for a staff division (owner only)"
    )
    @app_commands.choices(
        division=[
            app_commands.Choice(name="Main Staff", value="main_staff"),
            app_commands.Choice(name="Operations Support", value="operations_support"),
            app_commands.Choice(name="Ticket Support", value="ticket_support"),
            app_commands.Choice(name="Staff Managers", value="staff_managers")
        ]
    )
    async def setrole(
        self,
        interaction: discord.Interaction,
        division: app_commands.Choice[str],
        role_key: str,
        role: discord.Role
    ):
        if interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message(
                "Only the server owner can configure staff roles.",
                ephemeral=True
            )

        if role_key not in DIVISIONS[division.value]:
            return await interaction.response.send_message(
                "Invalid role key for that division. Use one of: "
                + ", ".join(DIVISIONS[division.value]),
                ephemeral=True
            )

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT INTO staff_role_config
                (guild_id, division, role_key, role_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, division, role_key)
                DO UPDATE SET role_id = excluded.role_id
            """, (
                interaction.guild_id,
                division.value,
                role_key,
                role.id
            ))
            await db.commit()

        await interaction.response.send_message(
            f"Configured {role.mention} as `{role_key}` "
            f"in **{division.name}**.",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(StaffManagement(bot))
