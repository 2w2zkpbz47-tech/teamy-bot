
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import config


async def has_division_role(member, division):
    if member.id == member.guild.owner_id:
        return True

    async with aiosqlite.connect(config.DATABASE) as db:
        async with db.execute("""
            SELECT role_id
            FROM staff_role_config
            WHERE guild_id = ? AND division = ?
        """, (member.guild.id, division)) as cursor:
            role_ids = {row[0] for row in await cursor.fetchall()}

    return any(role.id in role_ids for role in member.roles)


class DivisionDashboard(discord.ui.View):
    def __init__(self, division):
        super().__init__(timeout=300)
        self.division = division

    async def interaction_check(self, interaction):
        if not await has_division_role(interaction.user, self.division):
            await interaction.response.send_message(
                "You don't have permission to use this division panel.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="Open tickets",
        emoji="🎫",
        style=discord.ButtonStyle.primary
    )
    async def open_tickets(self, interaction, button):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT channel_id, user_id, category, claimed_by
                FROM tickets
                WHERE guild_id = ? AND closed = 0
                ORDER BY created_at ASC
                LIMIT 15
            """, (interaction.guild_id,)) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return await interaction.response.send_message(
                "There are currently no open tickets.",
                ephemeral=True
            )

        lines = []

        for channel_id, user_id, category, claimed_by in rows:
            channel = interaction.guild.get_channel(channel_id)
            channel_text = channel.mention if channel else f"Deleted channel ({channel_id})"
            claim_text = f"<@{claimed_by}>" if claimed_by else "Unclaimed"

            lines.append(
                f"**{category}** — {channel_text}\n"
                f"Member: <@{user_id}> | Claimed: {claim_text}"
            )

        embed = discord.Embed(
            title="Open Support Tickets",
            description="\n\n".join(lines),
            colour=discord.Colour.blurple()
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @discord.ui.button(
        label="Claim this ticket",
        emoji="✋",
        style=discord.ButtonStyle.success
    )
    async def claim_ticket(self, interaction, button):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT user_id, claimed_by, closed
                FROM tickets
                WHERE channel_id = ? AND guild_id = ?
            """, (interaction.channel_id, interaction.guild_id)) as cursor:
                ticket = await cursor.fetchone()

            if not ticket or ticket[2]:
                return await interaction.response.send_message(
                    "This channel is not an open ticket.",
                    ephemeral=True
                )

            if ticket[1] and ticket[1] != interaction.user.id:
                return await interaction.response.send_message(
                    f"This ticket is already claimed by <@{ticket[1]}>.",
                    ephemeral=True
                )

            await db.execute("""
                UPDATE tickets
                SET claimed_by = ?
                WHERE channel_id = ? AND closed = 0
            """, (interaction.user.id, interaction.channel_id))

            await db.execute("""
                INSERT INTO member_stats
                (guild_id, user_id, tickets_handled)
                VALUES (?, ?, 1)
                ON CONFLICT(guild_id, user_id)
                DO UPDATE SET tickets_handled = tickets_handled + 1
            """, (interaction.guild_id, interaction.user.id))

            await db.commit()

        await interaction.response.send_message(
            f"✋ This ticket has been claimed by {interaction.user.mention}."
        )

    @discord.ui.button(
        label="Refresh",
        emoji="🔄",
        style=discord.ButtonStyle.secondary
    )
    async def refresh(self, interaction, button):
        await interaction.response.send_message(
            "Your dashboard is ready. Use the buttons to access your division tools.",
            ephemeral=True
        )


class OperationsDashboard(DivisionDashboard):
    def __init__(self):
        super().__init__("operations_support")

    @discord.ui.button(
        label="Active teams",
        emoji="👥",
        style=discord.ButtonStyle.primary
    )
    async def active_teams(self, interaction, button):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT team_id, thread_id, voice_id, mode, members
                FROM active_teams
                WHERE guild_id = ?
                ORDER BY created_at DESC
                LIMIT 15
            """, (interaction.guild_id,)) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return await interaction.response.send_message(
                "There are no active teams recorded.",
                ephemeral=True
            )

        lines = []

        for team_id, thread_id, voice_id, mode, members in rows:
            thread = interaction.guild.get_channel(thread_id)
            voice = interaction.guild.get_channel(voice_id) if voice_id else None

            lines.append(
                f"**Team:** `{team_id}`\n"
                f"**Mode:** {mode}\n"
                f"**Chat:** {thread.mention if thread else 'Unavailable'}\n"
                f"**Voice:** {voice.mention if voice else 'Not created'}"
            )

        embed = discord.Embed(
            title="Teamy Operations — Active Teams",
            description="\n\n".join(lines),
            colour=discord.Colour.blurple()
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @discord.ui.button(
        label="Team Finder information",
        emoji="🔍",
        style=discord.ButtonStyle.secondary
    )
    async def team_information(self, interaction, button):
        await interaction.response.send_message(
            "Use this dashboard to monitor active teams and access "
            "the open support tickets relating to Team Finder.\n\n"
            "Team Finder support requests currently appear in their "
            "respective team channels.",
            ephemeral=True
        )


class DivisionPanels(commands.Cog):
    opsupport = app_commands.Group(
        name="opsupport",
        description="Teamy Operations Support tools"
    )

    ticketsupport = app_commands.Group(
        name="ticketsupport",
        description="Ticket Support tools"
    )

    def __init__(self, bot):
        self.bot = bot

    @opsupport.command(
        name="panel",
        description="Open the Teamy Operations Support dashboard"
    )
    async def operations_panel(self, interaction):
        if not await has_division_role(
            interaction.user, "operations_support"
        ):
            return await interaction.response.send_message(
                "You aren't a member of Teamy Operations Support.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="Teamy | Operations Support",
            description=(
                "Welcome to the Operations Support dashboard.\n\n"
                "Your team assists with Team Finder, team issues "
                "and member support."
            ),
            colour=discord.Colour.blurple()
        )

        embed.add_field(
            name="Available tools",
            value=(
                "👥 View active teams\n"
                "🎫 View and claim support tickets\n"
                "🔍 Team Finder information"
            ),
            inline=False
        )

        await interaction.response.send_message(
            embed=embed,
            view=OperationsDashboard(),
            ephemeral=True
        )

    @ticketsupport.command(
        name="panel",
        description="Open the Ticket Support dashboard"
    )
    async def ticket_panel(self, interaction):
        if not await has_division_role(
            interaction.user, "ticket_support"
        ):
            return await interaction.response.send_message(
                "You aren't a member of Ticket Support.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="Teamy | Ticket Support",
            description=(
                "Welcome to the Ticket Support dashboard.\n\n"
                "Manage incoming tickets, claim conversations "
                "and help members."
            ),
            colour=discord.Colour.blurple()
        )

        embed.add_field(
            name="Available tools",
            value=(
                "🎫 View open tickets\n"
                "✋ Claim tickets\n"
                "🔄 Refresh your dashboard"
            ),
            inline=False
        )

        await interaction.response.send_message(
            embed=embed,
            view=DivisionDashboard("ticket_support"),
            ephemeral=True
        )

    @ticketsupport.command(
        name="claim",
        description="Claim the ticket in the current channel"
    )
    async def claim(self, interaction):
        if not await has_division_role(
            interaction.user, "ticket_support"
        ):
            return await interaction.response.send_message(
                "You aren't a member of Ticket Support.",
                ephemeral=True
            )

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("""
                SELECT claimed_by, closed
                FROM tickets
                WHERE channel_id = ? AND guild_id = ?
            """, (interaction.channel_id, interaction.guild_id)) as cursor:
                ticket = await cursor.fetchone()

            if not ticket or ticket[1]:
                return await interaction.response.send_message(
                    "This isn't an open ticket.",
                    ephemeral=True
                )

            if ticket[0] and ticket[0] != interaction.user.id:
                return await interaction.response.send_message(
                    f"This ticket is already claimed by <@{ticket[0]}>.",
                    ephemeral=True
                )

            await db.execute("""
                UPDATE tickets SET claimed_by = ?
                WHERE channel_id = ?
            """, (interaction.user.id, interaction.channel_id))

            await db.execute("""
                INSERT INTO member_stats
                (guild_id, user_id, tickets_handled)
                VALUES (?, ?, 1)
                ON CONFLICT(guild_id, user_id)
                DO UPDATE SET tickets_handled = tickets_handled + 1
            """, (interaction.guild_id, interaction.user.id))

            await db.commit()

        await interaction.response.send_message(
            f"🎫 Ticket claimed by {interaction.user.mention}."
        )


async def setup(bot):
    await bot.add_cog(DivisionPanels(bot))
