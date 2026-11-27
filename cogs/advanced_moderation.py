
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import config
import re
from datetime import datetime, timezone


URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


async def send_log(guild: discord.Guild, title: str, description: str):
    """Send an event to the configured server log channel."""

    async with aiosqlite.connect(config.DATABASE) as db:
        async with db.execute(
            "SELECT log_channel FROM guild_config WHERE guild_id = ?",
            (guild.id,)
        ) as cursor:
            row = await cursor.fetchone()

    if not row or not row[0]:
        return

    channel = guild.get_channel(row[0])
    if channel is None:
        return

    embed = discord.Embed(
        title=title,
        description=description[:4000],
        colour=discord.Colour.dark_purple(),
        timestamp=discord.utils.utcnow()
    )

    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


async def get_case(guild_id: int, case_id: str):
    async with aiosqlite.connect(config.DATABASE) as db:
        async with db.execute(
            """
            SELECT case_id, user_id, moderator_id, action, reason, timestamp
            FROM cases
            WHERE guild_id = ? AND case_id = ?
            """,
            (guild_id, case_id.upper())
        ) as cursor:
            return await cursor.fetchone()


class AdvancedModeration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --------------------------------------------------
    # ADVANCED PURGE
    # --------------------------------------------------

    @app_commands.command(
        name="purge",
        description="Delete messages using advanced filters"
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(
        amount="Maximum number of messages to delete",
        member="Only delete messages from this member",
        bots_only="Only delete messages sent by bots",
        links_only="Only delete messages containing links",
        embeds_only="Only delete messages containing embeds",
        contains="Only delete messages containing this text"
    )
    async def purge(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
        member: discord.Member = None,
        bots_only: bool = False,
        links_only: bool = False,
        embeds_only: bool = False,
        contains: str = None
    ):
        channel = interaction.channel

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message(
                "Purge can only be used in a text channel or thread.",
                ephemeral=True
            )

        if not channel.permissions_for(interaction.guild.me).manage_messages:
            return await interaction.response.send_message(
                "I need Manage Messages permission in this channel.",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        has_filters = any([
            member is not None,
            bots_only,
            links_only,
            embeds_only,
            contains is not None
        ])

        matched = [0]

        def message_matches(message: discord.Message):
            if member and message.author.id != member.id:
                return False

            if bots_only and not message.author.bot:
                return False

            if links_only and not URL_PATTERN.search(message.content or ""):
                return False

            if embeds_only and not message.embeds:
                return False

            if contains and contains.casefold() not in (
                message.content or ""
            ).casefold():
                return False

            if matched[0] >= amount:
                return False

            matched[0] += 1
            return True

        try:
            deleted = await channel.purge(
                limit=1000 if has_filters else amount,
                check=message_matches,
                bulk=True,
                reason=f"Purged by {interaction.user}"
            )
        except discord.Forbidden:
            return await interaction.followup.send(
                "I don't have permission to delete messages here.",
                ephemeral=True
            )
        except discord.HTTPException as error:
            return await interaction.followup.send(
                f"Discord couldn't complete the purge: {error}",
                ephemeral=True
            )

        filter_names = []

        if member:
            filter_names.append(f"Member: {member}")
        if bots_only:
            filter_names.append("Bots only")
        if links_only:
            filter_names.append("Links only")
        if embeds_only:
            filter_names.append("Embeds only")
        if contains:
            filter_names.append(f"Contains: {contains}")

        filter_text = ", ".join(filter_names) if filter_names else "None"

        await interaction.followup.send(
            f"🧹 Deleted **{len(deleted)}** messages in {channel.mention}.\n"
            f"**Filters:** {filter_text}",
            ephemeral=True
        )

        await send_log(
            interaction.guild,
            "🧹 Messages Purged",
            f"**Moderator:** {interaction.user.mention}\n"
            f"**Channel:** {channel.mention}\n"
            f"**Deleted:** {len(deleted)}\n"
            f"**Filters:** {filter_text}"
        )

    # --------------------------------------------------
    # CASE LOOKUP
    # --------------------------------------------------

    @app_commands.command(
        name="case",
        description="View a moderation case"
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(case_id="The case reference, e.g. TEA-12345")
    async def case(
        self,
        interaction: discord.Interaction,
        case_id: str
    ):
        row = await get_case(interaction.guild.id, case_id)

        if not row:
            return await interaction.response.send_message(
                "I couldn't find that case.",
                ephemeral=True
            )

        case_ref, user_id, moderator_id, action, reason, timestamp = row

        embed = discord.Embed(
            title=f"Moderation Case — {case_ref}",
            colour=discord.Colour.orange()
        )

        embed.add_field(
            name="Member",
            value=f"<@{user_id}> (`{user_id}`)",
            inline=False
        )
        embed.add_field(
            name="Moderator",
            value=f"<@{moderator_id}>",
            inline=True
        )
        embed.add_field(
            name="Action",
            value=action.title(),
            inline=True
        )
        embed.add_field(
            name="Reason",
            value=reason or "No reason provided",
            inline=False
        )
        embed.add_field(
            name="Date",
            value=f"<t:{int(timestamp)}:F>",
            inline=False
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # --------------------------------------------------
    # MEMBER CASE HISTORY
    # --------------------------------------------------

    @app_commands.command(
        name="cases",
        description="View a member's moderation history"
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    async def cases(
        self,
        interaction: discord.Interaction,
        member: discord.Member
    ):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute(
                """
                SELECT case_id, action, reason, moderator_id, timestamp
                FROM cases
                WHERE guild_id = ? AND user_id = ?
                ORDER BY timestamp DESC
                LIMIT 15
                """,
                (interaction.guild.id, member.id)
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return await interaction.response.send_message(
                f"{member.mention} has no recorded moderation cases.",
                ephemeral=True
            )

        embed = discord.Embed(
            title=f"Moderation History — {member}",
            colour=discord.Colour.orange()
        )

        for case_id, action, reason, moderator_id, timestamp in rows:
            embed.add_field(
                name=f"{case_id} | {action.title()}",
                value=(
                    f"**Reason:** {reason or 'No reason provided'}\n"
                    f"**Moderator:** <@{moderator_id}>\n"
                    f"**Date:** <t:{int(timestamp)}:R>"
                ),
                inline=False
            )

        embed.set_footer(text="Showing the latest 15 cases")

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # --------------------------------------------------
    # MESSAGE EDIT LOGS
    # --------------------------------------------------

    @commands.Cog.listener()
    async def on_message_edit(
        self,
        before: discord.Message,
        after: discord.Message
    ):
        if before.guild is None:
            return

        if before.author.bot:
            return

        if before.content == after.content:
            return

        old_content = before.content or "No cached message content"
        new_content = after.content or "No message content"

        await send_log(
            before.guild,
            "✏️ Message Edited",
            f"**Author:** {before.author.mention}\n"
            f"**Channel:** {before.channel.mention}\n"
            f"**Before:**\n{old_content[:1200]}\n\n"
            f"**After:**\n{new_content[:1200]}\n"
            f"[Jump to message]({after.jump_url})"
        )

    # --------------------------------------------------
    # MESSAGE DELETE LOGS
    # --------------------------------------------------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None:
            return

        if message.author and message.author.bot:
            return

        author = (
            message.author.mention
            if message.author
            else "Unknown author"
        )

        content = message.content or "No cached message content"

        await send_log(
            message.guild,
            "🗑️ Message Deleted",
            f"**Author:** {author}\n"
            f"**Channel:** {message.channel.mention}\n"
            f"**Content:**\n{content[:2500]}"
        )

    # --------------------------------------------------
    # MEMBER JOIN LOGS
    # --------------------------------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await send_log(
            member.guild,
            "📥 Member Joined",
            f"**Member:** {member.mention}\n"
            f"**Account:** {member}\n"
            f"**ID:** `{member.id}`\n"
            f"**Account Created:** <t:{int(member.created_at.timestamp())}:F>"
        )

    # --------------------------------------------------
    # MEMBER LEAVE LOGS
    # --------------------------------------------------

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await send_log(
            member.guild,
            "📤 Member Left",
            f"**Member:** {member}\n"
            f"**ID:** `{member.id}`"
        )

    # --------------------------------------------------
    # ROLE CHANGE LOGS
    # --------------------------------------------------

    @commands.Cog.listener()
    async def on_member_update(
        self,
        before: discord.Member,
        after: discord.Member
    ):
        if before.guild is None:
            return

        before_roles = {role.id: role for role in before.roles}
        after_roles = {role.id: role for role in after.roles}

        added = [
            role for role_id, role in after_roles.items()
            if role_id not in before_roles and role.id != after.guild.id
        ]

        removed = [
            role for role_id, role in before_roles.items()
            if role_id not in after_roles and role.id != before.guild.id
        ]

        if not added and not removed:
            return

        changes = []

        if added:
            changes.append(
                "**Added:** " + ", ".join(role.mention for role in added)
            )

        if removed:
            changes.append(
                "**Removed:** " + ", ".join(role.name for role in removed)
            )

        await send_log(
            after.guild,
            "🏷️ Member Roles Updated",
            f"**Member:** {after.mention}\n"
            + "\n".join(changes)
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AdvancedModeration(bot))
