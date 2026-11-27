
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button
import aiosqlite
import random
import re
from datetime import datetime, timedelta, timezone
import config


class GiveawayView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Enter Giveaway",
        style=discord.ButtonStyle.success,
        emoji="🎉",
        custom_id="giveaway:enter"
    )
    async def enter(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild:
            return await interaction.response.send_message(
                "Giveaways can only be entered in a server.",
                ephemeral=True
            )

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute(
                "SELECT ended FROM giveaways WHERE message_id = ? AND guild_id = ?",
                (interaction.message.id, interaction.guild.id)
            ) as cursor:
                giveaway = await cursor.fetchone()

            if not giveaway:
                return await interaction.response.send_message(
                    "This giveaway could not be found.",
                    ephemeral=True
                )

            if giveaway[0]:
                return await interaction.response.send_message(
                    "This giveaway has already ended.",
                    ephemeral=True
                )

            await db.execute("""
                INSERT OR IGNORE INTO giveaway_entries
                (message_id, user_id)
                VALUES (?, ?)
            """, (interaction.message.id, interaction.user.id))
            await db.commit()

            async with db.execute(
                "SELECT changes()"
            ) as cursor:
                inserted = (await cursor.fetchone())[0]

        if inserted:
            await interaction.response.send_message(
                "🎉 You're entered! Good luck!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "You're already entered in this giveaway!",
                ephemeral=True
            )


class Giveaways(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_giveaways.start()

    async def cog_load(self):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS giveaways (
                    message_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    prize TEXT NOT NULL,
                    winners INTEGER NOT NULL,
                    end_time REAL NOT NULL,
                    host_id INTEGER NOT NULL,
                    ended INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS giveaway_entries (
                    message_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    PRIMARY KEY (message_id, user_id)
                );
            """)
            await db.commit()

        self.bot.add_view(GiveawayView(self.bot))

    def cog_unload(self):
        self.check_giveaways.cancel()

    @app_commands.command(name="gstart", description="Start a giveaway")
    @app_commands.describe(
        duration="Duration, e.g. 10m, 1h or 1d",
        winners="Number of winners",
        prize="What are you giving away?"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gstart(
        self,
        interaction: discord.Interaction,
        duration: str,
        winners: app_commands.Range[int, 1, 20],
        prize: str
    ):
        match = re.fullmatch(r"([1-9][0-9]*)([smhd])", duration.lower())

        if not match:
            return await interaction.response.send_message(
                "Invalid duration. Use `30s`, `10m`, `1h` or `1d`.",
                ephemeral=True
            )

        amount = int(match.group(1))
        unit = match.group(2)
        seconds = amount * {
            "s": 1,
            "m": 60,
            "h": 3600,
            "d": 86400
        }[unit]

        if seconds < 30:
            return await interaction.response.send_message(
                "Giveaways must last at least 30 seconds.",
                ephemeral=True
            )

        if seconds > 31_536_000:
            return await interaction.response.send_message(
                "Giveaways cannot last longer than one year.",
                ephemeral=True
            )

        end_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)

        embed = discord.Embed(
            title="🎉 GIVEAWAY",
            description=(
                f"**Prize:** {prize}\n"
                f"**Winners:** {winners}\n"
                f"**Ends:** <t:{int(end_time.timestamp())}:R>\n\n"
                "Click the button below to enter!"
            ),
            color=getattr(config, "COLOR_GIVEAWAY", 0xF1C40F)
        )
        embed.set_footer(text=f"Hosted by {interaction.user}")

        message = await interaction.channel.send(
            embed=embed,
            view=GiveawayView(self.bot)
        )

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT INTO giveaways
                (message_id, channel_id, guild_id, prize, winners,
                 end_time, host_id, ended)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                message.id,
                interaction.channel.id,
                interaction.guild.id,
                prize,
                winners,
                end_time.timestamp(),
                interaction.user.id
            ))
            await db.commit()

        await interaction.response.send_message(
            f"✅ Giveaway started! [Jump to giveaway]({message.jump_url})",
            ephemeral=True
        )

    @app_commands.command(name="gend", description="End a giveaway early")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gend(
        self,
        interaction: discord.Interaction,
        message_id: str
    ):
        try:
            giveaway_id = int(message_id)
        except ValueError:
            return await interaction.response.send_message(
                "Please provide a valid giveaway message ID.",
                ephemeral=True
            )

        result = await self.end_giveaway(
            giveaway_id,
            interaction.guild
        )

        messages = {
            "ended": "✅ Giveaway ended and winners were selected.",
            "missing": "❌ I couldn't find that giveaway.",
            "already": "This giveaway has already ended.",
            "unavailable": "I couldn't access the giveaway channel or message."
        }

        await interaction.response.send_message(
            messages[result],
            ephemeral=True
        )

    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute(
                "SELECT message_id, guild_id FROM giveaways "
                "WHERE ended = 0 AND end_time <= ?",
                (datetime.now(timezone.utc).timestamp(),)
            ) as cursor:
                rows = await cursor.fetchall()

        for message_id, guild_id in rows:
            guild = self.bot.get_guild(guild_id)
            if guild:
                await self.end_giveaway(message_id, guild)

    @check_giveaways.before_loop
    async def before_check_giveaways(self):
        await self.bot.wait_until_ready()

    async def end_giveaway(self, message_id: int, guild: discord.Guild):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT channel_id, prize, winners, ended
                FROM giveaways
                WHERE message_id = ? AND guild_id = ?
            """, (message_id, guild.id)) as cursor:
                row = await cursor.fetchone()

            if not row:
                return "missing"

            channel_id, prize, winner_count, ended = row

            if ended:
                return "already"

            channel = guild.get_channel(channel_id)
            if not channel:
                return "unavailable"

            try:
                message = await channel.fetch_message(message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return "unavailable"

            async with db.execute(
                "SELECT user_id FROM giveaway_entries WHERE message_id = ?",
                (message_id,)
            ) as cursor:
                entries = await cursor.fetchall()

            user_ids = [entry[0] for entry in entries]

            # Mark as ended only once, preventing duplicate winner announcements.
            cursor = await db.execute(
                "UPDATE giveaways SET ended = 1 "
                "WHERE message_id = ? AND ended = 0",
                (message_id,)
            )
            await db.commit()

            if cursor.rowcount == 0:
                return "already"

        winners = random.sample(
            user_ids,
            min(winner_count, len(user_ids))
        ) if user_ids else []

        embed = discord.Embed(
            title="🎉 GIVEAWAY ENDED",
            description=f"**Prize:** {prize}",
            color=getattr(config, "COLOR_GIVEAWAY", 0xF1C40F)
        )

        if winners:
            winner_mentions = ", ".join(f"<@{user_id}>" for user_id in winners)
            embed.add_field(
                name="🏆 Winner(s)",
                value=winner_mentions,
                inline=False
            )
            announcement = (
                f"🎉 Congratulations {winner_mentions}! "
                f"You won **{prize}**!"
            )
        else:
            embed.add_field(
                name="Entries",
                value="Nobody entered this giveaway.",
                inline=False
            )
            announcement = f"Nobody entered the giveaway for **{prize}**."

        embed.set_footer(text=f"{len(user_ids)} entr(y/ies)")

        try:
            await message.edit(embed=embed, view=None)
            await channel.send(
                announcement,
                allowed_mentions=discord.AllowedMentions(users=True)
            )
        except discord.HTTPException:
            pass

        return "ended"


async def setup(bot):
    await bot.add_cog(Giveaways(bot))
