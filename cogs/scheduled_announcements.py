
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config


UK_TIMEZONE = ZoneInfo("Europe/London")


class ScheduledAnnouncements(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    creator_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    send_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at REAL NOT NULL
                )
            """)

            # Retry announcements that were interrupted by a restart.
            await db.execute("""
                UPDATE scheduled_announcements
                SET status = 'pending'
                WHERE status = 'sending'
            """)

            await db.commit()

        self.dispatch_announcements.start()

    def cog_unload(self):
        self.dispatch_announcements.cancel()

    announcement = app_commands.Group(
        name="announcement",
        description="Schedule and manage server announcements."
    )

    @announcement.command(
        name="schedule",
        description="Schedule an announcement for a future time."
    )
    @app_commands.describe(
        channel="The channel where the announcement will be posted.",
        when="UK time, using YYYY-MM-DD HH:MM.",
        message="The announcement message."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def schedule(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        when: str,
        message: str
    ):
        if channel.guild.id != interaction.guild_id:
            await interaction.response.send_message(
                "That channel must be in this server.",
                ephemeral=True
            )
            return

        if len(message) > 2000:
            await interaction.response.send_message(
                "Your announcement must be 2,000 characters or fewer.",
                ephemeral=True
            )
            return

        try:
            scheduled_time = datetime.strptime(
                when, "%Y-%m-%d %H:%M"
            ).replace(tzinfo=UK_TIMEZONE)
        except ValueError:
            await interaction.response.send_message(
                "Invalid date or time. Use `YYYY-MM-DD HH:MM`, "
                "for example `2026-12-01 18:30`.",
                ephemeral=True
            )
            return

        if scheduled_time <= datetime.now(UK_TIMEZONE):
            await interaction.response.send_message(
                "The scheduled time must be in the future.",
                ephemeral=True
            )
            return

        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute("""
                INSERT INTO scheduled_announcements (
                    guild_id,
                    channel_id,
                    creator_id,
                    content,
                    send_at,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """, (
                interaction.guild_id,
                channel.id,
                interaction.user.id,
                message,
                scheduled_time.timestamp(),
                datetime.now(timezone.utc).timestamp()
            ))

            announcement_id = cursor.lastrowid
            await db.commit()

        await interaction.response.send_message(
            f"Announcement **#{announcement_id}** scheduled for "
            f"**{scheduled_time.strftime('%d %B %Y at %H:%M')} UK time** "
            f"in {channel.mention}.",
            ephemeral=True
        )

    @announcement.command(
        name="list",
        description="View upcoming scheduled announcements."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def list_announcements(
        self,
        interaction: discord.Interaction
    ):
        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute("""
                SELECT id, channel_id, content, send_at
                FROM scheduled_announcements
                WHERE guild_id = ? AND status = 'pending'
                ORDER BY send_at ASC
                LIMIT 15
            """, (interaction.guild_id,))

            rows = await cursor.fetchall()

        if not rows:
            await interaction.response.send_message(
                "There are no upcoming scheduled announcements.",
                ephemeral=True
            )
            return

        lines = []

        for announcement_id, channel_id, content, send_at in rows:
            scheduled_time = datetime.fromtimestamp(
                send_at, UK_TIMEZONE
            )

            preview = content.replace("\n", " ")[:65]

            lines.append(
                f"**#{announcement_id}** — "
                f"{scheduled_time.strftime('%d/%m/%Y %H:%M')} UK time\n"
                f"<#{channel_id}> — {preview}"
            )

        await interaction.response.send_message(
            "**Upcoming announcements**\n\n" + "\n\n".join(lines),
            ephemeral=True
        )

    @announcement.command(
        name="cancel",
        description="Cancel a scheduled announcement."
    )
    @app_commands.describe(
        announcement_id="The ID shown in /announcement list."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cancel(
        self,
        interaction: discord.Interaction,
        announcement_id: int
    ):
        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute("""
                UPDATE scheduled_announcements
                SET status = 'cancelled'
                WHERE id = ?
                AND guild_id = ?
                AND status = 'pending'
            """, (announcement_id, interaction.guild_id))

            await db.commit()

        if cursor.rowcount == 0:
            await interaction.response.send_message(
                "I couldn't find a pending announcement with that ID.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"Announcement **#{announcement_id}** has been cancelled.",
            ephemeral=True
        )

    @tasks.loop(seconds=30)
    async def dispatch_announcements(self):
        now = datetime.now(timezone.utc).timestamp()

        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute("""
                SELECT id, guild_id, channel_id, content
                FROM scheduled_announcements
                WHERE status = 'pending' AND send_at <= ?
                ORDER BY send_at ASC
                LIMIT 10
            """, (now,))

            due_announcements = await cursor.fetchall()

        for announcement_id, guild_id, channel_id, content in due_announcements:
            # Claim the announcement so it cannot be processed twice
            # by overlapping loop iterations.
            async with aiosqlite.connect(config.DATABASE) as db:
                cursor = await db.execute("""
                    UPDATE scheduled_announcements
                    SET status = 'sending'
                    WHERE id = ? AND status = 'pending'
                """, (announcement_id,))

                await db.commit()

                if cursor.rowcount == 0:
                    continue

            try:
                channel = self.bot.get_channel(channel_id)

                if channel is None:
                    channel = await self.bot.fetch_channel(channel_id)

                if not isinstance(channel, discord.TextChannel):
                    raise ValueError("The saved channel is not a text channel.")

                await channel.send(
                    content,
                    allowed_mentions=discord.AllowedMentions.none()
                )

                new_status = "sent"

            except (discord.Forbidden, discord.NotFound, discord.HTTPException, ValueError) as error:
                print(
                    f"Scheduled announcement #{announcement_id} failed: {error}"
                )
                new_status = "failed"

            except Exception as error:
                print(
                    f"Unexpected error sending announcement #{announcement_id}: {error}"
                )
                new_status = "failed"

            async with aiosqlite.connect(config.DATABASE) as db:
                await db.execute("""
                    UPDATE scheduled_announcements
                    SET status = ?
                    WHERE id = ?
                """, (new_status, announcement_id))

                await db.commit()

    @dispatch_announcements.before_loop
    async def before_dispatch(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ScheduledAnnouncements(bot))
