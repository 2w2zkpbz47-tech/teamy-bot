import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiosqlite
import asyncio
from datetime import datetime, timedelta, timezone
import re
import config
from utils.embeds import create_embed

class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    def parse_time(self, time_str: str):
        """Parse time strings like 10m, 1h, 2d into seconds"""
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        match = re.match(r"(\d+)([smhdw])", time_str.lower())
        if not match:
            return None
        amount, unit = match.groups()
        return int(amount) * units[unit]

    @app_commands.command(name="remind", description="Set a reminder")
    @app_commands.describe(
        time="When to remind you (e.g. 10m, 1h, 2d)",
        reminder="What to remind you about"
    )
    async def remind(self, interaction: discord.Interaction, time: str, reminder: str):
        seconds = self.parse_time(time)
        if not seconds or seconds < 30:
            return await interaction.response.send_message(
                "Invalid time. Use formats like `10m`, `1h`, `2d`. Minimum 30 seconds.",
                ephemeral=True
            )

        remind_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    channel_id INTEGER,
                    guild_id INTEGER,
                    reminder TEXT,
                    remind_at REAL,
                    created_at REAL
                )
            """)
            await db.execute(
                "INSERT INTO reminders (user_id, channel_id, guild_id, reminder, remind_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (interaction.user.id, interaction.channel.id, interaction.guild.id, reminder, remind_at.timestamp(), datetime.now(timezone.utc).timestamp())
            )
            await db.commit()

        embed = create_embed(
            "⏰ Reminder Set",
            f"I will remind you <t:{int(remind_at.timestamp())}:R>:\n\n**{reminder}**"
        )
        await interaction.response.send_message(embed=embed)

    @tasks.loop(seconds=30)
    async def check_reminders(self):
        now = datetime.now(timezone.utc).timestamp()
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("SELECT id, user_id, channel_id, reminder FROM reminders WHERE remind_at <= ?", (now,)) as cursor:
                rows = await cursor.fetchall()

            for reminder_id, user_id, channel_id, reminder_text in rows:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        await channel.send(
                            content=f"<@{user_id}>",
                            embed=create_embed("⏰ Reminder", reminder_text)
                        )
                    except:
                        pass

                await db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            await db.commit()

async def setup(bot):
    await bot.add_cog(Reminders(bot))