
import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta


class RoleAssignmentModal(discord.ui.Modal, title="Assign a Server Role"):
    member_id = discord.ui.TextInput(
        label="Member ID",
        placeholder="Enter the member's Discord ID",
        max_length=25
    )
    role_id = discord.ui.TextInput(
        label="Role ID",
        placeholder="Enter the server role ID",
        max_length=25
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_id = int(self.member_id.value.strip())
            target_role_id = int(self.role_id.value.strip())
        except ValueError:
            return await interaction.response.send_message(
                "Member ID and role ID must contain numbers only.",
                ephemeral=True
            )

        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message(
                "This can only be used inside a server.",
                ephemeral=True
            )

        try:
            member = await guild.fetch_member(target_id)
        except discord.NotFound:
            return await interaction.response.send_message(
                "I couldn't find that member in this server.",
                ephemeral=True
            )
        except discord.HTTPException:
            return await interaction.response.send_message(
                "I couldn't retrieve that member. Please try again.",
                ephemeral=True
            )

        role = guild.get_role(target_role_id)
        if role is None:
            return await interaction.response.send_message(
                "That role doesn't exist in this server.",
                ephemeral=True
            )

        bot_member = guild.me
        if bot_member is None or role >= bot_member.top_role:
            return await interaction.response.send_message(
                "My bot role must be higher than the role you're assigning.",
                ephemeral=True
            )

        if (
            interaction.user.id != guild.owner_id
            and role >= interaction.user.top_role
        ):
            return await interaction.response.send_message(
                "You cannot assign a role equal to or higher than your own.",
                ephemeral=True
            )

        if role in member.roles:
            return await interaction.response.send_message(
                f"{member.mention} already has {role.mention}.",
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
        except discord.HTTPException:
            return await interaction.response.send_message(
                "Discord couldn't complete the role assignment. Try again.",
                ephemeral=True
            )

        await interaction.response.send_message(
            f"Successfully assigned {role.mention} to {member.mention}.",
            ephemeral=True
        )


class EventModal(discord.ui.Modal, title="Create a Server Event"):
    event_name = discord.ui.TextInput(
        label="Event name",
        placeholder="Enter the event name",
        max_length=100
    )

    description = discord.ui.TextInput(
        label="Description",
        placeholder="Describe your event",
        style=discord.TextStyle.paragraph,
        max_length=1000
    )

    location = discord.ui.TextInput(
        label="Location",
        placeholder="e.g. Server Lounge / Main Voice",
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message(
                "This can only be used inside a server.",
                ephemeral=True
            )

        if not guild.me.guild_permissions.manage_events:
            return await interaction.response.send_message(
                "I need the Manage Events permission to create events.",
                ephemeral=True
            )

        now = discord.utils.utcnow()

        try:
            event = await guild.create_scheduled_event(
                name=self.event_name.value,
                description=self.description.value,
                entity_type=discord.EntityType.external,
                location=self.location.value,
                scheduled_start_time=now + timedelta(hours=1),
                scheduled_end_time=now + timedelta(hours=2),
                privacy_level=discord.PrivacyLevel.guild_only,
                reason=f"Created by {interaction.user}"
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "I don't have permission to create server events.",
                ephemeral=True
            )
        except discord.HTTPException as error:
            return await interaction.response.send_message(
                f"Discord couldn't create the event: {error}",
                ephemeral=True
            )

        await interaction.response.send_message(
            f"Successfully created **{event.name}**!\n"
            f"Start time: <t:{int(event.start_time.timestamp())}:F>",
            ephemeral=True
        )


class AdminDashboard(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def interaction_check(self, interaction: discord.Interaction):
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
    async def assign_role(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(RoleAssignmentModal())

    @discord.ui.button(
        label="Create event",
        emoji="📅",
        style=discord.ButtonStyle.success
    )
    async def create_event(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(EventModal())

    @discord.ui.button(
        label="Giveaway commands",
        emoji="🎉",
        style=discord.ButtonStyle.secondary
    )
    async def giveaway_info(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "**Teamy Giveaway Tools**\n\n"
            "Use the giveaway commands provided by your giveaway cog.\n"
            "The available commands depend on which giveaway features "
            "are installed.",
            ephemeral=True
        )


class AdminPanel(commands.Cog):
    admin = app_commands.Group(
        name="admin",
        description="Teamy administrative tools"
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @admin.command(
        name="panel",
        description="Open the Teamy administrator dashboard"
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Teamy | Administration",
            description=(
                "Welcome to the Teamy administrator dashboard.\n\n"
                "Choose an action below to manage your server."
            ),
            colour=discord.Colour.dark_purple()
        )

        embed.add_field(
            name="Administrative tools",
            value=(
                "🏷️ Assign server roles\n"
                "📅 Create scheduled server events\n"
                "🎉 Access giveaway information"
            ),
            inline=False
        )

        embed.set_footer(text="Teamy Administration")

        await interaction.response.send_message(
            embed=embed,
            view=AdminDashboard(),
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminPanel(bot))
