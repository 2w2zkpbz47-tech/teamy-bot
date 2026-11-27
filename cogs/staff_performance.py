
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
                "This command can only be used in a server.",
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

        guild_id = interaction.guild.id
        user_id = staff_member.id

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT tickets_handled
                FROM member_stats
                WHERE guild_id = ? AND user_id = ?
            """, (guild_id, user_id)) as cursor:
                stats = await cursor.fetchone()

            async with db.execute("""
                SELECT COUNT(*)
                FROM staff_requests
                WHERE guild_id = ? AND requester_id = ?
            """, (guild_id, user_id)) as cursor:
                submitted = (await cursor.fetchone())[0]

            async with db.execute("""
                SELECT COUNT(*)
                FROM staff_requests
                WHERE guild_id = ? AND target_id = ?
                AND status = 'approved'
            """, (guild_id, user_id)) as cursor:
                approved_actions = (await cursor.fetchone())[0]

            async with db.execute("""
                SELECT COUNT(*)
                FROM staff_strikes
                WHERE guild_id = ? AND user_id = ?
            """, (guild_id, user_id)) as cursor:
                strikes = (await cursor.fetchone())[0]

            async with db.execute("""
                SELECT COUNT(*)
                FROM division_notes
                WHERE guild_id = ? AND user_id = ?
            """, (guild_id, user_id)) as cursor:
                notes = (await cursor.fetchone())[0]

        ticket_claims = stats[0] if stats else 0

        embed = discord.Embed(
            title="Teamy | Staff Performance",
            description=f"Performance overview for {staff_member.mention}",
            colour=discord.Colour.blurple()
        )

        embed.set_thumbnail(url=staff_member.display_avatar.url)

        embed.add_field(
            name="🎫 Recorded Ticket Claims",
            value=str(ticket_claims),
            inline=True
        )
        embed.add_field(
            name="📋 Requests Submitted",
            value=str(submitted),
            inline=True
        )
        embed.add_field(
            name="✅ Approved Staff Actions",
            value=str(approved_actions),
            inline=True
        )
        embed.add_field(
            name="⚠️ Strikes",
            value=str(strikes),
            inline=True
        )
        embed.add_field(
            name="📝 Staff Notes",
            value=str(notes),
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
                SELECT user_id, tickets_handled
                FROM member_stats
                WHERE guild_id = ? AND tickets_handled > 0
                ORDER BY tickets_handled DESC
                LIMIT 10
            """, (interaction.guild.id,)) as cursor:
                rows = await cursor.fetchall()

        embed = discord.Embed(
            title="🏆 Teamy Staff Activity Leaderboard",
            description="Top recorded ticket-claim activity.",
            colour=discord.Colour.gold()
        )

        if not rows:
            embed.description = "No ticket-claim activity has been recorded yet."
        else:
            lines = []

            for position, (user_id, claims) in enumerate(rows, start=1):
                member = interaction.guild.get_member(user_id)
                name = member.mention if member else f"`{user_id}`"

                lines.append(
                    f"**#{position}** {name} — **{claims}** recorded claims"
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
