import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import random
from datetime import datetime, timezone
import config
from utils.embeds import create_embed

class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="rank", description="Check your rank or another member's rank")
    @app_commands.describe(member="The member to check")
    async def rank(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute(
                "SELECT xp, level, messages, voice_time FROM levels WHERE guild_id = ? AND user_id = ?",
                (interaction.guild.id, member.id)
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return await interaction.response.send_message(
                embed=create_embed("Rank", f"{member.mention} hasn't earned any XP yet.")
            )

        xp, level, messages, voice_time = row

        embed = create_embed(f"📊 Rank — {member.display_name}", color=config.COLOR_LEVEL)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="XP", value=str(xp), inline=True)
        embed.add_field(name="Messages", value=str(messages), inline=True)
        embed.add_field(name="Voice Time", value=f"{voice_time // 60} minutes", inline=True)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="View the XP leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute(
                "SELECT user_id, xp, level FROM levels WHERE guild_id = ? ORDER BY xp DESC LIMIT 10",
                (interaction.guild.id,)
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return await interaction.response.send_message(embed=create_embed("Leaderboard", "No data yet."))

        description = ""
        for i, (user_id, xp, level) in enumerate(rows, start=1):
            description += f"**#{i}** <@{user_id}> — Level **{level}** ({xp} XP)\n"

        embed = create_embed("🏆 XP Leaderboard", description, config.COLOR_LEVEL)
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Give XP
        if random.random() < 0.7:
            xp_gain = random.randint(15, 25)

            async with aiosqlite.connect(config.DATABASE) as db:
                await db.execute(
                    "INSERT OR IGNORE INTO levels (guild_id, user_id) VALUES (?, ?)",
                    (message.guild.id, message.author.id)
                )
                await db.execute(
                    "UPDATE levels SET messages = messages + 1, xp = xp + ? WHERE guild_id = ? AND user_id = ?",
                    (xp_gain, message.guild.id, message.author.id)
                )
                await db.commit()

                async with db.execute(
                    "SELECT xp, level FROM levels WHERE guild_id = ? AND user_id = ?",
                    (message.guild.id, message.author.id)
                ) as cursor:
                    xp, level = await cursor.fetchone()

                new_level = int((xp ** 0.5) / 8)

                if new_level > level:
                    await db.execute(
                        "UPDATE levels SET level = ? WHERE guild_id = ? AND user_id = ?",
                        (new_level, message.guild.id, message.author.id)
                    )
                    await db.commit()

                    try:
                        await message.channel.send(
                            embed=create_embed(
                                "🎉 Level Up!",
                                f"{message.author.mention} reached **Level {new_level}**!",
                                config.COLOR_LEVEL
                            ),
                            delete_after=12
                        )
                    except:
                        pass

async def setup(bot):
    await bot.add_cog(Leveling(bot))