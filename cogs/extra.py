
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import config
from utils.embeds import create_embed


class Extra(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.snipes = {}

    # -------------------- SNIPE SYSTEM --------------------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        self.snipes[message.channel.id] = message

    @app_commands.command(
        name="snipe",
        description="Show the last deleted message in this channel"
    )
    async def snipe(self, interaction: discord.Interaction):
        message = self.snipes.get(interaction.channel.id)

        if not message:
            return await interaction.response.send_message(
                embed=create_embed(
                    "Snipe",
                    "There's nothing to snipe in this channel."
                ),
                ephemeral=True
            )

        embed = create_embed(
            "🔍 Sniped Message",
            message.content or "*No text content*",
            config.COLOR_INFO
        )

        embed.set_author(
            name=str(message.author),
            icon_url=message.author.display_avatar.url
        )

        embed.set_footer(
            text=f"Deleted in #{message.channel.name}"
        )

        embed.timestamp = message.created_at

        await interaction.response.send_message(embed=embed)

    # -------------------- INVITES COMMAND --------------------

    @app_commands.command(
        name="invites",
        description="Check how many people someone has invited"
    )
    async def invites(
        self,
        interaction: discord.Interaction,
        member: discord.Member = None
    ):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True
            )

        member = member or interaction.user

        async with aiosqlite.connect(config.DATABASE) as db:
            async with db.execute(
                """
                SELECT COUNT(*)
                FROM invite_joins
                WHERE guild_id = ? AND inviter_id = ?
                """,
                (interaction.guild.id, member.id)
            ) as cursor:
                count = (await cursor.fetchone())[0]

        embed = create_embed(
            "📨 Invites",
            f"{member.mention} has invited **{count}** members."
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Extra(bot))
