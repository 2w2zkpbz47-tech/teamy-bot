import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import aiosqlite
from datetime import datetime, timezone
import config
from utils.embeds import create_embed
from utils.database import get_config

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup-tickets", description="Post the Ticket & Appeal panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tickets(self, interaction: discord.Interaction):
        embed = create_embed(
            "🎫 Support & Ban Appeals",
            "Need help? Want to report a player? Or appeal a punishment?\n\n"
            "Click the button that matches your request below."
        )
        await interaction.channel.send(embed=embed, view=TicketPanelView())
        await interaction.response.send_message("✅ Ticket panel posted!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Tickets(bot))
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())

# -------------------- Ticket Panel --------------------

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Support", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="ticket:support")
    async def support(self, interaction: discord.Interaction, button: Button):
        await create_ticket(interaction, "Support")

    @discord.ui.button(label="Report Player", style=discord.ButtonStyle.danger, emoji="🚨", custom_id="ticket:report")
    async def report(self, interaction: discord.Interaction, button: Button):
        await create_ticket(interaction, "Report")

    @discord.ui.button(label="Ban Appeal", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="ticket:appeal")
    async def appeal(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(AppealModal())

    @discord.ui.button(label="Other", style=discord.ButtonStyle.secondary, emoji="❓", custom_id="ticket:other")
    async def other(self, interaction: discord.Interaction, button: Button):
        await create_ticket(interaction, "Other")

class AppealModal(Modal, title="Ban Appeal Form"):
    reason = TextInput(label="Why were you banned?", style=discord.TextStyle.paragraph, required=True, max_length=800)
    why_unban = TextInput(label="Why should we unban you?", style=discord.TextStyle.paragraph, required=True, max_length=800)
    changes = TextInput(label="What will you do differently?", style=discord.TextStyle.paragraph, required=True, max_length=800)

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

async def create_ticket(interaction: discord.Interaction, category: str, appeal_data: dict = None):
    guild = interaction.guild
    config_data = await get_config(guild.id)

    # Prevent multiple open tickets
    async with aiosqlite.connect(config.DATABASE) as db:
        async with db.execute("SELECT channel_id FROM tickets WHERE guild_id = ? AND user_id = ? AND closed = 0", (guild.id, interaction.user.id)) as cursor:
            if await cursor.fetchone():
                return await interaction.response.send_message("You already have an open ticket.", ephemeral=True)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True, manage_messages=True)
    }

    # Add staff role if set
    if config_data and config_data[5]:
        staff_role = guild.get_role(config_data[5])
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    category_channel = guild.get_channel(config_data[6]) if config_data and config_data[6] else None

    channel = await guild.create_text_channel(
        name=f"ticket-{interaction.user.name[:18]}",
        overwrites=overwrites,
        category=category_channel,
        topic=f"{category} ticket for {interaction.user} ({interaction.user.id})"
    )

    async with aiosqlite.connect(config.DATABASE) as db:
        await db.execute(
            "INSERT INTO tickets (channel_id, guild_id, user_id, category, created_at) VALUES (?, ?, ?, ?, ?)",
            (channel.id, guild.id, interaction.user.id, category, datetime.now(timezone.utc).timestamp())
        )
        await db.commit()

    embed = create_embed(
        f"🎫 Ticket Opened — {category}",
        f"Hello {interaction.user.mention}!\nA staff member will be with you as soon as possible.\n\n**Category:** {category}",
        config.COLOR_TICKET
    )

    if appeal_data:
        embed.add_field(name="Why were you banned?", value=appeal_data["reason"][:300], inline=False)
        embed.add_field(name="Why should we unban you?", value=appeal_data["why"][:300], inline=False)
        embed.add_field(name="What will you do differently?", value=appeal_data["changes"][:300], inline=False)

    await channel.send(content=f"{interaction.user.mention}", embed=embed, view=TicketControlView())
    await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

class TicketControlView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.primary, emoji="✋", custom_id="ticket:claim")
    async def claim(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.moderate_members:
            return await interaction.response.send_message("Only staff can claim tickets.", ephemeral=True)

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("UPDATE tickets SET claimed_by = ? WHERE channel_id = ?", (interaction.user.id, interaction.channel.id))
            await db.commit()

        await interaction.response.send_message(embed=create_embed("✅ Ticket Claimed", f"This ticket has been claimed by {interaction.user.mention}."))

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close")
    async def close(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Closing ticket in 3 seconds...")
        await discord.utils.sleep_until(discord.utils.utcnow() + discord.utils.timedelta(seconds=3))

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("UPDATE tickets SET closed = 1 WHERE channel_id = ?", (interaction.channel.id,))
            await db.commit()

        try:
            await interaction.channel.delete()
        except:
            pass