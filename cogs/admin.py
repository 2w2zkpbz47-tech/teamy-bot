import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import config
from utils.embeds import create_embed
from utils.database import get_config

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="set-log", description="Set the moderation log channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                "UPDATE guild_config SET log_channel = ? WHERE guild_id = ?",
                (channel.id, interaction.guild.id)
            )
            await db.commit()
        await interaction.response.send_message(
            embed=create_embed("✅ Log Channel Set", f"Moderation logs will now be sent to {channel.mention}")
        )

    @app_commands.command(name="set-welcome", description="Set the welcome channel and message")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_welcome(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = "Welcome {user} to **{server}**!"):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                "UPDATE guild_config SET welcome_channel = ?, welcome_message = ? WHERE guild_id = ?",
                (channel.id, message, interaction.guild.id)
            )
            await db.commit()
        await interaction.response.send_message(
            embed=create_embed("✅ Welcome Set", f"Welcome messages will be sent to {channel.mention}\n\nMessage: {message}")
        )

    @app_commands.command(name="set-autorole", description="Set the autorole given on join")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_autorole(self, interaction: discord.Interaction, role: discord.Role):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                "UPDATE guild_config SET autorole = ? WHERE guild_id = ?",
                (role.id, interaction.guild.id)
            )
            await db.commit()
        await interaction.response.send_message(
            embed=create_embed("✅ Autorole Set", f"New members will automatically receive {role.mention}")
        )

    @app_commands.command(name="set-staffrole", description="Set the staff role (for tickets)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_staffrole(self, interaction: discord.Interaction, role: discord.Role):
        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute(
                "UPDATE guild_config SET staff_role = ? WHERE guild_id = ?",
                (role.id, interaction.guild.id)
            )
            await db.commit()
        await interaction.response.send_message(
            embed=create_embed("✅ Staff Role Set", f"Staff role set to {role.mention}")
        )

    @app_commands.command(name="config", description="View current server configuration")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_view(self, interaction: discord.Interaction):
        data = await get_config(interaction.guild.id)

        embed = create_embed("⚙️ Server Configuration")
        embed.add_field(name="Log Channel", value=f"<#{data[1]}>" if data[1] else "Not set", inline=False)
        embed.add_field(name="Welcome Channel", value=f"<#{data[2]}>" if data[2] else "Not set", inline=False)
        embed.add_field(name="Welcome Message", value=data[3] or "Default", inline=False)
        embed.add_field(name="Autorole", value=f"<@&{data[4]}>" if data[4] else "Not set", inline=False)
        embed.add_field(name="Staff Role", value=f"<@&{data[5]}>" if data[5] else "Not set", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Admin(bot))