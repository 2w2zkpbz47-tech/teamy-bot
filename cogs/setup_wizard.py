import discord
from discord import app_commands
from discord.ext import commands
import config


class SetupWizardView(discord.ui.View):
    def __init__(self, cog: "SetupWizard", step: int = 0):
        super().__init__(timeout=300)
        self.cog = cog
        self.step = step
        self.guild = None
        self.message = None

    async def update_content(self, interaction: discord.Interaction):
        embed, view_class = await self.cog.get_step_content(self.step, interaction.guild)
        new_view = view_class(self.cog, step=self.step)
        new_view.message = self.message
        new_view.guild = self.guild
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def on_timeout(self):
        try:
            for child in self.children:
                child.disabled = True
            await self.message.edit(view=self)
        except Exception:
            pass


class SetupWizard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need Administrator permission to use the setup wizard.",
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
                    "What we'll cover:\n"
                    "1. Server Info & Configuration\n"
                    "2. Staff Roles Setup\n"
                    "3. Log Channels Setup\n"
                    "4. Ticket System & Panels\n"
                    "5. AutoMod & Anti-Nuke\n"
                    "6. Welcome & Community Features\n"
                    "7. Final Summary & Checklist\n\n"
                    "You can skip any step or go back at any time. Let's get started!"
                ),
                color=getattr(config, "COLOR_INFO", 0x9B59B6)
            )
            class StartView(SetupWizardView):
                @discord.ui.button(label="🚀 Start Setup", style=discord.ButtonStyle.green)
                async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.guild = interaction.guild
                    self.step = 1
                    await self.update_content(interaction)
            return embed, StartView

        elif step == 1:
            embed = discord.Embed(
                title="Step 1 — Basic Server Configuration",
                description=(
                    f"Server Name: {guild.name}\n"
                    f"Server ID: {guild.id}\n"
                    f"Owner: {guild.owner.mention if guild.owner else 'Unknown'}\n\n"
                    "Is this your main server?"
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
            return embed, Step1View

        elif step == 2:
            embed = discord.Embed(
                title="Step 2 — Create Roles Automatically",
                description=(
                    "I can create these roles for you:\n"
                    "• Admin\n"
                    "• Moderator\n"
                    "• Ticket Support\n"
                    "• Member\n\n"
                    "Important: Move my role ABOVE these roles after I create them!"
                ),
                color=discord.Color.orange()
            )
            class Step2View(SetupWizardView):
                @discord.ui.button(label="🔨 Create Roles Now", style=discord.ButtonStyle.green)
                async def makeroles(self, interaction: discord.Interaction, button: discord.ui.Button):
                    await interaction.response.send_message(
                        "✅ Use /setup-server command to create roles and channels!",
                        ephemeral=True
                    )
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
            return embed, Step2View

        elif step == 3:
            embed = discord.Embed(
                title="Step 3 — Assign Staff Roles",
                description=(
                    "Tell me which roles handle what:\n\n"
                    "• General Staff Role -> Moderation commands\n"
                    "• Ticket Support Role -> Ticket management\n"
                    "• Admin Role -> Full bot control\n\n"
                    "Run these commands when ready:\n"
                    "/staff set-role @Moderator\n"
                    "/staff-role add division:Ticket Support role:@Ticket Support"
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
            return embed, Step3View

        elif step == 4:
            embed = discord.Embed(
                title="Step 4 — Create Channels Automatically",
                description=(
                    "I can create a full channel structure:\n\n"
                    "INFORMATION — Rules, Announcements, Welcome\n"
                    "COMMUNITY — Chat, Introductions, Suggestions\n"
                    "SUPPORT — Ticket Panel\n"
                    "STAFF AREA — Logs, Dashboard (Staff Only)\n"
                    "VOICE CHANNELS — General, Gaming\n\n"
                    "Would you like me to create these now?"
                ),
                color=discord.Color.teal()
            )
            class Step4View(SetupWizardView):
                @discord.ui.button(label="📂 Create Channels Now", style=discord.ButtonStyle.green)
                async def makechans(self, interaction: discord.Interaction, button: discord.ui.Button):
                    await interaction.response.send_message(
                        "✅ Run /setup-server to create all channels automatically!",
                        ephemeral=True
                    )
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
            return embed, Step4View        
                 elif step == 5:
            embed = discord.Embed(
                title="Step 5 — Set Up Log Channels",
                description=(
                    "Where should I log events?\n\n"
                    "Run these commands when ready:\n"
                    "/setup channels mod-logs #mod-logs\n"
                    "/setup channels ticket-logs #ticket-logs\n"
                    "/setup channels automod-logs #automod-logs"
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
            return embed, Step5View

        elif step == 6:
            embed = discord.Embed(
                title="Step 6 — Ticket System Setup",
                description=(
                    "Almost there! Tickets let members get help privately.\n\n"
                    "Run this command:\n"
                    "/ticket panel channel:#ticket-panel\n"
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
            return embed, Step6View

        elif step == 7:
            embed = discord.Embed(
                title="Step 7 — AutoMod & Security",
                description=(
                    "Protect your server automatically!\n\n"
                    "Run these commands:\n"
                    "/automod enable — Auto-delete spam/links/bad words\n"
                    "/antinuke enable — Stop mass deletions/raids"
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
            return embed, Step7View

        elif step == 8:
            embed = discord.Embed(
                title="Step 8 — Welcome & Community Features",
                description=(
                    "Make your server feel alive!\n\n"
                    "Welcome Messages:\n"
                    "/welcome set-channel #welcome\n"
                    "/welcome toggle enabled:On\n\n"
                    "Suggestions:\n"
                    "/suggestions set-channel #suggestions\n\n"
                    "Leveling:\n"
                    "/leveling toggle on — Members earn XP for chatting!"
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
                return embed, Step8View

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
                    "Need help later? Just type /help or run /wizard again!\n\n"
                    "Quick commands cheat sheet:\n"
                    "/ticket panel — Post ticket buttons\n"
                    "/warn @user reason — Issue warning\n"
                    "/automod enable — Turn on protection\n"
                    "/welcome toggle on — Welcome messages\n"
                    "/setup-server — Auto-create roles & channels\n\n"
                    "Enjoy using Teamy! 🚀"
                ),
                color=discord.Color.green()
            )
            class Step9View(SetupWizardView):
                @discord.ui.button(label="✅ Finish", style=discord.ButtonStyle.green)
                async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
                    await interaction.response.edit_message(
                        content="🎊 All done! Enjoy your fully set up server!",
                        embed=None,
                        view=None
                    )
                @discord.ui.button(label="⬅️ Back", style=discord.ButtonStyle.secondary)
                async def back9(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.step = 8
                    await self.update_content(interaction)
            return embed, Step9View

        else:
            embed = discord.Embed(
                title="✅ Done!",
                description="You're all set up!",
                color=discord.Color.green()
            )
            return embed, None

    @app_commands.command(name="wizard", description="Start the full server setup wizard")
    async def start_wizard(self, interaction: discord.Interaction):
        embed, ViewClass = await self.get_step_content(0, interaction.guild)
        view = ViewClass(self, step=0)
        view.message = await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
        view.guild = interaction.guild


async def setup(bot):
    await bot.add_cog(SetupWizard(bot))