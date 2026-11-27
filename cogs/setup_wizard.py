import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import config
from typing import Optional

class SetupWizardView(discord.ui.View):
    def __init__(self, cog: "SetupWizard", step: int = 0):
        super().__init__(timeout=300)
        self.cog = cog
        self.step = step
        self.guild = None

    async def update_content(self, interaction: discord.Interaction):
        embed, buttons = await self.cog.get_step_content(self.step, self.guild)
        self.clear_items()
        for button in buttons:
            self.add_item(button)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⬅️ Back", style=discord.ButtonStyle.secondary, row=0)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.step > 0:
            self.step -= 1
            await self.update_content(interaction)

    @discord.ui.button(label="Skip ➡️", style=discord.ButtonStyle.secondary, row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.step += 1
        await self.update_content(interaction)

    @discord.ui.button(label="✅ Start Here", style=discord.ButtonStyle.green, row=1)
    async def proceed(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.guild = interaction.guild
        self.step += 1
        await self.update_content(interaction)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(content="⏰ Setup wizard timed out. Run `/wizard` to start again.", view=self)
        except:
            pass


class YesNoButtons(discord.ui.View):
    def __init__(self, yes_label="✅ Yes", no_label="❌ No"):
        super().__init__(timeout=120)
        self.value = None
        self.responded = False

    @discord.ui.button(label="✅ Yes", style=discord.ButtonStyle.green)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.responded = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="❌ No / Skip", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.responded = True
        self.stop()
        await interaction.response.defer()

    async def wait_for_response(self):
        await self.wait()
        return self.value


class SetupWizard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need **Administrator** permission to use the setup wizard.",
                ephemeral=True
            )
            return False
        return True

    async def get_step_content(self, step: int, guild: discord.Guild):
        buttons = []

        if step == 0:
            embed = discord.Embed(
                title="🧙 Teamy Setup Wizard",
                description=(
                    "Welcome! I'll guide you through setting up your server step by step.\n\n"
                    "📋 **What we'll cover:**\n"
                    "1️⃣  Server Info & Configuration\n"
                    "2️⃣  Staff Roles Setup\n"
                    "3️⃣  Log Channels Setup\n"
                    "4️⃣  Ticket System & Panels\n"
                    "5️⃣  AutoMod & Anti-Nuke\n"
                    "6️⃣  Welcome & Community Features\n"
                    "7️⃣  Final Summary & Checklist\n\n"
                    "💡 You can skip any step or go back at any time. Let's get started!"
                ),
                color=getattr(config, "COLOR_INFO", 0x9B59B6)
            )
            buttons = [
                discord.ui.Button(label="🚀 Start Setup", style=discord.ButtonStyle.green, custom_id="wizard_start")
            ]

        elif step == 1:
            embed = discord.Embed(
                title="Step 1️⃣ — Basic Server Configuration",
                description=(
                    f"**Server Name:** {guild.name}\n"
                    f"**Server ID:** `{guild.id}`\n"
                    f"**Owner:** {guild.owner}\n\n"
                    "📌 **Is this your main server?**\n"
                    "This will be saved as your default guild."
                ),
                color=getattr(config, "COLOR_TICKET", 0x3498DB)
            )
            buttons = [
                discord.ui.Button(label="✅ Confirm — This is my server!", style=discord.ButtonStyle.green, custom_id="wizard_confirm1"),
                discord.ui.Button(label="➡️ Skip for now", style=discord.ButtonStyle.secondary, custom_id="wizard_skip1")
            ]

        elif step == 2:
            embed = discord.Embed(
                title="Step 2️⃣ — Create Roles Automatically",
                description=(
                    "I can create these roles for you:\n"
                    "• 👑 Admin\n"
                    "• 🛡️ Moderator\n"
                    "• 🎫 Ticket Support\n"
                    "• 👥 Member\n\n"
                    "⚠️ **Important:** Move my role ABOVE these roles after I create them!"
                ),
                color=discord.Color.orange()
            )
            buttons = [
                discord.ui.Button(label="🔨 Create Roles Now", style=discord.ButtonStyle.green, custom_id="wizard_makeroles"),
                discord.ui.Button(label="➡️ I'll do this later", style=discord.ButtonStyle.secondary, custom_id="wizard_skip2")
            ]

        elif step == 3:
            embed = discord.Embed(
                title="Step 3️⃣ — Assign Staff Roles",
                description=(
                    "Tell me which roles handle what:\n\n"
                    "• **General Staff Role** → Moderation commands\n"
                    "• **Ticket Support Role** → Ticket management\n"
                    "• **Admin Role** → Full bot control\n\n"
                    "Run these commands when ready:\n"
                    "`/staff set-role @Moderator`\n"
                    "`/staff-role add division:Ticket Support role:@Ticket Support`"
                ),
                color=discord.Color.blue()
            )
            buttons = [
                discord.ui.Button(label="✅ I've set my roles!", style=discord.ButtonStyle.green, custom_id="wizard_done3"),
                discord.ui.Button(label="➡️ Do this later", style=discord.ButtonStyle.secondary, custom_id="wizard_skip3")
            ]

        elif step == 4:
            embed = discord.Embed(
                title="Step 4️⃣ — Create Channels Automatically",
                description=(
                    "I can create a full channel structure:\n\n"
                    "📢 INFORMATION — Rules, Announcements, Welcome\n"
                    "💬 COMMUNITY — Chat, Introductions, Suggestions\n"
                    "🎫 SUPPORT — Ticket Panel\n"
                    "🔒 STAFF AREA — Logs, Dashboard (Staff Only)\n"
                    "🔊 VOICE CHANNELS — General, Gaming\n\n"
                    "Would you like me to create these now?"
                ),
                color=discord.Color.teal()
            )
            buttons = [
                discord.ui.Button(label="📂 Create Channels Now", style=discord.ButtonStyle.green, custom_id="wizard_makechans"),
                discord.ui.Button(label="➡️ I'll do this manually", style=discord.ButtonStyle.secondary, custom_id="wizard_skip4")
            ]

        elif step == 5:
            embed = discord.Embed(
                title="Step 5️⃣ — Set Up Log Channels",
                description=(
                    "Where should I log events?\n\n"
                    "Run these commands when ready:\n"
                    "`/setup channels mod-logs #mod-logs`\n"
                    "`/setup channels ticket-logs #ticket-logs`\n"
                    "`/setup channels automod-logs #automod-logs`\n\n"
                    "These channels keep a record of moderation actions, "
                    "ticket closures, and AutoMod alerts."
                ),
                color=discord.Color.purple()
            )
            buttons = [
                discord.ui.Button(label="✅ Log Channels Set!", style=discord.ButtonStyle.green, custom_id="wizard_done5"),
                discord.ui.Button(label="➡️ Later", style=discord.ButtonStyle.secondary, custom_id="wizard_skip5")
            ]

        elif step == 6:
            embed = discord.Embed(
                title="Step 6️⃣ — Ticket System Setup",
                description=(
                    "Almost there! 🎫 Tickets let members get help privately.\n\n"
                    "**Run these commands:**\n"
                    "1️⃣ `/ticket panel channel:#ticket-panel`\n"
                    "   Posts the buttons members click to open tickets\n\n"
                    "2️⃣ Test it — click a button → I make a private channel!\n\n"
                    "Staff commands: `/ticketsupport overview`"
                ),
                color=discord.Color.blue()
            )
            buttons = [
                discord.ui.Button(label="✅ Tickets Set Up!", style=discord.ButtonStyle.green, custom_id="wizard_done6"),
                discord.ui.Button(label="➡️ Later", style=discord.ButtonStyle.secondary, custom_id="wizard_skip6")
            ]

        elif step == 7:
            embed = discord.Embed(
                title="Step 7️⃣ — AutoMod & Security",
                description=(
                    "🛡️ Protect your server automatically!\n\n"
                    "**Run these commands:**\n"
                    "`/automod enable` — Auto-delete spam/links/bad words\n"
                    "`/antinuke enable` — Stop mass deletions/raids\n\n"
                    "⚠️ Anti-Nuke is highly recommended for larger servers!"
                ),
                color=discord.Color.red()
            )
            buttons = [
                discord.ui.Button(label="✅ Security Set Up!", style=discord.ButtonStyle.green, custom_id="wizard_done7"),
                discord.ui.Button(label="➡️ Later", style=discord.ButtonStyle.secondary, custom_id="wizard_skip7")
            ]

        elif step == 8:
            embed = discord.Embed(
                title="Step 8️⃣ — Welcome & Community Features",
                description=(
                    "👋 Make your server feel alive!\n\n"
                    "**Welcome Messages:**\n"
                    "`/welcome set-channel #welcome`\n"
                    "`/welcome toggle enabled:On`\n\n"
                    "**Suggestions:**\n"
                    "`/suggestions set-channel #suggestions`\n\n"
                    "**Leveling (Optional):**\n"
                    "`/leveling toggle on` — Members earn XP for chatting!"
                ),
                color=discord.Color.green()
            )
            buttons = [
                discord.ui.Button(label="✅ Looks Good!", style=discord.ButtonStyle.green, custom_id="wizard_done8"),
                discord.ui.Button(label="➡️ Later", style=discord.ButtonStyle.secondary, custom_id="wizard_skip8")
            ]

        elif step == 9:
            embed = discord.Embed(
                title="🎉 Setup Complete!",
                description=(
                    "Great job! Here's your final checklist:\n\n"
                    "✅ Bot online & slash commands working\n"
                    "✅ Roles created & assigned\n"
                    "✅ Channels organized\n"
                    "✅ Logs configured\n"
                    "✅ Ticket panel posted\n"
                    "✅ AutoMod & Anti-Nuke active\n"
                    "✅ Welcome messages set\n\n"
                    "📖 **Need help later?** Just type `/help` or ask me!\n\n"
                    "💡 **Quick commands cheat sheet:**\n"
                    "• `/ticket panel` → Post ticket buttons\n"
                    "• `/warn @user reason` → Issue warning\n"
                    "• `/automod enable` → Turn on protection\n"
                    "• `/welcome toggle on` → Welcome messages\n\n"
                    "Enjoy using Teamy! 🚀"
                ),
                color=discord.Color.green()
            )
            buttons = []

        else:
            embed = discord.Embed(title="✅ Setup Complete!", description="You're all set!", color=discord.Color.green())
            buttons = []

        return embed, buttons

    @app_commands.command(name="wizard", description="🧙 Start the full server setup wizard")
    async def start_wizard(self, interaction: discord.Interaction):
        embed, _ = await self.get_step_content(0, interaction.guild)
        view = SetupWizardView(self, step=0)
        view.message = await interaction.response.send_message(embed=embed, view=view, ephemeral=False)


async def setup(bot):
    await bot.add_cog(SetupWizard(bot))