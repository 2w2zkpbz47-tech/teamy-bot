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
        self.message = None

    async def on_timeout(self):
        try:
            for child in self.children:
                child.disabled = True
            await self.message.edit(view=self)
        except:
            pass


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
            class StartView(SetupWizardView):
                @discord.ui.button(label="🚀 Start Setup", style=discord.ButtonStyle.green)
                async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.guild = interaction.guild
                    self.step = 1
                    await self.update_content(interaction)
            return embed, StartView(self, step)

        elif step == 1:
            embed = discord.Embed(
                title="Step 1️⃣ — Basic Server Configuration",
                description=(
                    f"**Server Name:** {guild.name}\n"
                    f"**Server ID:** `{guild.id}`\n"
                    f"**Owner:** {guild.owner.mention if guild.owner else 'Unknown'}\n\n"
                    "📌 **Is this your main server?**"
                ),
                color=getattr(config, "COLOR_TICKET", 0x3498DB)
            )
            class Step1View(SetupWizardView):
                @discord.ui.button(label="✅ Confirm — This is my server!", style=discord.ButtonStyle.green)
                async def confirm1(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 2
                    await self.update_content(interaction)
                @discord.ui.button(label="➡️ Skip for now", style=discord.ButtonStyle.secondary)
                async def skip1(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 2
                    await self.update_content(interaction)
                @discord.ui.button(label="⬅️ Back", style=discord.ButtonStyle.secondary, row=1)
                async def back1(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 0
                    await self.update_content(interaction)
            return embed, Step1View(self, step)

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
            class Step2View(SetupWizardView):
                @discord.ui.button(label="🔨 Create Roles Now", style=discord.ButtonStyle.green)
                async def makeroles(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 3
                    await self.update_content(interaction)
                @discord.ui.button(label="➡️ I'll do this later", style=discord.ButtonStyle.secondary)
                async def skip2(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 3
                    await self.update_content(interaction)
                @discord.ui.button(label="⬅️ Back", style=discord.ButtonStyle.secondary, row=1)
                async def back2(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 1
                    await self.update_content(interaction)
            return embed, Step2View(self, step)

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
            class Step3View(SetupWizardView):
                @discord.ui.button(label="✅ I've set my roles!", style=discord.ButtonStyle.green)
                async def done3(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 4
                    await self.update_content(interaction)
                @discord.ui.button(label="➡️ Do this later", style=discord.ButtonStyle.secondary)
                async def skip3(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 4
                    await self.update_content(interaction)
                @discord.ui.button(label="⬅️ Back", style=discord.ButtonStyle.secondary, row=1)
                async def back3(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 2
                    await self.update_content(interaction)
            return embed, Step3View(self, step)

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
            class Step4View(SetupWizardView):
                @discord.ui.button(label="📂 Create Channels Now", style=discord.ButtonStyle.green)
                async def makechans(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 5
                    await self.update_content(interaction)
                @discord.ui.button(label="➡️ I'll do this manually", style=discord.ButtonStyle.secondary)
                async def skip4(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 5
                    await self.update_content(interaction)
                @discord.ui.button(label="⬅️ Back", style=discord.ButtonStyle.secondary, row=1)
                async def back4(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 3
                    await self.update_content(interaction)
            return embed, Step4View(self, step)

        elif step == 5:
            embed = discord.Embed(
                title="Step 5️⃣ — Set Up Log Channels",
                description=(
                    "Where should I log events?\n\n"
                    "Run these commands when ready:\n"
                    "`/setup channels mod-logs #mod-logs`\n"
                    "`/setup channels ticket-logs #ticket-logs`\n"
                    "`/setup channels automod-logs #automod-logs`"
                ),
                color=discord.Color.purple()
            )
            class Step5View(SetupWizardView):
                @discord.ui.button(label="✅ Log Channels Set!", style=discord.ButtonStyle.green)
                async def done5(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 6
                    await self.update_content(interaction)
                @discord.ui.button(label="➡️ Later", style=discord.ButtonStyle.secondary)
                async def skip5(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 6
                    await self.update_content(interaction)
                @discord.ui.button(label="⬅️ Back", style=discord.ButtonStyle.secondary, row=1)
                async def back5(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 4
                    await self.update_content(interaction)
            return embed, Step5View(self, step)

        elif step == 6:
            embed = discord.Embed(
                title="Step 6️⃣ — Ticket System Setup",
                description=(
                    "Almost there! 🎫 Tickets let members get help privately.\n\n"
                    "**Run this command:**\n"
                    "`/ticket panel channel:#ticket-panel`\n"
                    "Posts the buttons members click to open tickets"
                ),
                color=discord.Color.blue()
            )
            class Step6View(SetupWizardView):
                @discord.ui.button(label="✅ Tickets Set Up!", style=discord.ButtonStyle.green)
                async def done6(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 7
                    await self.update_content(interaction)
                @discord.ui.button(label="➡️ Later", style=discord.ButtonStyle.secondary)
                async def skip6(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 7
                    await self.update_content(interaction)
                @discord.ui.button(label="⬅️ Back", style=discord.ButtonStyle.secondary, row=1)
                async def back6(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 5
                    await self.update_content(interaction)
            return embed, Step6View(self, step)

        elif step == 7:
            embed = discord.Embed(
                title="Step 7️⃣ — AutoMod & Security",
                description=(
                    "🛡️ Protect your server automatically!\n\n"
                    "**Run these commands:**\n"
                    "`/automod enable` — Auto-delete spam/links/bad words\n"
                    "`/antinuke enable` — Stop mass deletions/raids"
                ),
                color=discord.Color.red()
            )
            class Step7View(SetupWizardView):
                @discord.ui.button(label="✅ Security Set Up!", style=discord.ButtonStyle.green)
                async def done7(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 8
                    await self.update_content(interaction)
                @discord.ui.button(label="➡️ Later", style=discord.ButtonStyle.secondary)
                async def skip7(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 8
                    await self.update_content(interaction)
                @discord.ui.button(label="⬅️ Back", style=discord.ButtonStyle.secondary, row=1)
                async def back7(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 6
                    await self.update_content(interaction)
            return embed, Step7View(self, step)

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
                    "**Leveling:**\n"
                    "`/leveling toggle on` — Members earn XP for chatting!"
                ),
                color=discord.Color.green()
            )
            class Step8View(SetupWizardView):
                @discord.ui.button(label="✅ Looks Good!", style=discord.ButtonStyle.green)
                async def done8(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 9
                    await self.update_content(interaction)
                @discord.ui.button(label="➡️ Later", style=discord.ButtonStyle.secondary)
                async def skip8(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 9
                    await self.update_content(interaction)
                @discord.ui.button(label="⬅️ Back", style=discord.ButtonStyle.secondary, row=1)
                async def back8(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 7
                    await self.update_content(interaction)
            return embed, Step8View(self, step)

        elif step == 9:
            embed = discord.Embed(
                title="🎉 Setup Complete!",