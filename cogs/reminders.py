import re
from datetime import datetime, timedelta, timezone

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from utils.embeds import create_embed


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        # Create the table BEFORE starting the background task.
        # Previously the task started in __init__, so it could query
        # reminders before the /remind command had ever created the table.
        await self.ensure_reminders_table()
        self.check_reminders.start()

    def cog_unload(self):
        if self.check_reminders.is_running():
            self.check_reminders.cancel()

    async def ensure_reminders_table(self):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER,
                    guild_id INTEGER,
                    reminder TEXT NOT NULL,
                    remind_at REAL NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            await db.commit()

    @staticmethod
    def parse_time(time_str: str):
        """Parse durations such as 30s, 10m, 1h, 2d or 1w."""
        units = {
            "s": 1,
            "m": 60,
            "h": 3600,
            "d": 86400,
            "w": 604800,
        }
        match = re.fullmatch(r"\s*(\d+)\s*([smhdw])\s*", time_str.lower())
        if not match:
            return None

        amount, unit = match.groups()
        seconds = int(amount) * units[unit]
        return seconds if seconds > 0 else None

    @app_commands.command(name="remind", description="Set a reminder")
    @app_commands.describe(
        time="When to remind you (e.g. 10m, 1h, 2d)",
        reminder="What to remind you about"
    )
    async def remind(
        self,
        interaction: discord.Interaction,
        time: str,
        reminder: str
    ):
        seconds = self.parse_time(time)

        if seconds is None or seconds < 30:
            return await interaction.response.send_message(
                "Invalid time. Use formats like `30s`, `10m`, `1h`, or `2d`. "
                "The minimum is 30 seconds.",
                ephemeral=True
            )

        if seconds > 365 * 24 * 60 * 60:
            return await interaction.response.send_message(
                "Reminders cannot be set more than one year ahead.",
                ephemeral=True
            )

        if not reminder.strip():
            return await interaction.response.send_message(
                "Please tell me what you want to be reminded about.",
                ephemeral=True
            )

        now = datetime.now(timezone.utc)
        remind_at = now + timedelta(seconds=seconds)

        # Reminders can also be created in DMs; guild_id is nullable.
        guild_id = interaction.guild.id if interaction.guild else None
        channel_id = interaction.channel_id

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT INTO reminders
                (user_id, channel_id, guild_id, reminder, remind_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                interaction.user.id,
                channel_id,
                guild_id,
                reminder.strip(),
                remind_at.timestamp(),
                now.timestamp()
            ))
            await db.commit()

        embed = create_embed(
            "â° Reminder Set",
            f"I will remind you <t:{int(remind_at.timestamp())}:R>:\n\n"
            f"**{discord.utils.escape_markdown(reminder.strip())}**"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tasks.loop(seconds=30)
    async def check_reminders(self):
        now = datetime.now(timezone.utc).timestamp()

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT id, user_id, channel_id, reminder
                FROM reminders
                WHERE remind_at <= ?
                ORDER BY remind_at ASC
            """, (now,)) as cursor:
                rows = await cursor.fetchall()

            for reminder_id, user_id, channel_id, reminder_text in rows:
                delivered = False

                channel = self.bot.get_channel(channel_id) if channel_id else None

                if channel is None and channel_id:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        channel = None

                try:
                    if channel is not None:
                        await channel.send(
                            content=f"<@{user_id}>",
                            embed=create_embed("â° Reminder", reminder_text),
                            allowed_mentions=discord.AllowedMentions(
                                users=True,
                                roles=False,
                                everyone=False
                            )
                        )
                        delivered = True
                    else:
                        user = self.bot.get_user(user_id)
                        if user is None:
                            user = await self.bot.fetch_user(user_id)

                        await user.send(
                            embed=create_embed("â° Reminder", reminder_text)
                        )
                        delivered = True

                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    # Keep the reminder in the database if delivery failed,
                    # so a temporary Discord/API issue does not erase it.
                    delivered = False

                if delivered:
                    await db.execute(
                        "DELETE FROM reminders WHERE id = ?",
                        (reminder_id,)
                    )

            await db.commit()

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Reminders(bot))