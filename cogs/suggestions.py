import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
from datetime import datetime, timezone
import config
from utils.embeds import create_embed
from utils.database import get_config

class Suggestions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="suggest", description="Submit a suggestion")
    @app_commands.describe(suggestion="Your suggestion")
    async def suggest(self, interaction: discord.Interaction, suggestion: str):
        config_data = await get_config(interaction.guild.id)
        channel_id = config_data[7] if config_data and len(config_data) > 7 else None  # suggestion_channel

        channel = interaction.guild.get_channel(channel_id) if channel_id else interaction.channel

        embed = create_embed("💡 New Suggestion", suggestion)
        embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"User ID: {interaction.user.id}")

        msg = await channel.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                "INSERT INTO suggestions (guild_id, user_id, content, message_id, status) VALUES (?, ?, ?, ?, ?)",
                (interaction.guild.id, interaction.user.id, suggestion, msg.id, "pending")
            )
            await db.commit()

        await interaction.response.send_message(
            embed=create_embed("✅ Suggestion Submitted", f"Your suggestion has been posted in {channel.mention}"),
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Suggestions(bot))