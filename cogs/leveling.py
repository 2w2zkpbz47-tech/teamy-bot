
import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiosqlite
import random
import config
import math
import time


def calculate_level(xp: int) -> int:
    return int(math.sqrt(max(0, xp)) / 8)


def xp_for_next_level(level: int) -> int:
    return ((level + 1) * 8) ** 2


def voice_eligible(member: discord.Member) -> bool:
    if member.bot or member.voice is None:
        return False

    voice = member.voice

    return not (
        voice.afk
        or voice.self_deaf
        or voice.deaf
        or voice.self_mute
        or voice.mute
    )


class Leveling(commands.Cog):
    leaderboard_group = app_commands.Group(
        name="leaderboard",
        description="Teamy server leaderboards"
    )

    def __init__(self, bot):
        self.bot = bot
        self.message_cooldowns = {}
        self.voice_sessions = {}

    async def cog_load(self):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS member_stats (
                    guild_id INTEGER,
                    user_id INTEGER,
                    teams_created INTEGER DEFAULT 0,
                    teams_joined INTEGER DEFAULT 0,
                    tickets_handled INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS voice_levels (
                    guild_id INTEGER,
                    user_id INTEGER,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS team_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    user_id INTEGER,
                    team_id TEXT,
                    created_at REAL
                )
            """)

            await db.commit()

        self.voice_tracker.start()

    def cog_unload(self):
        self.voice_tracker.cancel()

    # -----------------------------------------------
    # PROFILE
    # -----------------------------------------------

    @app_commands.command(
        name="profile",
        description="View your or another member's Teamy profile"
    )
    @app_commands.guild_only()
    async def profile(
        self,
        interaction: discord.Interaction,
        member: discord.Member = None
    ):
        member = member or interaction.user

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT xp, level, messages, voice_time
                FROM levels
                WHERE guild_id = ? AND user_id = ?
            """, (interaction.guild.id, member.id)) as cursor:
                message_row = await cursor.fetchone()

            async with db.execute("""
                SELECT xp, level
                FROM voice_levels
                WHERE guild_id = ? AND user_id = ?
            """, (interaction.guild.id, member.id)) as cursor:
                voice_row = await cursor.fetchone()

            async with db.execute("""
                SELECT teams_created, teams_joined, tickets_handled
                FROM member_stats
                WHERE guild_id = ? AND user_id = ?
            """, (interaction.guild.id, member.id)) as cursor:
                stats_row = await cursor.fetchone()

            async with db.execute("""
                SELECT COUNT(*)
                FROM levels
                WHERE guild_id = ? AND xp > (
                    SELECT COALESCE(xp, 0)
                    FROM levels
                    WHERE guild_id = ? AND user_id = ?
                )
            """, (
                interaction.guild.id,
                interaction.guild.id,
                member.id
            )) as cursor:
                message_rank_row = await cursor.fetchone()

            async with db.execute("""
                SELECT COUNT(*)
                FROM voice_levels
                WHERE guild_id = ? AND xp > (
                    SELECT COALESCE(xp, 0)
                    FROM voice_levels
                    WHERE guild_id = ? AND user_id = ?
                )
            """, (
                interaction.guild.id,
                interaction.guild.id,
                member.id
            )) as cursor:
                voice_rank_row = await cursor.fetchone()

        message_row = message_row or (0, 0, 0, 0)
        voice_row = voice_row or (0, 0)
        stats_row = stats_row or (0, 0, 0)

        message_xp, message_level, messages, voice_time = message_row
        voice_xp, voice_level = voice_row
        teams_created, teams_joined, tickets_handled = stats_row

        message_rank = (message_rank_row[0] or 0) + 1
        voice_rank = (voice_rank_row[0] or 0) + 1

        embed = discord.Embed(
            title=f"👤 {member.display_name}'s Profile",
            colour=discord.Colour.blurple()
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(
            name="💬 Message Level",
            value=(
                f"**Level:** {message_level}\n"
                f"**XP:** {message_xp:,}\n"
                f"**Messages:** {messages:,}\n"
                f"**Rank:** #{message_rank}"
            ),
            inline=True
        )

        embed.add_field(
            name="🔊 Voice Level",
            value=(
                f"**Level:** {voice_level}\n"
                f"**XP:** {voice_xp:,}\n"
                f"**Time:** {voice_time // 3600}h "
                f"{(voice_time % 3600) // 60}m\n"
                f"**Rank:** #{voice_rank}"
            ),
            inline=True
        )

        embed.add_field(
            name="🤝 Team Statistics",
            value=(
                f"**Teams Created:** {teams_created:,}\n"
                f"**Teams Joined:** {teams_joined:,}\n"
                f"**Tickets Handled:** {tickets_handled:,}"
            ),
            inline=False
        )

        embed.add_field(
            name="📈 Next Message Level",
            value=f"{xp_for_next_level(message_level):,} XP",
            inline=True
        )

        embed.add_field(
            name="🎙️ Next Voice Level",
            value=f"{xp_for_next_level(voice_level):,} XP",
            inline=True
        )

        embed.set_footer(
            text=(
                f"Member since "
                f"{member.joined_at.strftime('%d %b %Y') if member.joined_at else 'Unknown'}"
            )
        )

        await interaction.response.send_message(embed=embed)

    # -----------------------------------------------
    # RANK
    # -----------------------------------------------

    @app_commands.command(
        name="rank",
        description="View your message and voice rank"
    )
    @app_commands.guild_only()
    async def rank(
        self,
        interaction: discord.Interaction,
        member: discord.Member = None
    ):
        member = member or interaction.user

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT xp, level, messages
                FROM levels
                WHERE guild_id = ? AND user_id = ?
            """, (interaction.guild.id, member.id)) as cursor:
                row = await cursor.fetchone()

            async with db.execute("""
                SELECT xp, level
                FROM voice_levels
                WHERE guild_id = ? AND user_id = ?
            """, (interaction.guild.id, member.id)) as cursor:
                voice_row = await cursor.fetchone()

        row = row or (0, 0, 0)
        voice_row = voice_row or (0, 0)

        message_xp, message_level, messages = row
        voice_xp, voice_level = voice_row

        embed = discord.Embed(
            title=f"📊 Rank — {member.display_name}",
            colour=discord.Colour.blurple()
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(
            name="💬 Message Rank",
            value=f"Level **{message_level}**\n{message_xp:,} XP",
            inline=True
        )

        embed.add_field(
            name="🔊 Voice Rank",
            value=f"Level **{voice_level}**\n{voice_xp:,} XP",
            inline=True
        )

        embed.add_field(
            name="Messages",
            value=f"{messages:,}",
            inline=True
        )

        await interaction.response.send_message(embed=embed)

    # -----------------------------------------------
    # MESSAGE LEADERBOARD
    # -----------------------------------------------

    @leaderboard_group.command(
        name="messages",
        description="View the message XP leaderboard"
    )
    @app_commands.guild_only()
    async def message_leaderboard(self, interaction: discord.Interaction):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT user_id, xp, level, messages
                FROM levels
                WHERE guild_id = ?
                ORDER BY xp DESC
                LIMIT 10
            """, (interaction.guild.id,)) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return await interaction.response.send_message(
                "There isn't any message XP data yet.",
                ephemeral=True
            )

        lines = []
        medals = ["🥇", "🥈", "🥉"]

        for index, (user_id, xp, level, messages) in enumerate(rows, 1):
            medal = medals[index - 1] if index <= 3 else f"**#{index}**"

            lines.append(
                f"{medal} <@{user_id}> — Level **{level}** "
                f"• **{xp:,} XP** • {messages:,} messages"
            )

        embed = discord.Embed(
            title="💬 Message Leaderboard",
            description="\n".join(lines),
            colour=discord.Colour.gold()
        )

        await interaction.response.send_message(embed=embed)

    # -----------------------------------------------
    # VOICE LEADERBOARD
    # -----------------------------------------------

    @leaderboard_group.command(
        name="voice",
        description="View the voice XP leaderboard"
    )
    @app_commands.guild_only()
    async def voice_leaderboard(self, interaction: discord.Interaction):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT v.user_id, v.xp, v.level, l.voice_time
                FROM voice_levels v
                LEFT JOIN levels l
                    ON l.guild_id = v.guild_id
                    AND l.user_id = v.user_id
                WHERE v.guild_id = ?
                ORDER BY v.xp DESC
                LIMIT 10
            """, (interaction.guild.id,)) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return await interaction.response.send_message(
                "There isn't any voice XP data yet.",
                ephemeral=True
            )

        lines = []
        medals = ["🥇", "🥈", "🥉"]

        for index, (user_id, xp, level, voice_time) in enumerate(rows, 1):
            medal = medals[index - 1] if index <= 3 else f"**#{index}**"
            minutes = (voice_time or 0) // 60

            lines.append(
                f"{medal} <@{user_id}> — Level **{level}** "
                f"• **{xp:,} XP** • {minutes:,} minutes"
            )

        embed = discord.Embed(
            title="🔊 Voice Leaderboard",
            description="\n".join(lines),
            colour=discord.Colour.gold()
        )

        await interaction.response.send_message(embed=embed)

    # -----------------------------------------------
    # TEAM LEADERBOARD
    # -----------------------------------------------

    @leaderboard_group.command(
        name="teams",
        description="View the team creation leaderboard"
    )
    @app_commands.guild_only()
    async def team_leaderboard(self, interaction: discord.Interaction):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT user_id, teams_created
                FROM member_stats
                WHERE guild_id = ? AND teams_created > 0
                ORDER BY teams_created DESC
                LIMIT 10
            """, (interaction.guild.id,)) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return await interaction.response.send_message(
                "There isn't any team creation data yet.",
                ephemeral=True
            )

        lines = []
        medals = ["🥇", "🥈", "🥉"]

        for index, (user_id, count) in enumerate(rows, 1):
            medal = medals[index - 1] if index <= 3 else f"**#{index}**"

            lines.append(
                f"{medal} <@{user_id}> — **{count:,} teams created**"
            )

        embed = discord.Embed(
            title="🤝 Team Creation Leaderboard",
            description="\n".join(lines),
            colour=discord.Colour.gold()
        )

        await interaction.response.send_message(embed=embed)

    # -----------------------------------------------
    # MESSAGE XP
    # -----------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        if len(message.content.strip()) < 3 and not message.attachments:
            return

        key = (message.guild.id, message.author.id)
        now = time.monotonic()

        last_award = self.message_cooldowns.get(key)

        if last_award is not None and now - last_award < 30:
            return

        self.message_cooldowns[key] = now
        xp_gain = random.randint(15, 25)

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT OR IGNORE INTO levels
                (guild_id, user_id, xp, level, messages, voice_time)
                VALUES (?, ?, 0, 0, 0, 0)
            """, (message.guild.id, message.author.id))

            await db.execute("""
                UPDATE levels
                SET xp = xp + ?, messages = messages + 1
                WHERE guild_id = ? AND user_id = ?
            """, (xp_gain, message.guild.id, message.author.id))

            async with db.execute("""
                SELECT xp, level
                FROM levels
                WHERE guild_id = ? AND user_id = ?
            """, (message.guild.id, message.author.id)) as cursor:
                xp, old_level = await cursor.fetchone()

            new_level = calculate_level(xp)

            if new_level > old_level:
                await db.execute("""
                    UPDATE levels
                    SET level = ?
                    WHERE guild_id = ? AND user_id = ?
                """, (new_level, message.guild.id, message.author.id))

            await db.commit()

        if new_level > old_level:
            embed = discord.Embed(
                title="🎉 Level Up!",
                description=(
                    f"{message.author.mention} reached "
                    f"**Message Level {new_level}**!\n"
                    f"You now have **{xp:,} XP**."
                ),
                colour=discord.Colour.green()
            )

            try:
                await message.channel.send(
                    embed=embed,
                    delete_after=15
                )
            except discord.HTTPException:
                pass

    # -----------------------------------------------
    # VOICE STATE UPDATES
    # -----------------------------------------------

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ):
        if member.bot:
            return

        key = (member.guild.id, member.id)

        if voice_eligible(member):
            self.voice_sessions.setdefault(key, (time.monotonic(), 0.0))
        else:
            self.voice_sessions.pop(key, None)

    # -----------------------------------------------
    # VOICE XP TRACKER
    # -----------------------------------------------

    @tasks.loop(seconds=10)
    async def voice_tracker(self):
        now = time.monotonic()
        active_members = set()

        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                for member in channel.members:
                    if not voice_eligible(member):
                        continue

                    key = (guild.id, member.id)
                    active_members.add(key)

                    session = self.voice_sessions.get(key)

                    if session is None:
                        self.voice_sessions[key] = (now, 0.0)
                        continue

                    last_check, remainder = session

                    # Avoid awarding excessive XP if the task stalls.
                    elapsed = min(now - last_check, 30.0)
                    total = remainder + elapsed

                    minutes_earned = int(total // 60)
                    new_remainder = total % 60

                    self.voice_sessions[key] = (now, new_remainder)

                    async with aiosqlite.connect(config.DATABASE) as db:
                        await db.execute("""
                            INSERT OR IGNORE INTO levels
                            (guild_id, user_id, xp, level, messages, voice_time)
                            VALUES (?, ?, 0, 0, 0, 0)
                        """, (guild.id, member.id))

                        await db.execute("""
                            INSERT OR IGNORE INTO voice_levels
                            (guild_id, user_id, xp, level)
                            VALUES (?, ?, 0, 0)
                        """, (guild.id, member.id))

                        await db.execute("""
                            UPDATE levels
                            SET voice_time = voice_time + ?
                            WHERE guild_id = ? AND user_id = ?
                        """, (
                            int(elapsed),
                            guild.id,
                            member.id
                        ))

                        if minutes_earned:
                            await db.execute("""
                                UPDATE voice_levels
                                SET xp = xp + ?
                                WHERE guild_id = ? AND user_id = ?
                            """, (
                                minutes_earned * 5,
                                guild.id,
                                member.id
                            ))

                            async with db.execute("""
                                SELECT xp, level
                                FROM voice_levels
                                WHERE guild_id = ? AND user_id = ?
                            """, (guild.id, member.id)) as cursor:
                                xp, old_level = await cursor.fetchone()

                            new_level = calculate_level(xp)

                            if new_level > old_level:
                                await db.execute("""
                                    UPDATE voice_levels
                                    SET level = ?
                                    WHERE guild_id = ? AND user_id = ?
                                """, (
                                    new_level,
                                    guild.id,
                                    member.id
                                ))

                        await db.commit()

                    if minutes_earned and new_level > old_level:
                        try:
                            await channel.send(
                                f"🎉 {member.mention} reached "
                                f"**Voice Level {new_level}**!"
                            )
                        except discord.HTTPException:
                            pass

        # Remove sessions for members who have left voice
        # or are no longer eligible for XP.
        for key in list(self.voice_sessions):
            if key not in active_members:
                self.voice_sessions.pop(key, None)

    @voice_tracker.before_loop
    async def before_voice_tracker(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Leveling(bot))
