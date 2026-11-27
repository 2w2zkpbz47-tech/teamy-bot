import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
import config
from utils.embeds import create_embed

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = datetime.now(timezone.utc)

    @app_commands.command(name="ping", description="Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            embed=create_embed("🏓 Pong!", f"Latency: `{latency}ms`")
        )

    @app_commands.command(name="userinfo", description="Get information about a user")
    @app_commands.describe(member="The user to get info about")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user

        embed = create_embed(f"User Info — {member}", color=member.color or config.COLOR_PRIMARY)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
        embed.add_field(name="Bot", value="Yes" if member.bot else "No", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)

        roles = [role.mention for role in member.roles[1:]]
        embed.add_field(name=f"Roles [{len(roles)}]", value=", ".join(roles) if roles else "None", inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Get information about the server")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild

        embed = create_embed(f"Server Info — {guild.name}", color=config.COLOR_PRIMARY)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Channels", value=len(guild.channels), inline=True)
        embed.add_field(name="Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="Boosts", value=guild.premium_subscription_count, inline=True)
        embed.add_field(name="Created", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=True)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Get a user's avatar")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        embed = create_embed(f"Avatar — {member.display_name}")
        embed.set_image(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description="Show help menu")
    async def help(self, interaction: discord.Interaction):
        embed = create_embed("📖 Teamy Help Center", "Here's what I can do:")
        embed.add_field(
            name="🔍 Team Finder",
            value="`/setup-panel` → Post the Find Team panel\nUse the buttons to find teammates",
            inline=False
        )
        embed.add_field(
            name="🛡️ Staff Tools",
            value="`/staff @user` → Open staff panel\n`/warn` `/timeout` `/kick` `/ban`",
            inline=False
        )
        embed.add_field(
            name="🎫 Tickets",
            value="`/setup-tickets` → Post ticket panel\nSupport • Reports • Ban Appeals",
            inline=False
        )
        embed.add_field(
            name="📊 Levels",
            value="`/rank` • `/leaderboard`",
            inline=False
        )
        embed.add_field(
            name="🛠️ Utility",
            value="`/userinfo` • `/serverinfo` • `/avatar` • `/ping`",
            inline=False
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Utility(bot))