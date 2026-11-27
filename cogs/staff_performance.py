
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
                SELECT role_id
                FROM staff_role_config
                WHERE guild_id = ? AND division = 'staff_managers'
            """, (member.guild.id,)) as cursor:
                rows = await cursor.fetchall()

        manager_roles = {row[0] for row in rows}
        return any(role.id in manager_roles for role in member.roles)

    async def check_access(self, interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used inside a server.",
                ephemeral=True
            )
            return False

        if not await self.is_manager(interaction.user):
            await interaction.response.send_message(
                "Only Staff Managers and the server owner can view performance records.",
                ephemeral=True
            )
            return False

        return True

    async def get_stats(self, guild_id, user_id):
        async with aiosqlite.connect(config.DATABASE) as db:
            async def count(query, parameters):
                async with db.execute(query, parameters) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0

            claimed = await count("""
                SELECT COUNT(*) FROM tickets
                WHERE guild_id = ? AND claimed_by = ?
            """, (guild_id, user_id))

            closed = await count("""
                SELECT COUNT(*) FROM tickets
                WHERE guild_id = ? AND claimed_by = ? AND closed = 1
            """, (guild_id, user_id))

            open_claims = await count("""
                SELECT COUNT(*) FROM tickets
                WHERE guild_id = ? AND claimed_by = ? AND closed = 0
            """, (guild_id, user_id))

            submitted = await count("""
                SELECT COUNT(*) FROM staff_requests
                WHERE guild_id = ? AND requester_id = ?
            """, (guild_id, user_id))

            approved = await count("""
                SELECT COUNT(*) FROM staff_requests
                WHERE guild_id = ? AND requester_id = ?
                AND status = 'approved'
            """, (guild_id, user_id))

            pending = await count("""
                SELECT COUNT(*) FROM staff_requests
                WHERE guild_id = ? AND requester_id = ?
                AND status = 'pending'
            """, (guild_id, user_id))

            strikes_issued = await count("""
                SELECT COUNT(*) FROM staff_strikes
                WHERE guild_id = ? AND issued_by = ?
            """, (guild_id, user_id))

            notes_added = await count("""
                SELECT COUNT(*) FROM division_notes
                WHERE guild_id = ? AND added_by = ?
            """, (guild_id, user_id))

        return {
            "claimed": claimed,
            "closed": closed,
            "open": open_claims,
            "submitted": submitted,
            "approved": approved,
            "pending": pending,
            "strikes": strikes_issued,
            "notes": notes_added
        }

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

        embed.add_field(
            name="🎫 Tickets Claimed",
            value=str(stats["claimed"]),
            inline=True
        )
        embed.add_field(
            name="🔒 Claimed Tickets Closed",
            value=str(stats["closed"]),
            inline=True
        )
        embed.add_field(
            name="⏳ Open Claimed Tickets",
            value=str(stats["open"]),
            inline=True
        )
        embed.add_field(
            name="📋 Requests Submitted",
            value=str(stats["submitted"]),
            inline=True
        )
        embed.add_field(
            name="✅ Requests Approved",
            value=str(stats["approved"]),
            inline=True
        )
        embed.add_field(
            name="⌛ Requests Pending",
            value=str(stats["pending"]),
            inline=True
        )
        embed.add_field(
            name="⚠️ Strikes Issued",
            value=str(stats["strikes"]),
            inline=True
        )
        embed.add_field(
            name="📝 Notes Added",
            value=str(stats["notes"]),
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
            embed.description = "No ticket-claim activity has been recorded yet."
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

        embed.set_footer(
            text="Teamy Staff Management • Internal Leaderboard"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(StaffPerformance(bot))
