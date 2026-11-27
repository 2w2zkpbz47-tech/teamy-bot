import io
import time
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import config

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------
async def ensure_ticket_tables():
    async with aiosqlite.connect(config.DATABASE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                claimed_by INTEGER,
                created_at REAL NOT NULL,
                closed INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ticket_panel_config (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                message_id INTEGER
            )
        """)
        await db.commit()

# ------------------------------------------------------------
# PERMISSIONS / HELPERS
# ------------------------------------------------------------
async def is_ticket_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_channels:
        return True
    async with aiosqlite.connect(config.DATABASE) as db:
        async with db.execute("""
            SELECT role_id
            FROM staff_role_config
            WHERE guild_id = ? AND division = 'ticket_support'
        """, (member.guild.id,)) as cursor:
            rows = await cursor.fetchall()
            configured_roles = {row[0] for row in rows}
            async with aiosqlite.connect(config.DATABASE) as db:
                async with db.execute(
                    "SELECT staff_role FROM guild_config WHERE guild_id = ?",
                    (member.guild.id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row and row[0]:
                        configured_roles.add(row[0])
            return any(role.id in configured_roles for role in member.roles)

async def get_ticket(channel_id: int):
    async with aiosqlite.connect(config.DATABASE) as db:
        async with db.execute("""
            SELECT channel_id, guild_id, user_id, category,
                   claimed_by, created_at, closed
            FROM tickets
            WHERE channel_id = ?
        """, (channel_id,)) as cursor:
            return await cursor.fetchone()

async def get_ticket_support_role_ids(guild_id: int):
    async with aiosqlite.connect(config.DATABASE) as db:
        async with db.execute("""
            SELECT role_id
            FROM staff_role_config
            WHERE guild_id = ? AND division = 'ticket_support'
        """, (guild_id,)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

# ------------------------------------------------------------
# BAN APPEAL MODAL
# ------------------------------------------------------------
class BanAppealModal(discord.ui.Modal, title="Ban Appeal"):
    reason = discord.ui.TextInput(
        label="Why were you banned?",
        style=discord.TextStyle.paragraph,
        max_length=700
    )
    why_unban = discord.ui.TextInput(
        label="Why should we unban you?",
        style=discord.TextStyle.paragraph,
        max_length=700
    )
    changes = discord.ui.TextInput(
        label="What will you do differently?",
        style=discord.TextStyle.paragraph,
        max_length=700
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.create_ticket(
            interaction,
            "Ban Appeal",
            {
                "reason": self.reason.value,
                "why": self.why_unban.value,
                "changes": self.changes.value
            }
        )

# ------------------------------------------------------------
# TICKET PANEL
# ------------------------------------------------------------
class TicketPanelView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Support",
        emoji="🛟",
        style=discord.ButtonStyle.primary,
        custom_id="teamy_ticket:open:support"
    )
    async def support(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.create_ticket(interaction, "Support")

    @discord.ui.button(
        label="Report Player",
        emoji="🚨",
        style=discord.ButtonStyle.danger,
        custom_id="teamy_ticket:open:report"
    )
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.create_ticket(interaction, "Player Report")

    @discord.ui.button(
        label="Ban Appeal",
        emoji="⚖️",
        style=discord.ButtonStyle.secondary,
        custom_id="teamy_ticket:open:appeal"
    )
    async def appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BanAppealModal(self.cog))

    @discord.ui.button(
        label="Other",
        emoji="💬",
        style=discord.ButtonStyle.success,
        custom_id="teamy_ticket:open:other"
    )
    async def other(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.create_ticket(interaction, "Other")

# ------------------------------------------------------------
# TICKET CONTROLS
# ------------------------------------------------------------
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Claim",
        emoji="🙋",
        style=discord.ButtonStyle.primary,
        custom_id="teamy_ticket:claim"
    )
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("Tickets")
        if cog is None:
            return await interaction.response.send_message(
                "The ticket system is unavailable right now.",
                ephemeral=True
            )
        await cog.claim_ticket(interaction)

    @discord.ui.button(
        label="Close",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="teamy_ticket:close"
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("Tickets")
        if cog is None:
            return await interaction.response.send_message(
                "The ticket system is unavailable right now.",
                ephemeral=True
            )
        await cog.close_ticket(interaction)

    @discord.ui.button(
        label="Reopen",
        emoji="🔓",
        style=discord.ButtonStyle.success,
        custom_id="teamy_ticket:reopen"
    )
    async def reopen(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("Tickets")
        if cog is None:
            return await interaction.response.send_message(
                "The ticket system is unavailable right now.",
                ephemeral=True
            )
        await cog.reopen_ticket(interaction)

    @discord.ui.button(
        label="Delete",
        emoji="🗑️",
        style=discord.ButtonStyle.secondary,
        custom_id="teamy_ticket:delete"
    )
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("Tickets")
        if cog is None:
            return await interaction.response.send_message(
                "The ticket system is unavailable right now.",
                ephemeral=True
            )
        await cog.delete_ticket(interaction)

# ------------------------------------------------------------
# MAIN TICKETS COG
# ------------------------------------------------------------
class Tickets(commands.Cog):
    ticket = app_commands.Group(
        name="ticket",
        description="Create and manage support tickets"
    )
    ticketsupport = app_commands.Group(
        name="ticketsupport",
        description="Ticket Support team tools"
    )

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        await ensure_ticket_tables()
        self.bot.add_view(TicketPanelView(self))
        self.bot.add_view(TicketControlView())

    async def create_ticket(self, interaction, category, appeal_data=None):
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message(
                "Tickets can only be created inside a server.",
                ephemeral=True
            )
        await interaction.response.defer(ephemeral=True, thinking=True)
        existing = await get_ticket_for_user(guild.id, interaction.user.id)
        if existing:
            existing_channel = guild.get_channel(existing[0])
            if existing_channel:
                return await interaction.followup.send(
                    f"You already have an open ticket: {existing_channel.mention}",
                    ephemeral=True
                )
            async with aiosqlite.connect(config.DATABASE) as db:
                await db.execute(
                    "UPDATE tickets SET closed = 1 WHERE channel_id = ?",
                    (existing[0],)
                )
                await db.commit()

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute(
                "SELECT staff_role, ticket_category FROM guild_config WHERE guild_id = ?",
                (guild.id,)
            ) as cursor:
                guild_config = await cursor.fetchone()

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True
            )
        }
        bot_member = guild.me or guild.get_member(self.bot.user.id)
        if bot_member:
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
                read_message_history=True
            )
        if guild_config and guild_config[0]:
            staff_role = guild.get_role(guild_config[0])
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )
        for role_id in await get_ticket_support_role_ids(guild.id):
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )

        category_channel = None
        if guild_config and guild_config[1]:
            category_channel = guild.get_channel(guild_config[1])

        safe_name = "".join(
            c.lower() if c.isalnum() else "-" for c in interaction.user.name
        ).strip("-")[:18] or "member"

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{safe_name}",
                overwrites=overwrites,
                category=category_channel,
                topic=f"{category} ticket | {interaction.user} ({interaction.user.id})"
            )
        except discord.Forbidden:
            return await interaction.followup.send(
                "I cannot create the ticket channel. Please check my Manage Channels permission.",
                ephemeral=True
            )

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT INTO tickets
                (channel_id, guild_id, user_id, category, claimed_by, created_at, closed)
                VALUES (?, ?, ?, ?, NULL, ?, 0)
            """, (channel.id, guild.id, interaction.user.id, category, time.time()))
            await db.commit()

        embed = discord.Embed(
            title=f"🎫 Ticket Opened — {category}",
            description=(
                f"Hello {interaction.user.mention}!\n"
                "A member of the team will be with you as soon as possible.\n\n"
                f"**Category:** {category}\n"
                f"**Created by:** {interaction.user.mention}"
            ),
            colour=getattr(config, "COLOR_TICKET", 0x3498DB),
            timestamp=discord.utils.utcnow()
        )
        if appeal_data:
            embed.add_field(name="Why were you banned?", value=appeal_data["reason"][:1000], inline=False)
            embed.add_field(name="Why should we unban you?", value=appeal_data["why"][:1000], inline=False)
            embed.add_field(name="What will you do differently?", value=appeal_data["changes"][:1000], inline=False)

        try:
            await channel.send(content=interaction.user.mention, embed=embed, view=TicketControlView())
        except discord.HTTPException:
            pass

        await interaction.followup.send(f"✅ Your ticket has been created: {channel.mention}", ephemeral=True)

    async def ticket_from_interaction(self, interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This can only be used inside a server.", ephemeral=True)
            return None
        ticket = await get_ticket(interaction.channel_id)
        if not ticket or ticket[1] != interaction.guild.id:
            await interaction.response.send_message("This channel is not a registered ticket.", ephemeral=True)
            return None
        return ticket

    async def claim_ticket(self, interaction):
        ticket = await self.ticket_from_interaction(interaction)
        if not ticket:
            return
        if not await is_ticket_staff(interaction.user):
            return await interaction.response.send_message("Only the Ticket Support team can claim tickets.", ephemeral=True)
        if ticket[4]:
            return await interaction.response.send_message(f"This ticket is already claimed by <@{ticket[4]}>.", ephemeral=True)
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("UPDATE  tickets SET claimed_by = ? WHERE channel_id = ?",
                (interaction.user.id, interaction.channel_id)
            )
            await db.commit()
        await interaction.response.send_message(f"🙋 Ticket claimed by {interaction.user.mention}.")

    async def close_ticket(self, interaction):
        ticket = await self.ticket_from_interaction(interaction)
        if not ticket:
            return
        is_owner = interaction.user.id == ticket[2]
        if not is_owner and not await is_ticket_staff(interaction.user):
            return await interaction.response.send_message(
                "Only the ticket creator or Ticket Support team can close this ticket.",
                ephemeral=True
            )
        await interaction.channel.set_permissions(
            interaction.guild.get_member(ticket[2]),
            view_channel=True,
            send_messages=False,
            read_message_history=True
        )
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                "UPDATE tickets SET closed = 1 WHERE channel_id = ?",
                (interaction.channel_id,)
            )
            await db.commit()
        await interaction.response.send_message(
            f"🔒 Ticket closed by {interaction.user.mention}. Staff can reopen it or delete it."
        )

    async def reopen_ticket(self, interaction):
        ticket = await self.ticket_from_interaction(interaction)
        if not ticket:
            return
        if not await is_ticket_staff(interaction.user):
            return await interaction.response.send_message(
                "Only the Ticket Support team can reopen tickets.",
                ephemeral=True
            )
        member = interaction.guild.get_member(ticket[2])
        if member:
            await interaction.channel.set_permissions(
                member,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True
            )
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                "UPDATE tickets SET closed = 0 WHERE channel_id = ?",
                (interaction.channel_id,)
            )
            await db.commit()
        await interaction.response.send_message(f"🔓 Ticket reopened by {interaction.user.mention}.")

    async def delete_ticket(self, interaction):
        ticket = await self.ticket_from_interaction(interaction)
        if not ticket:
            return
        if not await is_ticket_staff(interaction.user):
            return await interaction.response.send_message(
                "Only the Ticket Support team can delete tickets.",
                ephemeral=True
            )
        await interaction.response.send_message("🗑️ Deleting this ticket channel in a moment.")
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("DELETE FROM tickets WHERE channel_id = ?", (interaction.channel_id,))
            await db.commit()
        await interaction.channel.delete(reason=f"Ticket deleted by {interaction.user}")

    # ---------------- SLASH COMMAND GROUP: /ticket ----------------

    @ticket.command(name="panel", description="Post the ticket creation panel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_panel(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        target = channel or interaction.channel
        embed = discord.Embed(
            title="🎫 Teamy Support",
            description=(
                "Need help? Choose the option below to open a private ticket.\n\n"
                "🛟 **Support** — General help and questions\n"
                "🚨 **Report Player** — Report a player\n"
                "⚖️ **Ban Appeal** — Appeal a server ban\n"
                "💬 **Other** — Anything else"
            ),
            colour=getattr(config, "COLOR_TICKET", 0x3498DB)
        )
        await target.send(embed=embed, view=TicketPanelView(self))
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT OR REPLACE INTO ticket_panel_config
                (guild_id, channel_id, message_id) VALUES (?, ?, NULL)
            """, (interaction.guild.id, target.id))
            await db.commit()
        await interaction.response.send_message(f"✅ Ticket panel posted in {target.mention}.", ephemeral=True)

    @ticket.command(name="adduser", description="Add a member to this ticket")
    async def ticket_adduser(self, interaction: discord.Interaction, member: discord.Member):
        ticket = await self.ticket_from_interaction(interaction)
        if not ticket:
            return
        if not await is_ticket_staff(interaction.user):
            return await interaction.response.send_message(
                "Only the Ticket Support team can add members.", ephemeral=True
            )
        await interaction.channel.set_permissions(
            member, view_channel=True, send_messages=True,
            read_message_history=True, attach_files=True
        )
        await interaction.response.send_message(f"✅ Added {member.mention} to this ticket.")

    @ticket.command(name="removeuser", description="Remove a member from this ticket")
    async def ticket_removeuser(self, interaction: discord.Interaction, member: discord.Member):
        ticket = await self.ticket_from_interaction(interaction)
        if not ticket:
            return
        if not await is_ticket_staff(interaction.user):
            return await interaction.response.send_message(
                "Only the Ticket Support team can remove members.", ephemeral=True
            )
        if member.id == ticket[2]:
            return await interaction.response.send_message(
                "You cannot remove the ticket creator.", ephemeral=True
            )
        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(f"✅ Removed {member.mention} from this ticket.")

    @ticket.command(name="claim", description="Claim the current ticket")
    async def ticket_claim(self, interaction: discord.Interaction):
        await self.claim_ticket(interaction)

    @ticket.command(name="close", description="Close the current ticket")
    async def ticket_close(self, interaction: discord.Interaction):
        await self.close_ticket(interaction)

    @ticket.command(name="reopen", description="Reopen the current ticket")
    async def ticket_reopen(self, interaction: discord.Interaction):
        await self.reopen_ticket(interaction)

    @ticket.command(name="delete", description="Delete the current ticket")
    async def ticket_delete(self, interaction: discord.Interaction):
        await self.delete_ticket(interaction)

    @ticket.command(name="rename", description="Rename the current ticket")
    async def ticket_rename(self, interaction: discord.Interaction, name: str):
        ticket = await self.ticket_from_interaction(interaction)
        if not ticket:
            return
        if not await is_ticket_staff(interaction.user):
            return await interaction.response.send_message(
                "Only the Ticket Support team can rename tickets.", ephemeral=True
            )
        clean_name = "".join(
            c.lower() if c.isalnum() or c == "-" else "-" for c in name
        ).strip("-")[:90]
        if not clean_name:
            return await interaction.response.send_message("Please provide a valid channel name.", ephemeral=True)
        await interaction.channel.edit(name=clean_name)
        await interaction.response.send_message(f"✅ Ticket renamed to **{clean_name}**.")

    @ticket.command(name="transcript", description="Create a text transcript of this ticket")
    async def ticket_transcript(self, interaction: discord.Interaction):
        ticket = await self.ticket_from_interaction(interaction)
        if not ticket:
            return
        if interaction.user.id != ticket[2] and not await is_ticket_staff(interaction.user):
            return await interaction.response.send_message(
                "Only the ticket creator or Ticket Support team can create a transcript.", ephemeral=True
            )
        await interaction.response.defer(ephemeral=True, thinking=True)
        lines = []
        async for message in interaction.channel.history(limit=500, oldest_first=True):
            ts = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            content = message.content or ""
            if message.attachments:
                content += " " + " ".join(a.url for a in message.attachments)
            if message.embeds:
                content += " [embed]"
            lines.append(f"[{ts}] {message.author} ({message.author.id}): {content}")
        transcript = "\n".join(lines) or "No messages found."
        file = discord.File(
            io.BytesIO(transcript.encode("utf-8")),
            filename=f"ticket-{interaction.channel.id}-transcript.txt"
        )
        await interaction.followup.send("Here is the ticket transcript.", file=file, ephemeral=True)

    # ---------------- TICKET SUPPORT TEAM TOOLS ----------------

    @ticketsupport.command(name="panel", description="Post the Ticket Support team panel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticketsupport_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎟️ Ticket Support",
            description=(
                "Ticket Support staff can use the ticket controls or slash commands "
                "inside ticket channels to claim, close, reopen and manage tickets."
            ),
            colour=getattr(config, "COLOR_STAFF", 0xE67E22)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ticketsupport.command(name="claim", description="Claim the ticket you are viewing")
    async def ticketsupport_claim(self, interaction: discord.Interaction):
        await self.claim_ticket(interaction)

    @ticketsupport.command(name="overview", description="Show open tickets")
    async def ticketsupport_overview(self, interaction: discord.Interaction):
        if not await is_ticket_staff(interaction.user):
            return await interaction.response.send_message(
                "Only the Ticket Support team can view this overview.", ephemeral=True
            )
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT channel_id, user_id, category, claimed_by, created_at
                FROM tickets
                WHERE guild_id = ? AND closed = 0
                ORDER BY created_at ASC LIMIT 25
            """, (interaction.guild.id,)) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            return await interaction.response.send_message("There are no open tickets.", ephemeral=True)
        desc = []
        for ch_id, user_id, category, claimed_by, _ in rows:
            ch = interaction.guild.get_channel(ch_id)
            ch_text = ch.mention if ch else f"`{ch_id}`"
            claimed = f"<@{claimed_by}>" if claimed_by else "Unclaimed"
            desc.append(f"{ch_text} — **{category}** — <@{user_id}> — {claimed}")
        embed = discord.Embed(
            title="📋 Open Tickets",
            description="\n".join(desc),
            colour=getattr(config, "COLOR_TICKET", 0x3498DB)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def get_ticket_for_user(guild_id: int, user_id: int):
    async with aiosqlite.connect(config.DATABASE) as db:
        async with db.execute("""
            SELECT channel_id FROM tickets
            WHERE guild_id = ? AND user_id = ? AND closed = 0
            ORDER BY created_at DESC LIMIT 1
        """, (guild_id, user_id)) as cursor:
            return await cursor.fetchone()


async def setup(bot):
    # Remove existing command group first to avoid duplicate registration error
    existing = bot.tree.get_command("ticketsupport")
    if existing:
        bot.tree.remove_command("ticketsupport")
    existing_ticket = bot.tree.get_command("ticket")
    if existing_ticket:
        bot.tree.remove_command("ticket")
    await bot.add_cog(Tickets(bot))