
import discord
import aiosqlite
from discord import app_commands
from discord.ext import commands

import config


class StaffRecords(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    staffrecord = app_commands.Group(
        name="staffrecord",
        description="View internal staff records."
    )

    async def is_manager(self, member):
        if member.id == member.guild.owner_id:
            return True

        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute("""
                SELECT role_id
                FROM staff_role_config
                WHERE guild_id = ?
                AND division = 'staff_managers'
            """, (member.guild.id,))

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
                "You don't have permission to view staff records.",
                ephemeral=True
            )
            return False

        return True

    @staffrecord.command(
        name="view",
        description="View a member's complete staff history."
    )
    async def view(
        self,
        interaction: discord.Interaction,
        member: discord.Member
    ):
        if not await self.check_access(interaction):
            return

        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute("""
                SELECT action, division, reason, status, created_at
                FROM staff_requests
                WHERE guild_id = ? AND target_id = ?
            """, (interaction.guild.id, member.id))
            requests = await cursor.fetchall()

            cursor = await db.execute("""
                SELECT reason, timestamp
                FROM staff_strikes
                WHERE guild_id = ? AND user_id = ?
            """, (interaction.guild.id, member.id))
            strikes = await cursor.fetchall()

            cursor = await db.execute("""
                SELECT division, note, timestamp
                FROM division_notes
                WHERE guild_id = ? AND user_id = ?
            """, (interaction.guild.id, member.id))
            notes = await cursor.fetchall()

        history = []

        for action, division, reason, status, timestamp in requests:
            history.append((
                timestamp,
                f"📋 {action.title()} — {status.title()}",
                f"{division.replace('_', ' ').title()}\n{reason}"
            ))

        for reason, timestamp in strikes:
            history.append((
                timestamp,
                "⚠️ Staff Strike",
                reason
            ))

        for division, note, timestamp in notes:
            history.append((
                timestamp,
                "📝 Staff Note",
                f"{division.replace('_', ' ').title()}\n{note}"
            ))

        history.sort(key=lambda item: item[0], reverse=True)

        embed = discord.Embed(
            title="Staff Member Record",
            description=f"Records for {member.mention}",
            colour=discord.Colour.blurple()
        )

        embed.add_field(
            name="Total Records",
            value=str(len(history)),
            inline=True
        )
        embed.add_field(
            name="Strikes",
            value=str(len(strikes)),
            inline=True
        )
        embed.add_field(
            name="Staff Notes",
            value=str(len(notes)),
            inline=True
        )

        for timestamp, title, details in history[:10]:
            embed.add_field(
                name=f"{title} • <t:{int(timestamp)}:R>",
                value=details[:1000],
                inline=False
            )

        if not history:
            embed.description += "\n\nNo staff records were found."

        embed.set_footer(text="Teamy Staff Management • Internal Records")

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @staffrecord.command(
        name="strikes",
        description="View a member's staff strikes."
    )
    async def strikes(
        self,
        interaction: discord.Interaction,
        member: discord.Member
    ):
        if not await self.check_access(interaction):
            return

        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute("""
                SELECT issued_by, reason, timestamp
                FROM staff_strikes
                WHERE guild_id = ? AND user_id = ?
                ORDER BY timestamp DESC
            """, (interaction.guild.id, member.id))

            rows = await cursor.fetchall()

        embed = discord.Embed(
            title="Staff Strike History",
            description=f"Member: {member.mention}",
            colour=discord.Colour.red()
        )

        if not rows:
            embed.description += "\n\nNo strikes recorded."
        else:
            embed.add_field(
                name="Total Strikes",
                value=str(len(rows)),
                inline=False
            )

            for issuer, reason, timestamp in rows[:10]:
                embed.add_field(
                    name=f"Strike • <t:{int(timestamp)}:R>",
                    value=f"**Issued by:** <@{issuer}>\n**Reason:** {reason[:800]}",
                    inline=False
                )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @staffrecord.command(
        name="notes",
        description="View a member's internal staff notes."
    )
    async def notes(
        self,
        interaction: discord.Interaction,
        member: discord.Member
    ):
        if not await self.check_access(interaction):
            return

        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute("""
                SELECT added_by, division, note, timestamp
                FROM division_notes
                WHERE guild_id = ? AND user_id = ?
                ORDER BY timestamp DESC
            """, (interaction.guild.id, member.id))

            rows = await cursor.fetchall()

        embed = discord.Embed(
            title="Internal Staff Notes",
            description=f"Member: {member.mention}",
            colour=discord.Colour.blurple()
        )

        if not rows:
            embed.description += "\n\nNo staff notes recorded."
        else:
            embed.add_field(
                name="Total Notes",
                value=str(len(rows)),
                inline=False
            )

            for issuer, division, note, timestamp in rows[:10]:
                embed.add_field(
                    name=f"{division.replace('_', ' ').title()} • <t:{int(timestamp)}:R>",
                    value=f"**Added by:** <@{issuer}>\n{note[:800]}",
                    inline=False
                )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(StaffRecords(bot))
