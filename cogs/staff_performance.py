
import discord
import aiosqlite
from discord import app_commands
from discord.ext import commands
import config


class StaffPerformance(commands.Cog):
    staffperformance = app_commands.Group(
        name="staffperformance",
        description="Staff performance statistics"
    )

    def __init__(self, bot):
        self.bot = bot

    async def is_manager(self, member):
        if member.id == member.guild.owner_id:
            return True

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT role_id FROM staff_role_config
                WHERE guild_id = ? AND division = 'staff_managers'
            """, (member.guild.id,)) as cursor:
                rows = await cursor.fetchall()

        manager_roles = {row[0] for row in rows}
        return any(role.id in manager_roles for role in member.roles)

    async def check_access(self, interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "Use this command inside your server.",
                ephemeral=True
            )
            return False

        if not await self.is_manager(interaction.user):
            await interaction.response.send_message(
                "Only Staff Managers and the server owner can access this.",
                ephemeral=True
            )
            return False

        return True

    async def get_stats(self, guild_id, user_id):
        async with aiosqlite.connect(config.DATABASE) as db:

            async def count(query, params):
                async with db.execute(query, params) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0

            stats = {}

            stats["claimed"] = await count("""
                SELECT COUNT(*) FROM tickets
                WHERE guild_id = ? AND claimed_by = ?
            """, (guild_id, user_id))

            stats["closed"] = await count("""
                SELECT COUNT(*) FROM tickets
                WHERE guild_id = ? AND claimed_by = ? AND closed = 1
            """, (guild_id, user_id))

            stats["open"] = await count("""
                SELECT COUNT(*) FROM tickets
                WHERE guild_id = ? AND claimed_by = ? AND closed = 0
            """, (guild_id, user_id))

            stats["submitted"] = await count("""
                SELECT COUNT(*) FROM staff_requests
                WHERE guild_id = ? AND requester_id = ?
            """, (guild_id, user_id))

            stats["received"] = await count("""
                SELECT COUNT(*) FROM staff_requests
                WHERE guild_id = ? AND target_id = ?
                AND status = 'approved'
            """, (guild_id, user_id))

            stats["strikes"] = await count("""
                SELECT COUNT(*) FROM staff_strikes
                WHERE guild_id = ? AND user_id = ?
            """, (guild_id, user_id))

            stats["notes"] = await count("""
                SELECT COUNT(*) FROM division_notes
                WHERE guild_id = ? AND user_id = ?
            """, (guild_id, user_id))

        return stats

    @staffperformance.command(
        name="member",
        description="View an individual staff member's performance."
    )
    async def member(
        self,
        interaction: discord.Interaction,
        staff_member: discord.Member
    ):
        if not await self.check_access(interaction):
            return

        stats = await self.get_stats(
            interaction.guild.id,
            staff_member.id
        )

        embed = discord.Embed(
            title="Teamy | Staff Performance",
            description=f"Performance overview for {staff_member.mention}",
            colour=discord.Colour.blurple()
        )

        embed.set_thumbnail(url=staff_member.display_avatar.url)

        fields = [
            ("🎫 Tickets Claimed", stats["claimed"]),
            ("🔒 Claimed Tickets Closed", stats["closed"]),
            ("⏳ Open Claimed Tickets", stats["open"]),
            ("📋 Requests Submitted", stats["submitted"]),
            ("✅ Approved Actions Received", stats["received"]),
            ("⚠️ Strikes Received", stats["strikes"]),
            ("📝 Staff Notes", stats["notes"])
        ]

        for name, value in fields:
            embed.add_field(
                name=name,
                value=str(value),
                inline=True
            )

        embed.set_footer(
            text="Teamy Staff Management • Internal Performance Report"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @staffperformance.command(
        name="leaderboard",
        description="View the ticket-claim activity leaderboard."
    )
    async def leaderboard(self, interaction: discord.Interaction):
        if not await self.check_access(interaction):
            return

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT claimed_by, COUNT(*)
                FROM tickets
                WHERE guild_id = ? AND claimed_by IS NOT NULL
                GROUP BY claimed_by
                ORDER BY COUNT(*) DESC
                LIMIT 10
            """, (interaction.guild.id,)) as cursor:
                rows = await cursor.fetchall()

        embed = discord.Embed(
            title="🏆 Teamy Staff Activity Leaderboard",
            description="Ranked by recorded ticket claims.",
            colour=discord.Colour.gold()
        )

        if not rows:
            embed.description = "No ticket claims have been recorded yet."
        else:
            lines = []

            for position, (user_id, claims) in enumerate(rows, start=1):
                staff_member = interaction.guild.get_member(user_id)
                name = (
                    staff_member.mention
                    if staff_member else f"`{user_id}`"
                )

                lines.append(
                    f"**#{position}** {name} — **{claims}** claims"
                )

            embed.description = "\n".join(lines)

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(StaffPerformance(bot))
