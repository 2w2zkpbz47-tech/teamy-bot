
import discord
import aiosqlite
from discord import app_commands
from discord.ext import commands
import config


class StaffApprovalQueue(commands.Cog):
    staffapprovals = app_commands.Group(
        name="staffapprovals",
        description="Server-owner staff approval queue"
    )

    def __init__(self, bot):
        self.bot = bot

    async def owner_only(self, interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command must be used inside the server.",
                ephemeral=True
            )
            return False

        if interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(
                "Only the server owner can access the approval queue.",
                ephemeral=True
            )
            return False

        return True

    @staffapprovals.command(
        name="pending",
        description="View all staff requests awaiting owner approval."
    )
    async def pending(self, interaction: discord.Interaction):
        if not await self.owner_only(interaction):
            return

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT request_id, requester_id, target_id,
                       division, action, reason, created_at
                FROM staff_requests
                WHERE guild_id = ? AND status = 'pending'
                ORDER BY created_at ASC
                LIMIT 15
            """, (interaction.guild.id,)) as cursor:
                rows = await cursor.fetchall()

        embed = discord.Embed(
            title="Teamy | Pending Staff Approvals",
            description="Requests waiting for your decision.",
            colour=discord.Colour.orange()
        )

        if not rows:
            embed.description = "There are no pending staff requests."
        else:
            for request_id, requester, target, division, action, reason, created in rows:
                embed.add_field(
                    name=f"{action.title()} • `{request_id}`",
                    value=(
                        f"**Requested by:** <@{requester}>\n"
                        f"**Target:** <@{target}>\n"
                        f"**Division:** {division.replace('_', ' ').title()}\n"
                        f"**Reason:** {reason[:500]}\n"
                        f"**Submitted:** <t:{int(created)}:R>"
                    ),
                    inline=False
                )

        embed.set_footer(
            text="Use the approval buttons in your DM to approve or deny requests."
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @staffapprovals.command(
        name="history",
        description="View recently reviewed staff requests."
    )
    async def history(self, interaction: discord.Interaction):
        if not await self.owner_only(interaction):
            return

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT request_id, requester_id, target_id,
                       division, action, status, reviewed_at
                FROM staff_requests
                WHERE guild_id = ? AND status != 'pending'
                ORDER BY reviewed_at DESC
                LIMIT 15
            """, (interaction.guild.id,)) as cursor:
                rows = await cursor.fetchall()

        embed = discord.Embed(
            title="Teamy | Staff Approval History",
            description="Recently reviewed staff requests.",
            colour=discord.Colour.blurple()
        )

        if not rows:
            embed.description = "No reviewed staff requests were found."
        else:
            for request_id, requester, target, division, action, status, reviewed in rows:
                embed.add_field(
                    name=f"{status.upper()} • `{request_id}`",
                    value=(
                        f"**Action:** {action.title()}\n"
                        f"**Requested by:** <@{requester}>\n"
                        f"**Target:** <@{target}>\n"
                        f"**Division:** {division.replace('_', ' ').title()}\n"
                        f"**Reviewed:** <t:{int(reviewed)}:R>"
                    ),
                    inline=False
                )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(StaffApprovalQueue(bot))
