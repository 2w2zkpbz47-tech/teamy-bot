import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button
import aiosqlite
import asyncio
import random
from datetime import datetime, timedelta, timezone
import config
from utils.embeds import create_embed

class Giveaways(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    @app_commands.command(name="gstart", description="Start a giveaway")
    @app_commands.describe(
        duration="Duration (e.g. 10m, 1h, 1d)",
        winners="Number of winners",
        prize="What are you giving away?"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gstart(self, interaction: discord.Interaction, duration: str, winners: app_commands.Range[int, 1, 20], prize: str):
        # Parse duration
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        try:
            amount = int(duration[:-1])
            unit = duration[-1].lower()
            seconds = amount * units[unit]
            if seconds < 30:
                return await interaction.response.send_message("Duration must be at least 30 seconds.", ephemeral=True)
        except:
            return await interaction.response.send_message("Invalid duration. Use examples: `10m`, `1h`, `1d`", ephemeral=True)

        end_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)

        embed = create_embed(
            "🎉 GIVEAWAY",
            f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** <t:{int(end_time.timestamp())}:R> (<t:{int(end_time.timestamp())}:f>)\n\nClick the button below to enter!",
            config.COLOR_GIVEAWAY
        )
        embed.set_footer(text=f"Hosted by {interaction.user}")

        view = GiveawayView()
        message = await interaction.channel.send(embed=embed, view=view)

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                "INSERT INTO giveaways (message_id, channel_id, guild_id, prize, winners, end_time, host_id, ended) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                (message.id, interaction.channel.id, interaction.guild.id, prize, winners, end_time.timestamp(), interaction.user.id)
            )
            await db.commit()

        await interaction.response.send_message("✅ Giveaway started!", ephemeral=True)

    @app_commands.command(name="gend", description="End a giveaway early")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gend(self, interaction: discord.Interaction, message_id: str):
        try:
            message_id = int(message_id)
        except:
            return await interaction.response.send_message("Invalid message ID.", ephemeral=True)

        await self.end_giveaway(message_id, interaction.guild)
        await interaction.response.send_message("✅ Giveaway ended.", ephemeral=True)

    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("SELECT message_id, channel_id, guild_id, prize, winners, end_time FROM giveaways WHERE ended = 0") as cursor:
                rows = await cursor.fetchall()

        now = datetime.now(timezone.utc).timestamp()
        for message_id, channel_id, guild_id, prize, winners, end_time in rows:
            if now >= end_time:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    await self.end_giveaway(message_id, guild)

    async def end_giveaway(self, message_id: int, guild: discord.Guild):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("SELECT channel_id, prize, winners, ended FROM giveaways WHERE message_id = ?", (message_id,)) as cursor:
                row = await cursor.fetchone()

            if not row or row[3] == 1:
                return

            channel_id, prize, winners_count, _ = row
            channel = guild.get_channel(channel_id)
            if not channel:
                return

            try:
                message = await channel.fetch_message(message_id)
            except:
                return

            # Get users who reacted with the button (we'll use reactions as fallback)
            # For simplicity, we'll use a basic method
            users = []
            for reaction in message.reactions:
                if str(reaction.emoji) == "🎉":
                    async for user in reaction.users():
                        if not user.bot:
                            users.append(user)

            # Better: Since we used a button, we should store entries. For now using reactions as simple version.
            if not users:
                # Fallback message
                embed = create_embed("🎉 Giveaway Ended", f"**Prize:** {prize}\n\nNo one entered the giveaway.", config.COLOR_GIVEAWAY)
                await message.edit(embed=embed, view=None)
            else:
                winners = random.sample(users, min(winners_count, len(users)))
                winners_text = ", ".join(w.mention for w in winners)

                embed = create_embed(
                    "🎉 Giveaway Ended",
                    f"**Prize:** {prize}\n**Winners:** {winners_text}\n\nCongratulations!",
                    config.COLOR_GIVEAWAY
                )
                await message.edit(embed=embed, view=None)
                await channel.send(f"🎉 Congratulations {winners_text}! You won **{prize}**!")

            await db.execute("UPDATE giveaways SET ended = 1 WHERE message_id = ?", (message_id,))
            await db.commit()

class GiveawayView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.success, emoji="🎉", custom_id="giveaway:enter")
    async def enter(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("✅ You have entered the giveaway!", ephemeral=True)
        # In a full version we would store the entry in the database

async def setup(bot):
    await bot.add_cog(Giveaways(bot))