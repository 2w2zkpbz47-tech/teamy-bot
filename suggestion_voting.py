
import discord
import aiosqlite
from discord.ext import commands

import config


class SuggestionVoting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def update_vote_counts(self, guild_id, message_id):
        if not guild_id:
            return

        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute("""
                SELECT channel_id
                FROM suggestions
                WHERE guild_id = ? AND message_id = ?
            """, (guild_id, message_id))

            result = await cursor.fetchone()

        if not result:
            return

        channel_id = result[0]
        guild = self.bot.get_guild(guild_id)

        if not guild:
            return

        channel = guild.get_channel(channel_id)

        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return

        try:
            message = await channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        if not message.embeds:
            return

        thumbs_up = 0
        thumbs_down = 0

        for reaction in message.reactions:
            count = reaction.count

            # Exclude Teamy's own starter reaction.
            if reaction.me:
                count = max(0, count - 1)

            if str(reaction.emoji) == "👍":
                thumbs_up = count

            elif str(reaction.emoji) == "👎":
                thumbs_down = count

        embed = message.embeds[0].copy()

        vote_field = None

        for index, field in enumerate(embed.fields):
            if field.name == "Community Votes":
                vote_field = index
                break

        vote_text = (
            f"👍 **{thumbs_up}** in favour\n"
            f"👎 **{thumbs_down}** against"
        )

        if vote_field is None:
            embed.add_field(
                name="Community Votes",
                value=vote_text,
                inline=False
            )
        else:
            embed.set_field_at(
                vote_field,
                name="Community Votes",
                value=vote_text,
                inline=False
            )

        try:
            await message.edit(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return

        if str(payload.emoji) not in ("👍", "👎"):
            return

        await self.update_vote_counts(
            payload.guild_id,
            payload.message_id
        )

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.user_id == self.bot.user.id:
            return

        if str(payload.emoji) not in ("👍", "👎"):
            return

        await self.update_vote_counts(
            payload.guild_id,
            payload.message_id
        )


async def setup(bot):
    await bot.add_cog(SuggestionVoting(bot))
