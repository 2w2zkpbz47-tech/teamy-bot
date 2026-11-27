
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import config
import re


class CommunityFeatures(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.afk_users = {}
        self.sticky_cache = {}

    async def cog_load(self):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS afk_users (
                    guild_id INTEGER,
                    user_id INTEGER,
                    reason TEXT,
                    PRIMARY KEY (guild_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS sticky_messages (
                    guild_id INTEGER,
                    channel_id INTEGER,
                    message TEXT,
                    last_message_id INTEGER,
                    PRIMARY KEY (guild_id, channel_id)
                );

                CREATE TABLE IF NOT EXISTS reaction_roles (
                    guild_id INTEGER,
                    message_id INTEGER,
                    emoji TEXT,
                    role_id INTEGER,
                    PRIMARY KEY (guild_id, message_id, emoji)
                );

                CREATE TABLE IF NOT EXISTS custom_commands (
                    guild_id INTEGER,
                    trigger TEXT,
                    response TEXT,
                    created_by INTEGER,
                    PRIMARY KEY (guild_id, trigger)
                );

                CREATE TABLE IF NOT EXISTS suggestions (
                    suggestion_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    channel_id INTEGER,
                    message_id INTEGER,
                    user_id INTEGER,
                    suggestion TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at REAL
                );

                CREATE TABLE IF NOT EXISTS suggestion_votes (
                    guild_id INTEGER,
                    message_id INTEGER,
                    user_id INTEGER,
                    vote INTEGER,
                    PRIMARY KEY (guild_id, message_id, user_id)
                );
            """)
            await db.commit()

    # --------------------------------------------------
    # AFK
    # --------------------------------------------------

    @app_commands.command(name="afk", description="Set yourself as AFK")
    @app_commands.guild_only()
    async def afk(
        self,
        interaction: discord.Interaction,
        reason: str = "AFK"
    ):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT OR REPLACE INTO afk_users
                (guild_id, user_id, reason)
                VALUES (?, ?, ?)
            """, (interaction.guild_id, interaction.user.id, reason[:300]))
            await db.commit()

        self.afk_users[(interaction.guild_id, interaction.user.id)] = reason

        await interaction.response.send_message(
            f"💤 You're now AFK: **{reason}**",
            ephemeral=True
        )

    async def remove_afk(self, member: discord.Member):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                DELETE FROM afk_users
                WHERE guild_id = ? AND user_id = ?
            """, (member.guild.id, member.id))
            await db.commit()

        self.afk_users.pop((member.guild.id, member.id), None)

    # --------------------------------------------------
    # STICKY MESSAGES
    # --------------------------------------------------

    sticky = app_commands.Group(
        name="sticky",
        description="Manage sticky messages"
    )

    @sticky.command(name="set", description="Set a sticky message")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_set(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str
    ):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT OR REPLACE INTO sticky_messages
                (guild_id, channel_id, message, last_message_id)
                VALUES (?, ?, ?, NULL)
            """, (interaction.guild_id, channel.id, message[:1900]))
            await db.commit()

        await interaction.response.send_message(
            f"Sticky message configured for {channel.mention}.",
            ephemeral=True
        )

    @sticky.command(name="remove", description="Remove a sticky message")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_remove(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                DELETE FROM sticky_messages
                WHERE guild_id = ? AND channel_id = ?
            """, (interaction.guild_id, channel.id))
            await db.commit()

        await interaction.response.send_message(
            f"Sticky message removed from {channel.mention}.",
            ephemeral=True
        )

    # --------------------------------------------------
    # REACTION ROLES
    # --------------------------------------------------

    reactionrole = app_commands.Group(
        name="reactionrole",
        description="Configure reaction roles"
    )

    @reactionrole.command(name="add", description="Add a reaction role")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reactionrole_add(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str,
        role: discord.Role
    ):
        try:
            mid = int(message_id)
        except ValueError:
            return await interaction.response.send_message(
                "Message ID must be numeric.",
                ephemeral=True
            )

        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                "My highest role must be above that role.",
                ephemeral=True
            )

        try:
            channel = interaction.channel
            message = await channel.fetch_message(mid)
            await message.add_reaction(emoji)
        except discord.NotFound:
            return await interaction.response.send_message(
                "I couldn't find that message in this channel.",
                ephemeral=True
            )
        except discord.HTTPException:
            return await interaction.response.send_message(
                "I couldn't add that reaction. Check the emoji.",
                ephemeral=True
            )

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT OR REPLACE INTO reaction_roles
                (guild_id, message_id, emoji, role_id)
                VALUES (?, ?, ?, ?)
            """, (interaction.guild_id, mid, emoji, role.id))
            await db.commit()

        await interaction.response.send_message(
            f"Reaction role configured: {emoji} → {role.mention}",
            ephemeral=True
        )

    @reactionrole.command(name="remove", description="Remove a reaction role")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reactionrole_remove(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str
    ):
        try:
            mid = int(message_id)
        except ValueError:
            return await interaction.response.send_message(
                "Message ID must be numeric.",
                ephemeral=True
            )

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                DELETE FROM reaction_roles
                WHERE guild_id = ? AND message_id = ? AND emoji = ?
            """, (interaction.guild_id, mid, emoji))
            await db.commit()

        await interaction.response.send_message(
            "Reaction role configuration removed.",
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None or payload.member is None:
            return

        if payload.member.bot:
            return

        emoji = str(payload.emoji)

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT role_id FROM reaction_roles
                WHERE guild_id = ? AND message_id = ? AND emoji = ?
            """, (payload.guild_id, payload.message_id, emoji)) as cursor:
                row = await cursor.fetchone()

        if not row:
            return

        role = payload.member.guild.get_role(row[0])
        if role:
            try:
                await payload.member.add_roles(role, reason="Reaction role")
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        member = guild.get_member(payload.user_id)
        if member is None or member.bot:
            return

        emoji = str(payload.emoji)

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT role_id FROM reaction_roles
                WHERE guild_id = ? AND message_id = ? AND emoji = ?
            """, (payload.guild_id, payload.message_id, emoji)) as cursor:
                row = await cursor.fetchone()

        if not row:
            return

        role = guild.get_role(row[0])
        if role:
            try:
                await member.remove_roles(role, reason="Reaction role removed")
            except discord.HTTPException:
                pass

    # --------------------------------------------------
    # SELF ROLES
    # --------------------------------------------------

    @app_commands.command(name="selfroles", description="Open the self-role menu")
    @app_commands.guild_only()
    async def selfroles(self, interaction: discord.Interaction):
        roles = [
            role for role in interaction.guild.roles
            if role.name.lower().startswith("self:")
            and role < interaction.guild.me.top_role
        ]

        if not roles:
            return await interaction.response.send_message(
                "There are no self-assignable roles configured.\n"
                "Create roles beginning with `Self:` to make them available.",
                ephemeral=True
            )

        roles = roles[:25]

        options = [
            discord.SelectOption(
                label=role.name[5:].strip()[:100],
                value=str(role.id)
            )
            for role in roles
        ]

        class SelfRoleSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(
                    placeholder="Choose your roles...",
                    min_values=0,
                    max_values=len(options),
                    options=options
                )

            async def callback(self, select_interaction):
                selected = {int(value) for value in self.values}
                selected_roles = [
                    role for role in roles if role.id in selected
                ]

                current = [
                    role for role in roles
                    if role in select_interaction.user.roles
                ]

                add_roles = [
                    role for role in selected_roles
                    if role not in current
                ]

                remove_roles = [
                    role for role in current
                    if role not in selected_roles
                ]

                try:
                    if add_roles:
                        await select_interaction.user.add_roles(*add_roles)

                    if remove_roles:
                        await select_interaction.user.remove_roles(*remove_roles)

                except discord.HTTPException:
                    return await select_interaction.response.send_message(
                        "I couldn't update your roles. Check my permissions.",
                        ephemeral=True
                    )

                await select_interaction.response.send_message(
                    "Your self-roles have been updated!",
                    ephemeral=True
                )

        view = discord.ui.View(timeout=180)
        view.add_item(SelfRoleSelect())

        await interaction.response.send_message(
            "Select the roles you want. Unselect roles to remove them.",
            view=view,
            ephemeral=True
        )

    # --------------------------------------------------
    # CUSTOM COMMANDS
    # --------------------------------------------------

    custom = app_commands.Group(
        name="custom",
        description="Manage custom server commands"
    )

    @custom.command(name="add", description="Create a custom text command")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def custom_add(
        self,
        interaction: discord.Interaction,
        trigger: str,
        response: str
    ):
        trigger = trigger.lower().strip()

        if not re.fullmatch(r"[a-z0-9_-]{1,32}", trigger):
            return await interaction.response.send_message(
                "Trigger can only contain letters, numbers, underscores "
                "and hyphens (maximum 32 characters).",
                ephemeral=True
            )

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT OR REPLACE INTO custom_commands
                (guild_id, trigger, response, created_by)
                VALUES (?, ?, ?, ?)
            """, (
                interaction.guild_id,
                trigger,
                response[:1900],
                interaction.user.id
            ))
            await db.commit()

        await interaction.response.send_message(
            f"Custom command `!{trigger}` created.",
            ephemeral=True
        )

    @custom.command(name="remove", description="Delete a custom command")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def custom_remove(
        self,
        interaction: discord.Interaction,
        trigger: str
    ):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                DELETE FROM custom_commands
                WHERE guild_id = ? AND trigger = ?
            """, (interaction.guild_id, trigger.lower().strip()))
            await db.commit()

        await interaction.response.send_message(
            "Custom command removed if it existed.",
            ephemeral=True
        )

    @custom.command(name="list", description="List custom commands")
    async def custom_list(self, interaction: discord.Interaction):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT trigger FROM custom_commands
                WHERE guild_id = ?
                ORDER BY trigger
            """, (interaction.guild_id,)) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return await interaction.response.send_message(
                "No custom commands configured.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "**Custom Commands:**\n" +
            "\n".join(f"`!{row[0]}`" for row in rows),
            ephemeral=True
        )

    # --------------------------------------------------
    # SUGGESTIONS
    # --------------------------------------------------

    @app_commands.command(name="suggest", description="Submit a server suggestion")
    @app_commands.guild_only()
    async def suggest(
        self,
        interaction: discord.Interaction,
        suggestion: str
    ):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT channel_id FROM guild_config
                WHERE guild_id = ?
            """, (interaction.guild_id,)) as cursor:
                row = await cursor.fetchone()

        # Suggestions use the configured level channel until a dedicated
        # suggestion-channel setting is added.
        channel = interaction.guild.get_channel(row[0]) if row and row[0] else None

        if channel is None:
            return await interaction.response.send_message(
                "The suggestions channel hasn't been configured.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="💡 New Suggestion",
            description=suggestion[:4000],
            colour=discord.Colour.gold()
        )

        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url
        )

        embed.set_footer(text="Status: Pending • Vote below")

        message = await channel.send(embed=embed)

        try:
            thread = await message.create_thread(
                name=f"Suggestion discussion - {interaction.user.display_name}"[:100]
            )
            await thread.send(
                "Discuss this suggestion respectfully. Staff will review it."
            )
        except discord.HTTPException:
            pass

        await message.add_reaction("👍")
        await message.add_reaction("👎")

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT INTO suggestions
                (guild_id, channel_id, message_id, user_id, suggestion, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """, (
                interaction.guild_id,
                channel.id,
                message.id,
                interaction.user.id,
                suggestion[:4000],
                discord.utils.utcnow().timestamp()
            ))
            await db.commit()

        await interaction.response.send_message(
            f"Your suggestion has been submitted to {channel.mention}!",
            ephemeral=True
        )

    @app_commands.command(name="suggestion", description="Approve or deny a suggestion")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.choices(action=[
        app_commands.Choice(name="Approve", value="approved"),
        app_commands.Choice(name="Deny", value="denied")
    ])
    async def suggestion_review(
        self,
        interaction: discord.Interaction,
        message_id: str,
        action: app_commands.Choice[str],
        reason: str = "No reason provided"
    ):
        try:
            mid = int(message_id)
        except ValueError:
            return await interaction.response.send_message(
                "Message ID must be numeric.",
                ephemeral=True
            )

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT channel_id, status FROM suggestions
                WHERE guild_id = ? AND message_id = ?
            """, (interaction.guild_id, mid)) as cursor:
                row = await cursor.fetchone()

            if not row:
                return await interaction.response.send_message(
                    "Suggestion not found.",
                    ephemeral=True
                )

            if row[1] != "pending":
                return await interaction.response.send_message(
                    "This suggestion has already been reviewed.",
                    ephemeral=True
                )

            await db.execute("""
                UPDATE suggestions
                SET status = ?
                WHERE guild_id = ? AND message_id = ?
            """, (action.value, interaction.guild_id, mid))
            await db.commit()

        channel = interaction.guild.get_channel(row[0])

        if channel:
            try:
                message = await channel.fetch_message(mid)
                if message.embeds:
                    embed = message.embeds[0]
                    embed.colour = (
                        discord.Colour.green()
                        if action.value == "approved"
                        else discord.Colour.red()
                    )
                    embed.set_footer(
                        text=f"Status: {action.value.title()} • Reviewed by {interaction.user}"
                    )
                    embed.add_field(
                        name="Review reason",
                        value=reason[:1000],
                        inline=False
                    )
                    await message.edit(embed=embed)
            except discord.HTTPException:
                pass

        await interaction.response.send_message(
            f"Suggestion **{action.value}**.",
            ephemeral=True
        )

    # --------------------------------------------------
    # MESSAGE LISTENER: AFK, STICKY, CUSTOM COMMANDS
    # --------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return

        guild_id = message.guild.id
        user_id = message.author.id

        # Clear AFK when the user speaks.
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT reason FROM afk_users
                WHERE guild_id = ? AND user_id = ?
            """, (guild_id, user_id)) as cursor:
                afk_row = await cursor.fetchone()

        if afk_row:
            await self.remove_afk(message.author)

            try:
                await message.reply(
                    f"👋 Welcome back! Your AFK status has been removed.",
                    delete_after=8
                )
            except discord.HTTPException:
                pass

        # Notify when an AFK user is mentioned.
        for mentioned in message.mentions:
            async with aiosqlite.connect(config.DATABASE) as db:
                async with db.execute("""
                    SELECT reason FROM afk_users
                    WHERE guild_id = ? AND user_id = ?
                """, (guild_id, mentioned.id)) as cursor:
                    row = await cursor.fetchone()

            if row:
                try:
                    await message.reply(
                        f"💤 **{mentioned.display_name}** is AFK: {row[0]}",
                        delete_after=12
                    )
                except discord.HTTPException:
                    pass

        # Custom commands use !trigger.
        content = message.content.strip()

        if content.startswith("!"):
            trigger = content[1:].lower().split()[0] if content[1:].strip() else ""

            if trigger:
                async with aiosqlite.connect(config.DATABASE) as db:
                    async with db.execute("""
                        SELECT response FROM custom_commands
                        WHERE guild_id = ? AND trigger = ?
                    """, (guild_id, trigger)) as cursor:
                        row = await cursor.fetchone()

                if row:
                    response = row[0]
                    response = response.replace("{user}", message.author.mention)
                    response = response.replace("{server}", message.guild.name)

                    try:
                        await message.channel.send(response)
                    except discord.HTTPException:
                        pass

        # Sticky messages are reposted after every five messages.
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT message, last_message_id
                FROM sticky_messages
                WHERE guild_id = ? AND channel_id = ?
            """, (guild_id, message.channel.id)) as cursor:
                sticky_row = await cursor.fetchone()

            if sticky_row:
                sticky_text, last_id = sticky_row

                count = 0

                if last_id:
                    try:
                        async for msg in message.channel.history(
                            limit=20,
                            after=discord.Object(id=last_id)
                        ):
                            if not msg.author.bot:
                                count += 1
                    except discord.HTTPException:
                        count = 5

                if count >= 5:
                    try:
                        sticky_message = await message.channel.send(sticky_text)

                        await db.execute("""
                            UPDATE sticky_messages
                            SET last_message_id = ?
                            WHERE guild_id = ? AND channel_id = ?
                        """, (
                            sticky_message.id,
                            guild_id,
                            message.channel.id
                        ))
                        await db.commit()
                    except discord.HTTPException:
                        pass


async def setup(bot):
    await bot.add_cog(CommunityFeatures(bot))
