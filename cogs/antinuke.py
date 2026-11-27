import discord
from discord import app_commands
from discord.ext import commands
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import asyncio
import config
from utils.embeds import create_embed

class AntiNuke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Trackers
        self.join_tracker = defaultdict(list)       # guild_id: [timestamps]
        self.ban_tracker = defaultdict(list)        # guild_id: [timestamps]
        self.channel_delete_tracker = defaultdict(list)
        self.role_delete_tracker = defaultdict(list)

        # Thresholds (you can adjust these)
        self.JOIN_THRESHOLD = 8          # joins
        self.JOIN_TIMEFRAME = 12         # seconds
        self.BAN_THRESHOLD = 4
        self.BAN_TIMEFRAME = 15
        self.CHANNEL_DELETE_THRESHOLD = 3
        self.CHANNEL_TIMEFRAME = 15
        self.ROLE_DELETE_THRESHOLD = 3
        self.ROLE_TIMEFRAME = 15

        self.locked_guilds = set()       # guilds currently in lockdown

    # ==================== ANTI RAID (JOINS) ====================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        now = datetime.now(timezone.utc).timestamp()

        self.join_tracker[guild.id] = [
            t for t in self.join_tracker[guild.id] if now - t < self.JOIN_TIMEFRAME
        ]
        self.join_tracker[guild.id].append(now)

        if len(self.join_tracker[guild.id]) >= self.JOIN_THRESHOLD:
            await self.trigger_lockdown(guild, reason="Possible Raid detected (mass joins)")

    # ==================== MASS BAN PROTECTION ====================
    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        now = datetime.now(timezone.utc).timestamp()

        self.ban_tracker[guild.id] = [
            t for t in self.ban_tracker[guild.id] if now - t < self.BAN_TIMEFRAME
        ]
        self.ban_tracker[guild.id].append(now)

        if len(self.ban_tracker[guild.id]) >= self.BAN_THRESHOLD:
            await self.trigger_lockdown(guild, reason="Mass ban detected")

    # ==================== MASS CHANNEL DELETE ====================
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        now = datetime.now(timezone.utc).timestamp()

        self.channel_delete_tracker[guild.id] = [
            t for t in self.channel_delete_tracker[guild.id] if now - t < self.CHANNEL_TIMEFRAME
        ]
        self.channel_delete_tracker[guild.id].append(now)

        if len(self.channel_delete_tracker[guild.id]) >= self.CHANNEL_DELETE_THRESHOLD:
            await self.trigger_lockdown(guild, reason="Mass channel deletion detected")

    # ==================== MASS ROLE DELETE ====================
    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        now = datetime.now(timezone.utc).timestamp()

        self.role_delete_tracker[guild.id] = [
            t for t in self.role_delete_tracker[guild.id] if now - t < self.ROLE_TIMEFRAME
        ]
        self.role_delete_tracker[guild.id].append(now)

        if len(self.role_delete_tracker[guild.id]) >= self.ROLE_DELETE_THRESHOLD:
            await self.trigger_lockdown(guild, reason="Mass role deletion detected")

    # ==================== LOCKDOWN SYSTEM ====================
    async def trigger_lockdown(self, guild: discord.Guild, reason: str):
        if guild.id in self.locked_guilds:
            return

        self.locked_guilds.add(guild.id)

        # Try to lock @everyone from sending messages
        everyone = guild.default_role
        try:
            await everyone.edit(
                permissions=discord.Permissions(send_messages=False, connect=False),
                reason=f"Anti-Nuke Lockdown: {reason}"
            )
        except:
            pass

        # Send alert to log channel or system channel
        embed = create_embed(
            "🚨 ANTI-NUKE TRIGGERED",
            f"**Reason:** {reason}\n\n"
            f"The server has been temporarily locked down.\n"
            f"Use `/unlock` to restore normal permissions.",
            config.COLOR_ERROR
        )

        # Try to send to system channel or first text channel
        channel = guild.system_channel
        if not channel:
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break

        if channel:
            try:
                await channel.send(embed=embed)
            except:
                pass

        # Auto unlock after 10 minutes
        await asyncio.sleep(600)
        if guild.id in self.locked_guilds:
            await self.unlock_server(guild)

    async def unlock_server(self, guild: discord.Guild):
        if guild.id not in self.locked_guilds:
            return

        everyone = guild.default_role
        try:
            # Restore basic permissions
            await everyone.edit(
                permissions=discord.Permissions(send_messages=True, connect=True, read_messages=True),
                reason="Anti-Nuke: Automatic unlock"
            )
        except:
            pass

        self.locked_guilds.discard(guild.id)

    # ==================== COMMANDS ====================
    @app_commands.command(name="lockdown", description="Manually lockdown the server")
    @app_commands.checks.has_permissions(administrator=True)
    async def lockdown(self, interaction: discord.Interaction):
        await self.trigger_lockdown(interaction.guild, reason=f"Manual lockdown by {interaction.user}")
        await interaction.response.send_message(
            embed=create_embed("🔒 Server Locked", "The server has been locked down.", config.COLOR_ERROR)
        )

    @app_commands.command(name="unlock", description="Unlock the server after lockdown")
    @app_commands.checks.has_permissions(administrator=True)
    async def unlock(self, interaction: discord.Interaction):
        await self.unlock_server(interaction.guild)
        await interaction.response.send_message(
            embed=create_embed("🔓 Server Unlocked", "The server has been unlocked.", config.COLOR_SUCCESS)
        )

async def setup(bot):
    await bot.add_cog(AntiNuke(bot))