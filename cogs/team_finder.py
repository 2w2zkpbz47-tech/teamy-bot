import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Select
import aiosqlite
import asyncio
import json
from datetime import datetime, timezone
import config
from utils.embeds import create_embed
from utils.database import get_config

class TeamFinder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup-panel", description="Post the Team Finder panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_panel(self, interaction: discord.Interaction):
        embed = create_embed(
            "🔍 Teamy — Find Your Squad",
            "**Looking for teammates?**\n\n"
            "🔍 **Find Team** → Answer a few questions and get matched\n"
            "🎫 **Token Hunt** → Instant match (no questions)\n\n"
            "Click a button below to start!"
        )
        view = MainPanelView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Team Finder panel posted!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TeamFinder(bot))
    bot.add_view(MainPanelView())
    bot.add_view(TeamPanelView())

# -------------------- Views --------------------

class MainPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Find Team", style=discord.ButtonStyle.primary, emoji="🔍", custom_id="tf:find_team")
    async def find_team(self, interaction: discord.Interaction, button: Button):
        view = GameModeView()
        await interaction.response.send_message(
            embed=create_embed("🔍 Find Team", "Select your **Game Mode**:"),
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="Token Hunt", style=discord.ButtonStyle.success, emoji="🎫", custom_id="tf:token_hunt")
    async def token_hunt(self, interaction: discord.Interaction, button: Button):
        await add_to_queue(interaction.user.id, interaction.guild.id, "Token Hunt", False, "Any", "token")
        await interaction.response.send_message(
            embed=create_embed("🎫 Token Hunt", "You joined the **Token Hunt** pool!\nSearching for teammates...", config.COLOR_TOKEN),
            ephemeral=True
        )
        await try_match(interaction.guild, interaction.user, "Token Hunt", False, "Any", "token")

class GameModeView(View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.select(
        placeholder="Choose Game Mode...",
        options=[
            discord.SelectOption(label="Zero Build", value="Zero Build", emoji="🏙️"),
            discord.SelectOption(label="Build", value="Build", emoji="🏗️"),
            discord.SelectOption(label="Reload", value="Reload", emoji="🔄"),
        ]
    )
    async def select_mode(self, interaction: discord.Interaction, select: Select):
        mode = select.values[0]
        view = RankedView(mode)
        await interaction.response.edit_message(
            embed=create_embed("🔍 Find Team", f"**Mode:** {mode}\n\nIs this **Ranked**?"),
            view=view
        )

class RankedView(View):
    def __init__(self, mode: str):
        super().__init__(timeout=60)
        self.mode = mode

    @discord.ui.button(label="Yes - Ranked", style=discord.ButtonStyle.success, emoji="🏆")
    async def ranked_yes(self, interaction: discord.Interaction, button: Button):
        view = RankSelectView(self.mode)
        await interaction.response.edit_message(
            embed=create_embed("🔍 Find Team", f"**Mode:** {self.mode}\n**Ranked:** Yes\n\nSelect your **Rank**:"),
            view=view
        )

    @discord.ui.button(label="No - Casual", style=discord.ButtonStyle.secondary, emoji="🎮")
    async def ranked_no(self, interaction: discord.Interaction, button: Button):
        view = LevelSelectView(self.mode)
        await interaction.response.edit_message(
            embed=create_embed("🔍 Find Team", f"**Mode:** {self.mode}\n**Ranked:** No\n\nSelect your **Level range**:"),
            view=view
        )

class RankSelectView(View):
    def __init__(self, mode: str):
        super().__init__(timeout=60)
        self.mode = mode

    @discord.ui.select(
        placeholder="Select your Rank...",
        options=[
            discord.SelectOption(label="Bronze", value="Bronze", emoji="🥉"),
            discord.SelectOption(label="Silver", value="Silver", emoji="🥈"),
            discord.SelectOption(label="Gold", value="Gold", emoji="🥇"),
            discord.SelectOption(label="Platinum", value="Platinum", emoji="💎"),
            discord.SelectOption(label="Diamond", value="Diamond", emoji="💠"),
            discord.SelectOption(label="Elite", value="Elite", emoji="🔥"),
            discord.SelectOption(label="Champion", value="Champion", emoji="👑"),
            discord.SelectOption(label="Unreal", value="Unreal", emoji="🌌"),
        ]
    )
    async def select_rank(self, interaction: discord.Interaction, select: Select):
        rank = select.values[0]
        await add_to_queue(interaction.user.id, interaction.guild.id, self.mode, True, rank)
        await interaction.response.edit_message(
            embed=create_embed("✅ Joined Queue", f"**Mode:** {self.mode}\n**Rank:** {rank}\n\nSearching for teammates...", config.COLOR_SUCCESS),
            view=None
        )
        await try_match(interaction.guild, interaction.user, self.mode, True, rank)

class LevelSelectView(View):
    def __init__(self, mode: str):
        super().__init__(timeout=60)
        self.mode = mode

    @discord.ui.select(
        placeholder="Select Level Range...",
        options=[
            discord.SelectOption(label="1 - 50", value="1-50"),
            discord.SelectOption(label="51 - 100", value="51-100"),
            discord.SelectOption(label="101 - 200", value="101-200"),
            discord.SelectOption(label="201 - 500", value="201-500"),
            discord.SelectOption(label="500+", value="500+"),
        ]
    )
    async def select_level(self, interaction: discord.Interaction, select: Select):
        level = select.values[0]
        await add_to_queue(interaction.user.id, interaction.guild.id, self.mode, False, level)
        await interaction.response.edit_message(
            embed=create_embed("✅ Joined Queue", f"**Mode:** {self.mode}\n**Level:** {level}\n\nSearching...", config.COLOR_SUCCESS),
            view=None
        )
        await try_match(interaction.guild, interaction.user, self.mode, False, level)

class TeamPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create VC", style=discord.ButtonStyle.primary, emoji="🔊", custom_id="tf:create_vc")
    async def create_vc(self, interaction: discord.Interaction, button: Button):
        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute("SELECT members FROM active_teams WHERE thread_id = ?", (interaction.channel.id,)) as cursor:
                row = await cursor.fetchone()

        if not row:
            return await interaction.response.send_message("Team data not found.", ephemeral=True)

        member_ids = json.loads(row[0])
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True)
        }
        for uid in member_ids:
            member = interaction.guild.get_member(uid)
            if member:
                overwrites[member] = discord.PermissionOverwrite(view_channel=True, connect=True)

        category = discord.utils.get(interaction.guild.categories, name="Teamy Teams")
        vc = await interaction.guild.create_voice_channel(
            name=f"Team VC • {interaction.user.display_name[:15]}",
            overwrites=overwrites,
            category=category,
            user_limit=config.TEAM_SIZE
        )

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("UPDATE active_teams SET voice_id = ? WHERE thread_id = ?", (vc.id, interaction.channel.id))
            await db.commit()

        await interaction.response.send_message(
            embed=create_embed("🔊 Voice Channel Created", f"Join here: {vc.mention}", config.COLOR_SUCCESS)
        )
        button.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Request Staff", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="tf:request_staff")
    async def request_staff(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            embed=create_embed("🛡️ Staff Requested", f"{interaction.user.mention} requested staff assistance.")
        )

    @discord.ui.button(label="Leave Team", style=discord.ButtonStyle.danger, emoji="🚪", custom_id="tf:leave")
    async def leave_team(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(f"{interaction.user.mention} left the team.")

# -------------------- Logic --------------------

async def add_to_queue(user_id: int, guild_id: int, mode: str, ranked: bool, rank_or_level: str, qtype: str = "normal"):
    async with aiosqlite.connect(config.DATABASE) as db:
        await db.execute(
            "INSERT OR REPLACE INTO queues (user_id, guild_id, mode, ranked, rank_or_level, joined_at, type) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, guild_id, mode, int(ranked), rank_or_level, datetime.now(timezone.utc).timestamp(), qtype)
        )
        await db.commit()

async def remove_from_queue(user_id: int):
    async with aiosqlite.connect(config.DATABASE) as db:
        await db.execute("DELETE FROM queues WHERE user_id = ?", (user_id,))
        await db.commit()

async def try_match(guild: discord.Guild, user: discord.Member, mode: str, ranked: bool, rank_or_level: str, qtype: str = "normal"):
    async with aiosqlite.connect(config.DATABASE) as db:
        async with db.execute(
            "SELECT user_id FROM queues WHERE guild_id = ? AND mode = ? AND type = ? AND user_id != ? ORDER BY joined_at ASC",
            (guild.id, mode, qtype, user.id)
        ) as cursor:
            others = [row[0] for row in await cursor.fetchall()]

    if len(others) >= config.TEAM_SIZE - 1:
        team_members = [user.id] + others[:config.TEAM_SIZE - 1]
        await create_team(guild, team_members, mode, qtype == "token")
        for uid in team_members:
            await remove_from_queue(uid)
        return

    await asyncio.sleep(config.MATCH_TIMEOUT)

    async with aiosqlite.connect(config.DATABASE) as db:
        async with db.execute("SELECT user_id FROM queues WHERE user_id = ?", (user.id,)) as cursor:
            if not await cursor.fetchone():
                return
        async with db.execute(
            "SELECT user_id FROM queues WHERE guild_id = ? AND mode = ? AND type = ? LIMIT ?",
            (guild.id, mode, qtype, config.TEAM_SIZE)
        ) as cursor:
            players = [row[0] for row in await cursor.fetchall()]

    if len(players) >= 2:
        await create_team(guild, players, mode, qtype == "token")
        for uid in players:
            await remove_from_queue(uid)

async def create_team(guild: discord.Guild, member_ids: list, mode: str, is_token: bool = False):
    members = [guild.get_member(uid) for uid in member_ids if guild.get_member(uid)]
    if len(members) < 2:
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
    }
    for member in members:
        overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    category = discord.utils.get(guild.categories, name="Teamy Teams")
    if not category:
        category = await guild.create_category("Teamy Teams")

    channel = await guild.create_text_channel(
        name=f"team-{members[0].display_name[:12]}",
        overwrites=overwrites,
        category=category
    )

    thread = await channel.create_thread(
        name="Team Chat",
        type=discord.ChannelType.private_thread,
        invitable=False
    )

    for member in members:
        try:
            await thread.add_user(member)
        except:
            pass

    view = TeamPanelView()
    title = "🎫 Token Hunt Team Formed!" if is_token else "🎮 Team Formed!"
    color = config.COLOR_TOKEN if is_token else config.COLOR_TEAM

    embed = create_embed(
        title,
        f"**Mode:** {mode}\n**Players:** {', '.join(m.mention for m in members)}\n\nUse the buttons below!",
        color
    )

    await thread.send(content=" ".join(m.mention for m in members), embed=embed, view=view)

    async with aiosqlite.connect(config.DATABASE) as db:
        await db.execute(
            "INSERT INTO active_teams (team_id, guild_id, thread_id, voice_id, mode, members, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(thread.id), guild.id, thread.id, None, mode, json.dumps(member_ids), datetime.now(timezone.utc).timestamp())
        )
        await db.commit()