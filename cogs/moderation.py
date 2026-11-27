import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import aiosqlite
import random
from datetime import datetime, timedelta, timezone
import config
from utils.embeds import create_embed
from utils.database import get_config

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------- Staff View Command ----------
    @app_commands.command(name="staff", description="Open staff management panel for a user")
    @app_commands.describe(user="The user you want to manage")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def staff(self, interaction: discord.Interaction, user: discord.Member):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, user.id)) as c:
                warn_count = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM staff_notes WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, user.id)) as c:
                note_count = (await c.fetchone())[0]

        embed = create_embed(f"🛡️ Staff Panel — {user.display_name}", color=config.COLOR_STAFF)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="ID", value=user.id, inline=True)
        embed.add_field(name="Joined", value=f"<t:{int(user.joined_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(user.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Warnings", value=str(warn_count), inline=True)
        embed.add_field(name="Staff Notes", value=str(note_count), inline=True)
        embed.add_field(name="Highest Role", value=user.top_role.mention, inline=True)

        if user.is_timed_out():
            embed.add_field(name="Timed Out Until", value=f"<t:{int(user.timed_out_until.timestamp())}:R>", inline=False)

        view = StaffPanelView(user)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ---------- Basic Mod Commands ----------
    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        case_id = await create_case(interaction.guild.id, member.id, interaction.user.id, "warn", reason)
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                "INSERT INTO warnings (case_id, guild_id, user_id, moderator_id, reason, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (case_id, interaction.guild.id, member.id, interaction.user.id, reason, datetime.now(timezone.utc).timestamp())
            )
            await db.commit()

        embed = create_embed("⚠️ Member Warned", f"**User:** {member.mention}\n**Moderator:** {interaction.user.mention}\n**Case ID:** `{case_id}`\n**Reason:** {reason}", config.COLOR_WARN)
        await interaction.response.send_message(embed=embed)
        await log_action(interaction.guild, f"⚠️ Warn | {case_id}", f"**User:** {member}\n**Mod:** {interaction.user}\n**Reason:** {reason}", config.COLOR_WARN)

    @app_commands.command(name="timeout", description="Timeout a member")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str = "No reason provided"):
        case_id = await create_case(interaction.guild.id, member.id, interaction.user.id, "timeout", reason)
        until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        await member.timeout(until, reason=f"[{case_id}] {reason}")

        embed = create_embed("⏳ Member Timed Out", f"**User:** {member.mention}\n**Duration:** {minutes} minutes\n**Case ID:** `{case_id}`\n**Reason:** {reason}", config.COLOR_WARN)
        await interaction.response.send_message(embed=embed)
        await log_action(interaction.guild, f"⏳ Timeout | {case_id}", f"**User:** {member}\n**Mod:** {interaction.user}\n**Duration:** {minutes}m\n**Reason:** {reason}", config.COLOR_WARN)

    @app_commands.command(name="kick", description="Kick a member")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        case_id = await create_case(interaction.guild.id, member.id, interaction.user.id, "kick", reason)
        await member.kick(reason=f"[{case_id}] {reason}")
        embed = create_embed("👢 Member Kicked", f"**User:** {member}\n**Case ID:** `{case_id}`\n**Reason:** {reason}", config.COLOR_ERROR)
        await interaction.response.send_message(embed=embed)
        await log_action(interaction.guild, f"👢 Kick | {case_id}", f"**User:** {member}\n**Mod:** {interaction.user}\n**Reason:** {reason}", config.COLOR_ERROR)

    @app_commands.command(name="ban", description="Ban a member")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        case_id = await create_case(interaction.guild.id, member.id, interaction.user.id, "ban", reason)
        await member.ban(reason=f"[{case_id}] {reason}")
        embed = create_embed("🔨 Member Banned", f"**User:** {member}\n**Case ID:** `{case_id}`\n**Reason:** {reason}", config.COLOR_ERROR)
        await interaction.response.send_message(embed=embed)
        await log_action(interaction.guild, f"🔨 Ban | {case_id}", f"**User:** {member}\n**Mod:** {interaction.user}\n**Reason:** {reason}", config.COLOR_ERROR)

async def setup(bot):
    await bot.add_cog(Moderation(bot))

# -------------------- Helpers --------------------

async def create_case(guild_id: int, user_id: int, mod_id: int, action: str, reason: str):
    case_id = f"TEA-{random.randint(10000, 99999)}"
    async with aiosqlite.connect(config.DATABASE) as db:
        await db.execute(
            "INSERT INTO cases (case_id, guild_id, user_id, moderator_id, action, reason, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (case_id, guild_id, user_id, mod_id, action, reason, datetime.now(timezone.utc).timestamp())
        )
        await db.commit()
    return case_id

async def log_action(guild: discord.Guild, title: str, description: str, color: int):
    config_data = await get_config(guild.id)
    if config_data and config_data[1]:  # log_channel
        channel = guild.get_channel(config_data[1])
        if channel:
            try:
                await channel.send(embed=create_embed(title, description, color))
            except:
                pass

# -------------------- Staff Panel View --------------------

class StaffPanelView(View):
    def __init__(self, target: discord.Member):
        super().__init__(timeout=180)
        self.target = target

    @discord.ui.button(label="Warn", style=discord.ButtonStyle.secondary, emoji="⚠️")
    async def warn_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.moderate_members:
            return await interaction.response.send_message("You don't have permission.", ephemeral=True)
        modal = ReasonModal("Warn User", self.target, "warn")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Timeout", style=discord.ButtonStyle.secondary, emoji="⏳")
    async def timeout_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.moderate_members:
            return await interaction.response.send_message("You don't have permission.", ephemeral=True)
        modal = TimeoutModal(self.target)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger, emoji="👢")
    async def kick_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.kick_members:
            return await interaction.response.send_message("Only Admins can kick.", ephemeral=True)
        modal = ReasonModal("Kick User", self.target, "kick")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Ban", style=discord.ButtonStyle.danger, emoji="🔨")
    async def ban_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message("Only Admins can ban.", ephemeral=True)
        modal = ReasonModal("Ban User", self.target, "ban")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Add Note", style=discord.ButtonStyle.primary, emoji="📝")
    async def note_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.moderate_members:
            return await interaction.response.send_message("You don't have permission.", ephemeral=True)
        modal = NoteModal(self.target)
        await interaction.response.send_modal(modal)

class ReasonModal(Modal):
    def __init__(self, title: str, target: discord.Member, action: str):
        super().__init__(title=title)
        self.target = target
        self.action = action
        self.reason = TextInput(label="Reason", style=discord.TextStyle.paragraph, required=True, max_length=500)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        reason = self.reason.value
        case_id = await create_case(interaction.guild.id, self.target.id, interaction.user.id, self.action, reason)

        if self.action == "warn":
            async with aiosqlite.connect(config.DATABASE) as db:
                await db.execute(
                    "INSERT INTO warnings (case_id, guild_id, user_id, moderator_id, reason, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                    (case_id, interaction.guild.id, self.target.id, interaction.user.id, reason, datetime.now(timezone.utc).timestamp())
                )
                await db.commit()
            await interaction.response.send_message(embed=create_embed("⚠️ Warned", f"{self.target.mention} has been warned.\n**Case:** `{case_id}`\n**Reason:** {reason}", config.COLOR_WARN))
            await log_action(interaction.guild, f"⚠️ Warn | {case_id}", f"**User:** {self.target}\n**Mod:** {interaction.user}\n**Reason:** {reason}", config.COLOR_WARN)

        elif self.action == "kick":
            await self.target.kick(reason=f"[{case_id}] {reason}")
            await interaction.response.send_message(embed=create_embed("👢 Kicked", f"{self.target} has been kicked.\n**Case:** `{case_id}`\n**Reason:** {reason}", config.COLOR_ERROR))
            await log_action(interaction.guild, f"👢 Kick | {case_id}", f"**User:** {self.target}\n**Mod:** {interaction.user}\n**Reason:** {reason}", config.COLOR_ERROR)

        elif self.action == "ban":
            await self.target.ban(reason=f"[{case_id}] {reason}")
            await interaction.response.send_message(embed=create_embed("🔨 Banned", f"{self.target} has been banned.\n**Case:** `{case_id}`\n**Reason:** {reason}", config.COLOR_ERROR))
            await log_action(interaction.guild, f"🔨 Ban | {case_id}", f"**User:** {self.target}\n**Mod:** {interaction.user}\n**Reason:** {reason}", config.COLOR_ERROR)

class TimeoutModal(Modal):
    def __init__(self, target: discord.Member):
        super().__init__(title=f"Timeout {target.display_name}")
        self.target = target
        self.minutes = TextInput(label="Duration (minutes)", placeholder="Example: 60", required=True)
        self.reason = TextInput(label="Reason", style=discord.TextStyle.paragraph, required=True)
        self.add_item(self.minutes)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            mins = int(self.minutes.value)
            if mins < 1 or mins > 40320:
                raise ValueError
        except:
            return await interaction.response.send_message("Please enter a valid number of minutes (1-40320).", ephemeral=True)

        reason = self.reason.value
        case_id = await create_case(interaction.guild.id, self.target.id, interaction.user.id, "timeout", reason)
        until = datetime.now(timezone.utc) + timedelta(minutes=mins)
        await self.target.timeout(until, reason=f"[{case_id}] {reason}")

        await interaction.response.send_message(
            embed=create_embed("⏳ Timed Out", f"{self.target.mention} has been timed out for **{mins} minutes**.\n**Case:** `{case_id}`\n**Reason:** {reason}", config.COLOR_WARN)
        )
        await log_action(interaction.guild, f"⏳ Timeout | {case_id}", f"**User:** {self.target}\n**Mod:** {interaction.user}\n**Duration:** {mins}m\n**Reason:** {reason}", config.COLOR_WARN)

class NoteModal(Modal):
    def __init__(self, target: discord.Member):
        super().__init__(title=f"Add Note for {target.display_name}")
        self.target = target
        self.note = TextInput(label="Staff Note", style=discord.TextStyle.paragraph, required=True, max_length=1000)
        self.add_item(self.note)

    async def on_submit(self, interaction: discord.Interaction):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                "INSERT INTO staff_notes (guild_id, user_id, moderator_id, note, timestamp) VALUES (?, ?, ?, ?, ?)",
                (interaction.guild.id, self.target.id, interaction.user.id, self.note.value, datetime.now(timezone.utc).timestamp())
            )
            await db.commit()
        await interaction.response.send_message(embed=create_embed("📝 Note Added", f"Staff note added for {self.target.mention}.", config.COLOR_SUCCESS), ephemeral=True)