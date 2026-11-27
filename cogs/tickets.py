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
            # The general staff role configured in /setup is also allowed.
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

        # Use the existing configured ticket category and general staff role.
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
            character.lower() if character.isalnum() else "-"
            for character in interaction.user.name
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
            """, (
                channel.id,
                guild.id,
                interaction.user.id,
                category,
                time.time()
            ))
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
            embed.add_field(
                name="Why were you banned?",
                value=appeal_data["reason"][:1000],
                inline=False
            )
            embed.add_field(
                name="Why should we unban you?",
                value=appeal_data["why"][:1000],
                inline=False
            )
            embed.add_field(
                name="What will you do differently?",
                value=appeal_data["changes"][:1000],
                inline=False
            )

        try:
            await channel.send(
                content=interaction.user.mention,
                embed=embed,
                view=TicketControlView()
            )
        except discord.HTTPException:
            pass

        await interaction.followup.send(
            f"✅ Your ticket has been created: {channel.mention}",
            ephemeral=True
        )

    async def ticket_from_interaction(self, interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This can only be used inside a server.",
                ephemeral=True
            )
            return None
        ticket = await get_ticket(interaction.channel_id)
        if not ticket or ticket[1] != interaction.guild.id:
            await interaction.response.send_message(
                "