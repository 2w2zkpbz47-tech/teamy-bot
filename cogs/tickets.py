
import asyncio
from datetime import datetime, timezone

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput

import config
from utils.embeds import create_embed
from utils.database import get_config


async def is_ticket_staff(member):
    if (
        member.guild_permissions.administrator
        or member.guild_permissions.manage_channels
        or member.guild_permissions.moderate_members
    ):
        return True

    guild_config = await get_config(member.guild.id)
    if guild_config and guild_config[5]:
        role = member.guild.get_role(guild_config[5])
        if role and role in member.roles:
            return True

    return False


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="setup-tickets",
        description="Post the Ticket and Appeal panel."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tickets(self, interaction: discord.Interaction):
        embed = create_embed(
            "🎫 Support & Ban Appeals",
            "Need help, want to report a player, or appeal a punishment?\n\n"
            "Choose the button that matches your request."
        )

        await interaction.channel.send(
            embed=embed,
            view=TicketPanelView()
        )

        await interaction.response.send_message(
            "✅ Ticket panel posted!",
            ephemeral=True
        )


class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Support",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="ticket:support"
    )
    async def support(self, interaction, button):
        await create_ticket(interaction, "Support")

    @discord.ui.button(
        label="Report Player",
        style=discord.ButtonStyle.danger,
        emoji="🚨",
        custom_id="ticket:report"
    )
    async def report(self, interaction, button):
        await create_ticket(interaction, "Report")

    @discord.ui.button(
        label="Ban Appeal",
        style=discord.ButtonStyle.secondary,
        emoji="🔄",
        custom_id="ticket:appeal"
    )
    async def appeal(self, interaction, button):
        await interaction.response.send_modal(AppealModal())

    @discord.ui.button(
        label="Other",
        style=discord.ButtonStyle.secondary,
        emoji="❓",
        custom_id="ticket:other"
    )
    async def other(self, interaction, button):
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

    async def on_submit(self, interaction):
        await create_ticket(
            interaction,
            "Ban Appeal",
            appeal_data={
                "reason": self.reason.value,
                "why": self.why_unban.value,
                "changes": self.changes.value
            }
        )


async def create_ticket(interaction, category, appeal_data=None):
    guild = interaction.guild

    if guild is None:
        return await interaction.response.send_message(
            "Tickets can only be created inside a server.",
            ephemeral=True
        )

    guild_config = await get_config(guild.id)

    async with aiosqlite.connect(config.DATABASE) as db:
        async with db.execute("""
            SELECT channel_id
            FROM tickets
            WHERE guild_id = ? AND user_id = ? AND closed = 0
        """, (guild.id, interaction.user.id)) as cursor:
            existing = await cursor.fetchone()

    if existing:
        existing_channel = guild.get_channel(existing[0])

        if existing_channel:
            return await interaction.response.send_message(
                f"You already have an open ticket: {existing_channel.mention}",
                ephemeral=True
            )

        # The old channel no longer exists. Mark its record closed.
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                UPDATE tickets SET closed = 1
                WHERE channel_id = ?
            """, (existing[0],))
            await db.commit()

    bot_member = guild.me
    if bot_member is None:
        bot_member = guild.get_member(interaction.client.user.id)

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
            manage_channels=True,
            manage_messages=True,
            read_message_history=True
        )
    }

    if guild_config and guild_config[5]:
        staff_role = guild.get_role(guild_config[5])
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

    category_channel = None
    if guild_config and guild_config[6]:
        category_channel = guild.get_channel(guild_config[6])

    channel = await guild.create_text_channel(
        name=f"ticket-{interaction.user.name[:18]}",
        overwrites=overwrites,
        category=category_channel,
        topic=f"{category} ticket for {interaction.user} ({interaction.user.id})"
    )

    async with aiosqlite.connect(config.DATABASE) as db:
        await db.execute("""
            INSERT INTO tickets
            (channel_id, guild_id, user_id, category, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            channel.id,
            guild.id,
            interaction.user.id,
            category,
            datetime.now(timezone.utc).timestamp()
        ))
        await db.commit()

    embed = create_embed(
        f"🎫 Ticket Opened — {category}",
        f"Hello {interaction.user.mention}!\n"
        "A staff member will be with you as soon as possible.\n\n"
        f"**Category:** {category}",
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
        f"✅ Your ticket has been created: {channel.mention}",
        ephemeral=True
    )


class TicketControlView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Claim",
        style=discord.ButtonStyle.primary,
        emoji="✋",
        custom_id="ticket:claim"
    )
    async def claim(self, interaction, button):
        if not await is_ticket_staff(interaction.user):
            return await interaction.response.send_message(
                "Only authorised staff can claim tickets.",
                ephemeral=True
            )

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT claimed_by, closed
                FROM tickets
                WHERE channel_id = ? AND guild_id = ?
            """, (
                interaction.channel.id,
                interaction.guild.id
            )) as cursor:
                row = await cursor.fetchone()

            if not row:
                return await interaction.response.send_message(
                    "This ticket could not be found in the database.",
                    ephemeral=True
                )

            claimed_by, closed = row

            if closed:
                return await interaction.response.send_message(
                    "This ticket is already closed.",
                    ephemeral=True
                )

            if claimed_by:
                return await interaction.response.send_message(
                    f"This ticket has already been claimed by <@{claimed_by}>.",
                    ephemeral=True
                )

            await db.execute("""
                UPDATE tickets
                SET claimed_by = ?
                WHERE channel_id = ?
                AND guild_id = ?
                AND claimed_by IS NULL
                AND closed = 0
            """, (
                interaction.user.id,
                interaction.channel.id,
                interaction.guild.id
            ))
            await db.commit()

            async with db.execute("""
                SELECT claimed_by
                FROM tickets
                WHERE channel_id = ?
            """, (interaction.channel.id,)) as cursor:
                updated = await cursor.fetchone()

        if not updated or updated[0] != interaction.user.id:
            return await interaction.response.send_message(
                "Another staff member claimed this ticket first.",
                ephemeral=True
            )

        await interaction.response.send_message(
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
    async def close(self, interaction, button):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT user_id, closed
                FROM tickets
                WHERE channel_id = ? AND guild_id = ?
            """, (
                interaction.channel.id,
                interaction.guild.id
            )) as cursor:
                row = await cursor.fetchone()

        if not row:
            return await interaction.response.send_message(
                "This ticket could not be found.",
                ephemeral=True
            )

        owner_id, closed = row

        if closed:
            return await interaction.response.send_message(
                "This ticket is already closed.",
                ephemeral=True
            )

        staff = await is_ticket_staff(interaction.user)

        if interaction.user.id != owner_id and not staff:
            return await interaction.response.send_message(
                "Only the ticket creator or authorised staff can close this ticket.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "🔒 Closing this ticket in 3 seconds..."
        )

        await asyncio.sleep(3)

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                UPDATE tickets
                SET closed = 1
                WHERE channel_id = ?
            """, (interaction.channel.id,))
            await db.commit()

        try:
            await interaction.channel.delete(
                reason=f"Ticket closed by {interaction.user}"
            )
        except discord.Forbidden:
            try:
                await interaction.channel.send(
                    "I couldn't delete this channel. Please check my permissions."
                )
            except discord.HTTPException:
                pass


async def setup(bot):
    await bot.add_cog(Tickets(bot))
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())
