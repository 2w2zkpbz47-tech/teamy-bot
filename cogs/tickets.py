
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import aiosqlite
from datetime import datetime, timezone
import config
from utils.embeds import create_embed
from utils.database import get_config


def is_ticket_staff(member: discord.Member, configured_staff_role=None):
    if member.guild_permissions.administrator or member.guild_permissions.manage_channels:
        return True

    if configured_staff_role and configured_staff_role in member.roles:
        return True

    return member.guild_permissions.moderate_members


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="setup-tickets",
        description="Post the Ticket & Appeal panel"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tickets(self, interaction: discord.Interaction):
        embed = create_embed(
            "🎫 Support & Ban Appeals",
            "Need help? Want to report a player? Or appeal a punishment?\n\n"
            "Click the button that matches your request below."
        )

        await interaction.channel.send(
            embed=embed,
            view=TicketPanelView()
        )

        await interaction.response.send_message(
            "✅ Ticket panel posted!",
            ephemeral=True
        )


# --------------------------------------------------
# TICKET PANEL
# --------------------------------------------------

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Support",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="ticket:support"
    )
    async def support(self, interaction: discord.Interaction, button: Button):
        await create_ticket(interaction, "Support")

    @discord.ui.button(
        label="Report Player",
        style=discord.ButtonStyle.danger,
        emoji="🚨",
        custom_id="ticket:report"
    )
    async def report(self, interaction: discord.Interaction, button: Button):
        await create_ticket(interaction, "Report")

    @discord.ui.button(
        label="Ban Appeal",
        style=discord.ButtonStyle.secondary,
        emoji="🔄",
        custom_id="ticket:appeal"
    )
    async def appeal(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(AppealModal())

    @discord.ui.button(
        label="Other",
        style=discord.ButtonStyle.secondary,
        emoji="❓",
        custom_id="ticket:other"
    )
    async def other(self, interaction: discord.Interaction, button: Button):
        await create_ticket(interaction, "Other")


class AppealModal(Modal, title="Ban Appeal Form"):
    reason = TextInput(
        label="Why were you banned?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=800
    )

    why_unban = TextInput(
        label="Why should we unban you?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=800
    )

    changes = TextInput(
        label="What will you do differently?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=800
    )

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(
            interaction,
            "Ban Appeal",
            appeal_data={
                "reason": self.reason.value,
                "why": self.why_unban.value,
                "changes": self.changes.value
            }
        )


# --------------------------------------------------
# CREATE TICKET
# --------------------------------------------------

async def create_ticket(
    interaction: discord.Interaction,
    category: str,
    appeal_data: dict = None
):
    guild = interaction.guild

    if guild is None:
        return await interaction.response.send_message(
            "Tickets can only be opened inside a server.",
            ephemeral=True
        )

    config_data = await get_config(guild.id)

    async with aiosqlite.connect(config.DATABASE) as db:
        async with db.execute(
            """
            SELECT channel_id
            FROM tickets
            WHERE guild_id = ? AND user_id = ? AND closed = 0
            """,
            (guild.id, interaction.user.id)
        ) as cursor:
            existing = await cursor.fetchone()

    if existing:
        existing_channel = guild.get_channel(existing[0])

        if existing_channel:
            return await interaction.response.send_message(
                f"You already have an open ticket: {existing_channel.mention}",
                ephemeral=True
            )

        # Clean up a stale ticket record if its channel was deleted.
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                "UPDATE tickets SET closed = 1 WHERE channel_id = ?",
                (existing[0],)
            )
            await db.commit()

    bot_member = guild.me

    if bot_member is None:
        bot_member = guild.get_member(interaction.client.user.id)

    if bot_member is None:
        return await interaction.response.send_message(
            "I couldn't identify my server member account.",
            ephemeral=True
        )

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False
        ),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True
        ),
        bot_member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True
        )
    }

    staff_role = None

    if config_data and len(config_data) > 5 and config_data[5]:
        staff_role = guild.get_role(config_data[5])

        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True
            )

    category_channel = None

    if config_data and len(config_data) > 6 and config_data[6]:
        possible_category = guild.get_channel(config_data[6])

        if isinstance(possible_category, discord.CategoryChannel):
            category_channel = possible_category

    try:
        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name[:18]}",
            overwrites=overwrites,
            category=category_channel,
            topic=(
                f"{category} ticket for {interaction.user} "
                f"({interaction.user.id})"
            )
        )
    except discord.Forbidden:
        return await interaction.response.send_message(
            "❌ I don't have permission to create ticket channels.",
            ephemeral=True
        )

    async with aiosqlite.connect(config.DATABASE) as db:
        await db.execute(
            """
            INSERT INTO tickets
            (channel_id, guild_id, user_id, category, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                channel.id,
                guild.id,
                interaction.user.id,
                category,
                datetime.now(timezone.utc).timestamp()
            )
        )
        await db.commit()

    embed = create_embed(
        f"🎫 Ticket Opened — {category}",
        (
            f"Hello {interaction.user.mention}!\n"
            "A staff member will be with you as soon as possible.\n\n"
            f"**Category:** {category}"
        ),
        config.COLOR_TICKET
    )

    if appeal_data:
        embed.add_field(
            name="Why were you banned?",
            value=appeal_data["reason"][:300],
            inline=False
        )
        embed.add_field(
            name="Why should we unban you?",
            value=appeal_data["why"][:300],
            inline=False
        )
        embed.add_field(
            name="What will you do differently?",
            value=appeal_data["changes"][:300],
            inline=False
        )

    await channel.send(
        content=interaction.user.mention,
        embed=embed,
        view=TicketControlView()
    )

    await interaction.response.send_message(
        f"✅ Ticket created: {channel.mention}",
        ephemeral=True
    )


# --------------------------------------------------
# TICKET CONTROLS
# --------------------------------------------------

class TicketControlView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Claim",
        style=discord.ButtonStyle.primary,
        emoji="✋",
        custom_id="ticket:claim"
    )
    async def claim(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild or not isinstance(
            interaction.user, discord.Member
        ):
            return await interaction.response.send_message(
                "This button can only be used inside a server.",
                ephemeral=True
            )

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute(
                """
                SELECT claimed_by, guild_id
                FROM tickets
                WHERE channel_id = ?
                """,
                (interaction.channel.id,)
            ) as cursor:
                ticket = await cursor.fetchone()

            if not ticket:
                return await interaction.response.send_message(
                    "❌ This channel isn't registered as a ticket.",
                    ephemeral=True
                )

            claimed_by, guild_id = ticket

            if guild_id != interaction.guild.id:
                return await interaction.response.send_message(
                    "❌ This ticket belongs to another server.",
                    ephemeral=True
                )

            config_data = await get_config(interaction.guild.id)
            staff_role = (
                interaction.guild.get_role(config_data[5])
                if config_data and len(config_data) > 5 and config_data[5]
                else None
            )

            if not is_ticket_staff(interaction.user, staff_role):
                return await interaction.response.send_message(
                    "❌ Only authorised staff can claim tickets.",
                    ephemeral=True
                )

            if claimed_by:
                return await interaction.response.send_message(
                    f"❌ This ticket has already been claimed by <@{claimed_by}>.",
                    ephemeral=True
                )

            await db.execute(
                """
                UPDATE tickets
                SET claimed_by = ?
                WHERE channel_id = ? AND claimed_by IS NULL
                """,
                (interaction.user.id, interaction.channel.id)
            )
            await db.commit()

        button.disabled = True
        button.label = f"Claimed by {interaction.user.display_name}"[:80]

        await interaction.response.edit_message(
            view=self
        )

        await interaction.followup.send(
            embed=create_embed(
                "✅ Ticket Claimed",
                f"This ticket has been claimed by {interaction.user.mention}."
            )
        )

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="ticket:close"
    )
    async def close(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild or not isinstance(
            interaction.user, discord.Member
        ):
            return await interaction.response.send_message(
                "This button can only be used inside a server.",
                ephemeral=True
            )

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute(
                """
                SELECT user_id, guild_id, closed
                FROM tickets
                WHERE channel_id = ?
                """,
                (interaction.channel.id,)
            ) as cursor:
                ticket = await cursor.fetchone()

        if not ticket:
            return await interaction.response.send_message(
                "❌ This channel isn't registered as a ticket.",
                ephemeral=True
            )

        owner_id, guild_id, closed = ticket

        if closed:
            return await interaction.response.send_message(
                "This ticket is already closed.",
                ephemeral=True
            )

        config_data = await get_config(interaction.guild.id)
        staff_role = (
            interaction.guild.get_role(config_data[5])
            if config_data and len(config_data) > 5 and config_data[5]
            else None
        )

        is_owner = interaction.user.id == owner_id
        is_staff = is_ticket_staff(interaction.user, staff_role)

        if not is_owner and not is_staff:
            return await interaction.response.send_message(
                "❌ Only the ticket owner or authorised staff can close this ticket.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "🔒 Closing this ticket in 3 seconds..."
        )

        await asyncio.sleep(3)

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                """
                UPDATE tickets
                SET closed = 1
                WHERE channel_id = ? AND guild_id = ?
                """,
                (interaction.channel.id, guild_id)
            )
            await db.commit()

        try:
            await interaction.channel.delete(
                reason=f"Ticket closed by {interaction.user}"
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I couldn't delete this ticket channel. "
                "Please check my Manage Channels permission.",
                ephemeral=True
            )
        except discord.NotFound:
            pass


async def setup(bot):
    await bot.add_cog(Tickets(bot))
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())
