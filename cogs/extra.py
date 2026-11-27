import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
from datetime import datetime, timezone
import config
from utils.embeds import create_embed

class Extra(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.snipes = {}          # {channel_id: message}
        self.afk_users = {}       # {user_id: reason}

    # -------------------- AFK System --------------------
    @app_commands.command(name="afk", description="Set yourself as AFK")
    @app_commands.describe(reason="Reason for being AFK")
    async def afk(self, interaction: discord.Interaction, reason: str = "AFK"):
        self.afk_users[interaction.user.id] = reason
        await interaction.response.send_message(
            embed=create_embed("💤 AFK Set", f"You are now AFK: **{reason}**\nI'll notify people who ping you.")
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # Remove AFK when user sends a message
        if message.author.id in self.afk_users:
            del self.afk_users[message.author.id]
            try:
                await message.channel.send(
                    embed=create_embed("👋 Welcome back!", f"{message.author.mention} is no longer AFK."),
                    delete_after=6
                )
            except:
                pass

        # Notify if someone pings an AFK user
        for user in message.mentions:
            if user.id in self.afk_users:
                reason = self.afk_users[user.id]
                try:
                    await message.channel.send(
                        embed=create_embed("💤 User is AFK", f"{user.display_name} is currently AFK: **{reason}**"),
                        delete_after=8
                    )
                except:
                    pass

    # -------------------- Snipe System --------------------
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        self.snipes[message.channel.id] = message

    @app_commands.command(name="snipe", description="Show the last deleted message in this channel")
    async def snipe(self, interaction: discord.Interaction):
        message = self.snipes.get(interaction.channel.id)

        if not message:
            return await interaction.response.send_message(
                embed=create_embed("Snipe", "There's nothing to snipe in this channel."),
                ephemeral=True
            )

        embed = create_embed(
            f"🔍 Sniped Message",
            message.content or "*No text content*",
            config.COLOR_INFO
        )
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.set_footer(text=f"Deleted in #{message.channel.name}")
        embed.timestamp = message.created_at

        await interaction.response.send_message(embed=embed)

    # -------------------- Invites Command --------------------
    @app_commands.command(name="invites", description="Check how many people someone has invited")
    async def invites(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM invite_joins WHERE guild_id = ? AND inviter_id = ?",
                (interaction.guild.id, member.id)
            ) as cursor:
                count = (await cursor.fetchone())[0]

        embed = create_embed("📨 Invites", f"{member.mention} has invited **{count}** members.")
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Extra(bot))