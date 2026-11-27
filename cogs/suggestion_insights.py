
import discord
import aiosqlite
from discord import app_commands
from discord.ext import commands

import config


class SuggestionInsights(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="mysuggestions",
        description="View your submitted suggestions."
    )
    async def my_suggestions(self, interaction: discord.Interaction):
        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute("""
                SELECT id, suggestion, status, timestamp
                FROM suggestions
                WHERE guild_id = ? AND user_id = ?
                ORDER BY timestamp DESC
                LIMIT 10
            """, (interaction.guild.id, interaction.user.id))

            rows = await cursor.fetchall()

        if not rows:
            await interaction.response.send_message(
                "You haven't submitted any suggestions yet.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Your Suggestions",
            color=discord.Color.blurple()
        )

        for suggestion_id, suggestion, status, timestamp in rows:
            status_emoji = {
                "pending": "🕒",
                "approved": "✅",
                "denied": "❌"
            }.get(status, "❔")

            embed.add_field(
                name=f"{status_emoji} Suggestion #{suggestion_id} — {status.title()}",
                value=(
                    f"{suggestion[:250]}\n"
                    f"<t:{timestamp}:R>"
                ),
                inline=False
            )

        embed.set_footer(text="Showing your 10 most recent suggestions.")

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="suggestionstats",
        description="View server suggestion statistics."
    )
    async def suggestion_stats(self, interaction: discord.Interaction):
        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute("""
                SELECT
                    COUNT(*),
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN status = 'denied' THEN 1 ELSE 0 END)
                FROM suggestions
                WHERE guild_id = ?
            """, (interaction.guild.id,))

            result = await cursor.fetchone()

        total, pending, approved, denied = result

        total = total or 0
        pending = pending or 0
        approved = approved or 0
        denied = denied or 0

        embed = discord.Embed(
            title="Suggestion Statistics",
            description="Community suggestion overview",
            color=discord.Color.blurple()
        )

        embed.add_field(name="Total Suggestions", value=f"**{total}**", inline=True)
        embed.add_field(name="Pending", value=f"🕒 **{pending}**", inline=True)
        embed.add_field(name="Approved", value=f"✅ **{approved}**", inline=True)
        embed.add_field(name="Denied", value=f"❌ **{denied}**", inline=True)

        if total:
            approval_rate = round((approved / total) * 100)
        else:
            approval_rate = 0

        embed.add_field(
            name="Approval Rate",
            value=f"**{approval_rate}%**",
            inline=False
        )

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(SuggestionInsights(bot))
