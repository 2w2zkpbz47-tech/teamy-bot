
import discord
from discord import app_commands
from discord.ext import commands


class RoleAssignmentModal(discord.ui.Modal, title="Assign a Server Role"):
    member_id = discord.ui.TextInput(
        label="Member ID",
        placeholder="Discord member ID"
    )
    role_id = discord.ui.TextInput(
        label="Role ID",
        placeholder="Discord role ID"
    )

    async def on_submit(self, interaction):
        try:
            member = await interaction.guild.fetch_member(
                int(self.member_id.value)
            )
            role = interaction.guild.get_role(
                int(self.role_id.value)
            )
        except ValueError:
            return await interaction.response.send_message(
                "IDs must be numbers.",
                ephemeral=True
            )

        if not role:
            return await interaction.response.send_message(
                "That role doesn't exist.",
                ephemeral=True
            )

        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                "My bot role must be above that role.",
                ephemeral=True
            )

        if role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message(
                "You cannot assign a role equal to or above your highest role.",
                ephemeral=True
            )

        try:
            await member.add_roles(
                role,
                reason=f"Admin panel action by {interaction.user}"
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "I don't have permission to assign that role.",
                ephemeral=True
            )

        await interaction.response.send_message(
            f"Assigned {role.mention} to {member.mention}.",
            ephemeral=True
        )


class EventModal(discord.ui.Modal, title="Create a Server Event"):
    event_name = discord.ui.TextInput(
        label="Event name",
        max_length=100
    )

    description = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        max_length=1000
    )

    location = discord.ui.TextInput(
        label="Location or voice channel",
        placeholder="e.g. Server Lounge"
    )

    async def on_submit(self, interaction):
        try:
            event = await interaction.guild.create_scheduled_event(
                name=self.event_name.value,
                description=self.description.value,
                entity_type=discord.EntityType.external,
                location=self.location.value,
                scheduled_start_time=discord.utils.utcnow()
                + discord.timedelta(hours=1),
                scheduled_end_time=discord.utils.utcnow()
                + discord.timedelta(hours=2),
                privacy_level=discord.PrivacyLevel.guild_only,
                reason=f"Created by {interaction.user}"
            )
        except (discord.Forbidden, discord.HTTPException) as error:
            return await interaction.response.send_message(
                f"Couldn't create the event: {error}",
                ephemeral=True
            )

        await interaction.response.send_message(
            f"Created server event: **{event.name}**",
            ephemeral=True
        )


class AdminDashboard(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def interaction_check(self, interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Administrator permission is required.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="Assign role",
        emoji="🏷️",
        style=discord.ButtonStyle.primary
    )
    async def assign_role(self, interaction, button):
        await interaction.response.send_modal(RoleAssignmentModal())

    @discord.ui.button(
        label="Create event",
        emoji="📅",
        style=discord.ButtonStyle.success
    )
    async def create_event(self, interaction, button):
        await interaction.response.send_modal(EventModal())

    @discord.ui.button(
        label="Giveaway commands",
        emoji="🎉",
        style=discord.ButtonStyle.secondary
    )
    async def giveaway_info(self, interaction, button):
        await interaction.response.send_message(
            "**Giveaway commands**\n\n"
            "`/gstart` — Start a giveaway\n"
            "`/gend` — End a giveaway early\n\n"
            "These use the existing Teamy giveaway system.",
            ephemeral=True
        )


class AdminPanel(commands.Cog):
    admin = app_commands.Group(
        name="admin",
        description="Teamy administrative tools"
    )

    def __init__(self, bot):
        self.bot = bot

    @admin.command(
        name="panel",
        description="Open the Teamy administrator dashboard"
    )
    async def panel(self, interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "You need Administrator permission to use this panel.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="Teamy | Administration",
            description=(
                "Welcome to your administrative dashboard.\n\n"
                "Choose an action below."
            ),
            colour=discord.Colour.dark_purple()
        )

        embed.add_field(
            name="Administrative tools",
            value=(
                "🏷️ Assign server roles\n"
                "📅 Create server events\n"
                "🎉 Access giveaway commands"
            ),
            inline=False
        )

        await interaction.response.send_message(
            embed=embed,
            view=AdminDashboard(),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(AdminPanel(bot))
