
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import config
import re
import time


class CommunityFeatures(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.afk_users = {}
        self.sticky_cache = {}

    async def cog_load(self):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS afk (
                    guild_id INTEGER,
                    user_id INTEGER,
                    reason TEXT,
                    timestamp INTEGER,
                    PRIMARY KEY (guild_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS sticky_messages (
                    guild_id INTEGER,
                    channel_id INTEGER,
                    message_id INTEGER,
                    content TEXT,
                    PRIMARY KEY (guild_id, channel_id)
                );

                CREATE TABLE IF NOT EXISTS reaction_roles (
                    guild_id INTEGER,
                    channel_id INTEGER,
                    message_id INTEGER,
                    emoji TEXT,
                    role_id INTEGER,
                    PRIMARY KEY (guild_id, message_id, emoji)
                );

                CREATE TABLE IF NOT EXISTS custom_commands (
                    guild_id INTEGER,
                    trigger TEXT,
                    response TEXT,
                    PRIMARY KEY (guild_id, trigger)
                );

                CREATE TABLE IF NOT EXISTS suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    user_id INTEGER,
                    channel_id INTEGER,
                    message_id INTEGER,
                    thread_id INTEGER,
                    suggestion TEXT,
                    status TEXT DEFAULT 'pending',
                    timestamp INTEGER
                );

                CREATE TABLE IF NOT EXISTS suggestion_config (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER
                );
            """)
            await db.commit()

    # --------------------------------------------------
    # AFK SYSTEM
    # --------------------------------------------------

    @app_commands.command(name="afk", description="Set yourself as AFK")
    async def afk(self, interaction: discord.Interaction, reason: str = "AFK"):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT OR REPLACE INTO afk
                (guild_id, user_id, reason, timestamp)
                VALUES (?, ?, ?, ?)
            """, (interaction.guild.id, interaction.user.id, reason, int(time.time())))
            await db.commit()

        await interaction.response.send_message(
            f"💤 You are now AFK: **{reason}**",
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        # Remove AFK when user speaks
        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute(
                "SELECT reason FROM afk WHERE guild_id = ? AND user_id = ?",
                (message.guild.id, message.author.id)
            )
            result = await cursor.fetchone()

            if result:
                await db.execute(
                    "DELETE FROM afk WHERE guild_id = ? AND user_id = ?",
                    (message.guild.id, message.author.id)
                )
                await db.commit()

                await message.channel.send(
                    f"👋 Welcome back {message.author.mention}! "
                    f"You were AFK: **{result[0]}**"
                )

            # Check mentions
            for member in message.mentions:
                cursor = await db.execute(
                    "SELECT reason, timestamp FROM afk WHERE guild_id = ? AND user_id = ?",
                    (message.guild.id, member.id)
                )
                afk_data = await cursor.fetchone()

                if afk_data:
                    duration = int(time.time()) - afk_data[1]
                    minutes = duration // 60

                    await message.reply(
                        f"💤 **{member.display_name}** is AFK: "
                        f"{afk_data[0]} ({minutes} minutes)",
                        mention_author=False
                    )

        # Custom commands
        content = message.content.strip()

        if content.startswith("!"):
            trigger = content[1:].split(" ", 1)[0].lower()

            async with aiosqlite.connect(config.DATABASE) as db:
                cursor = await db.execute(
                    "SELECT response FROM custom_commands "
                    "WHERE guild_id = ? AND trigger = ?",
                    (message.guild.id, trigger)
                )
                result = await cursor.fetchone()

            if result:
                response = result[0]
                response = response.replace("{user}", message.author.mention)
                response = response.replace("{server}", message.guild.name)

                await message.channel.send(
                    response,
                    allowed_mentions=discord.AllowedMentions.none()
                )

        # Sticky messages
        await self.check_sticky(message)

    # --------------------------------------------------
    # STICKY MESSAGES
    # --------------------------------------------------

    sticky = app_commands.Group(
        name="sticky",
        description="Manage sticky messages"
    )

    @sticky.command(name="set", description="Set a sticky message")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_set(
        self,
        interaction: discord.Interaction,
        message: str
    ):
        channel = interaction.channel

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT OR REPLACE INTO sticky_messages
                (guild_id, channel_id, message_id, content)
                VALUES (?, ?, ?, ?)
            """, (interaction.guild.id, channel.id, 0, message))
            await db.commit()

        sticky_message = await channel.send(message)

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                UPDATE sticky_messages
                SET message_id = ?
                WHERE guild_id = ? AND channel_id = ?
            """, (sticky_message.id, interaction.guild.id, channel.id))
            await db.commit()

        await interaction.response.send_message(
            "📌 Sticky message has been set!",
            ephemeral=True
        )

    @sticky.command(name="remove", description="Remove the sticky message")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_remove(self, interaction: discord.Interaction):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                "DELETE FROM sticky_messages WHERE guild_id = ? AND channel_id = ?",
                (interaction.guild.id, interaction.channel.id)
            )
            await db.commit()

        await interaction.response.send_message(
            "🗑️ Sticky message removed.",
            ephemeral=True
        )

    async def check_sticky(self, message):
        if message.author.bot:
            return

        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute(
                "SELECT message_id, content FROM sticky_messages "
                "WHERE guild_id = ? AND channel_id = ?",
                (message.guild.id, message.channel.id)
            )
            result = await cursor.fetchone()

        if not result:
            return

        old_message_id, content = result

        # Only repost after five human messages
        key = (message.guild.id, message.channel.id)
        self.sticky_cache[key] = self.sticky_cache.get(key, 0) + 1

        if self.sticky_cache[key] < 5:
            return

        self.sticky_cache[key] = 0

        # Delete old sticky message if possible
        if old_message_id:
            try:
                old_message = await message.channel.fetch_message(old_message_id)
                await old_message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        new_message = await message.channel.send(content)

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                "UPDATE sticky_messages SET message_id = ? "
                "WHERE guild_id = ? AND channel_id = ?",
                (new_message.id, message.guild.id, message.channel.id)
            )
            await db.commit()

    # --------------------------------------------------
    # REACTION ROLES
    # --------------------------------------------------

    reactionrole = app_commands.Group(
        name="reactionrole",
        description="Manage reaction roles"
    )

    @reactionrole.command(name="add", description="Add a reaction role")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reactionrole_add(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str,
        role: discord.Role
    ):
        try:
            msg_id = int(message_id)
            message = await interaction.channel.fetch_message(msg_id)
            await message.add_reaction(emoji)
        except (ValueError, discord.NotFound):
            await interaction.response.send_message(
                "❌ Invalid message ID or message not found.",
                ephemeral=True
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "❌ I couldn't add that reaction. Check the emoji.",
                ephemeral=True
            )
            return

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT OR REPLACE INTO reaction_roles
                (guild_id, channel_id, message_id, emoji, role_id)
                VALUES (?, ?, ?, ?, ?)
            """, (
                interaction.guild.id,
                interaction.channel.id,
                msg_id,
                str(emoji),
                role.id
            ))
            await db.commit()

        await interaction.response.send_message(
            f"✅ Reaction role configured: {emoji} → {role.mention}",
            ephemeral=True
        )

    @reactionrole.command(name="remove", description="Remove a reaction role")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reactionrole_remove(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str
    ):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                "DELETE FROM reaction_roles "
                "WHERE guild_id = ? AND message_id = ? AND emoji = ?",
                (interaction.guild.id, int(message_id), str(emoji))
            )
            await db.commit()

        await interaction.response.send_message(
            "🗑️ Reaction role removed.",
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.member is None or payload.member.bot:
            return

        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute(
                "SELECT role_id FROM reaction_roles "
                "WHERE guild_id = ? AND message_id = ? AND emoji = ?",
                (payload.guild_id, payload.message_id, str(payload.emoji))
            )
            result = await cursor.fetchone()

        if not result:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        role = guild.get_role(result[0])
        if role:
            try:
                await payload.member.add_roles(role, reason="Reaction role")
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.member and payload.member.bot:
            return

        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute(
                "SELECT role_id FROM reaction_roles "
                "WHERE guild_id = ? AND message_id = ? AND emoji = ?",
                (payload.guild_id, payload.message_id, str(payload.emoji))
            )
            result = await cursor.fetchone()

        if not result:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        role = guild.get_role(result[0])

        if member and role:
            try:
                await member.remove_roles(role, reason="Reaction role removed")
            except discord.Forbidden:
                pass

    # --------------------------------------------------
    # SELF ROLES
    # --------------------------------------------------

    @app_commands.command(name="selfroles", description="Choose your own roles")
    async def selfroles(self, interaction: discord.Interaction):
        roles = [
            role for role in interaction.guild.roles
            if role.name.startswith("Self:")
            and not role.is_default()
            and role < interaction.guild.me.top_role
        ]

        if not roles:
            await interaction.response.send_message(
                "No self-assignable roles are configured. "
                "Create roles starting with `Self:`.",
                ephemeral=True
            )
            return

        options = [
            discord.SelectOption(
                label=role.name.replace("Self:", "").strip()[:100],
                value=str(role.id)
            )
            for role in roles[:25]
        ]

        class SelfRoleSelect(discord.ui.Select):
            def __init__(self):
                super().__init__(
                    placeholder="Choose your roles...",
                    min_values=0,
                    max_values=len(options),
                    options=options
                )

            async def callback(self, select_interaction):
                selected_ids = [int(value) for value in self.values]
                selected_roles = [
                    role for role in roles
                    if role.id in selected_ids
                ]

                current_roles = [
                    role for role in interaction.user.roles
                    if role in roles
                ]

                add_roles = [
                    role for role in selected_roles
                    if role not in current_roles
                ]

                remove_roles = [
                    role for role in current_roles
                    if role not in selected_roles
                ]

                try:
                    if add_roles:
                        await interaction.user.add_roles(*add_roles)

                    if remove_roles:
                        await interaction.user.remove_roles(*remove_roles)

                    await select_interaction.response.send_message(
                        "✅ Your roles have been updated!",
                        ephemeral=True
                    )
                except discord.Forbidden:
                    await select_interaction.response.send_message(
                        "❌ I don't have permission to manage these roles.",
                        ephemeral=True
                    )

        view = discord.ui.View(timeout=120)
        view.add_item(SelfRoleSelect())

        await interaction.response.send_message(
            "Select the roles you want:",
            view=view,
            ephemeral=True
        )

    # --------------------------------------------------
    # CUSTOM COMMANDS
    # --------------------------------------------------

    custom = app_commands.Group(
        name="custom",
        description="Manage custom server commands"
    )

    @custom.command(name="add", description="Create a custom command")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def custom_add(
        self,
        interaction: discord.Interaction,
        trigger: str,
        response: str
    ):
        trigger = trigger.lower().strip()

        if not re.fullmatch(r"[a-z0-9_-]{1,32}", trigger):
            await interaction.response.send_message(
                "❌ Trigger must contain only letters, numbers, "
                "hyphens or underscores.",
                ephemeral=True
            )
            return

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT OR REPLACE INTO custom_commands
                (guild_id, trigger, response)
                VALUES (?, ?, ?)
            """, (interaction.guild.id, trigger, response))
            await db.commit()

        await interaction.response.send_message(
            f"✅ Custom command `!{trigger}` created!",
            ephemeral=True
        )

    @custom.command(name="remove", description="Remove a custom command")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def custom_remove(
        self,
        interaction: discord.Interaction,
        trigger: str
    ):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                "DELETE FROM custom_commands "
                "WHERE guild_id = ? AND trigger = ?",
                (interaction.guild.id, trigger.lower())
            )
            await db.commit()

        await interaction.response.send_message(
            f"🗑️ Custom command `!{trigger}` removed.",
            ephemeral=True
        )

    @custom.command(name="list", description="View custom commands")
    async def custom_list(self, interaction: discord.Interaction):
        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute(
                "SELECT trigger FROM custom_commands WHERE guild_id = ?",
                (interaction.guild.id,)
            )
            results = await cursor.fetchall()

        if not results:
            await interaction.response.send_message(
                "There are no custom commands.",
                ephemeral=True
            )
            return

        commands_list = "\n".join(
            f"`!{row[0]}`" for row in results
        )

        await interaction.response.send_message(
            f"**Custom Commands**\n{commands_list}",
            ephemeral=True
        )

    # --------------------------------------------------
    # SUGGESTIONS
    # --------------------------------------------------

    @app_commands.command(name="suggest", description="Submit a suggestion")
    async def suggest(self, interaction: discord.Interaction, suggestion: str):
        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute(
                "SELECT channel_id FROM suggestion_config WHERE guild_id = ?",
                (interaction.guild.id,)
            )
            result = await cursor.fetchone()

        if not result:
            await interaction.response.send_message(
                "❌ Suggestions haven't been configured yet.",
                ephemeral=True
            )
            return

        channel = interaction.guild.get_channel(result[0])

        if not channel:
            await interaction.response.send_message(
                "❌ The suggestion channel no longer exists.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="💡 New Suggestion",
            description=suggestion,
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Suggested by {interaction.user}")

        suggestion_message = await channel.send(embed=embed)
        await suggestion_message.add_reaction("👍")
        await suggestion_message.add_reaction("👎")

        thread = await suggestion_message.create_thread(
            name=f"Suggestion discussion - {interaction.user.name}"[:100]
        )

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT INTO suggestions
                (guild_id, user_id, channel_id, message_id, thread_id,
                 suggestion, status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """, (
                interaction.guild.id,
                interaction.user.id,
                channel.id,
                suggestion_message.id,
                thread.id,
                suggestion,
                int(time.time())
            ))
            await db.commit()

        await interaction.response.send_message(
            f"✅ Your suggestion has been submitted in {channel.mention}!",
            ephemeral=True
        )

    suggestions = app_commands.Group(
        name="suggestions",
        description="Manage the suggestion system"
    )

    @suggestions.command(name="setchannel", description="Set the suggestion channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def suggestions_setchannel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                INSERT OR REPLACE INTO suggestion_config
                (guild_id, channel_id)
                VALUES (?, ?)
            """, (interaction.guild.id, channel.id))
            await db.commit()

        await interaction.response.send_message(
            f"✅ Suggestions will now be sent to {channel.mention}.",
            ephemeral=True
        )

    @suggestions.command(name="approve", description="Approve a suggestion")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def suggestions_approve(
        self,
        interaction: discord.Interaction,
        suggestion_id: int
    ):
        await self.update_suggestion(interaction, suggestion_id, "approved")

    @suggestions.command(name="deny", description="Deny a suggestion")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def suggestions_deny(
        self,
        interaction: discord.Interaction,
        suggestion_id: int
    ):
        await self.update_suggestion(interaction, suggestion_id, "denied")

    async def update_suggestion(
        self,
        interaction,
        suggestion_id,
        status
    ):
        async with aiosqlite.connect(config.DATABASE) as db:
            cursor = await db.execute(
                "SELECT message_id, channel_id, thread_id, status "
                "FROM suggestions WHERE id = ? AND guild_id = ?",
                (suggestion_id, interaction.guild.id)
            )
            result = await cursor.fetchone()

            if not result:
                await interaction.response.send_message(
                    "❌ Suggestion not found.",
                    ephemeral=True
                )
                return

            message_id, channel_id, thread_id, old_status = result

            if old_status != "pending":
                await interaction.response.send_message(
                    "❌ This suggestion has already been reviewed.",
                    ephemeral=True
                )
                return

            await db.execute(
                "UPDATE suggestions SET status = ? WHERE id = ?",
                (status, suggestion_id)
            )
            await db.commit()

        channel = interaction.guild.get_channel(channel_id)

        if channel:
            try:
                message = await channel.fetch_message(message_id)

                embed = message.embeds[0] if message.embeds else discord.Embed()

                embed.color = (
                    discord.Color.green()
                    if status == "approved"
                    else discord.Color.red()
                )

                embed.add_field(
                    name="Status",
                    value=f"**{status.title()}** by {interaction.user.mention}",
                    inline=False
                )

                await message.edit(embed=embed)

            except discord.NotFound:
                pass

        thread = interaction.guild.get_thread(thread_id)

        if thread:
            try:
                await thread.send(
                    f"📢 This suggestion has been **{status}** "
                    f"by {interaction.user.mention}."
                )
            except discord.Forbidden:
                pass

        await interaction.response.send_message(
            f"✅ Suggestion #{suggestion_id} has been {status}.",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(CommunityFeatures(bot))
