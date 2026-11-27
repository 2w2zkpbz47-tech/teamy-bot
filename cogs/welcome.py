import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime, timezone
import config
from utils.embeds import create_embed
from utils.database import get_config

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invite_cache = {}

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            try:
                self.invite_cache[guild.id] = await guild.invites()
            except:
                self.invite_cache[guild.id] = []

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Invite tracking
        try:
            new_invites = await member.guild.invites()
            old_invites = self.invite_cache.get(member.guild.id, [])

            for invite in new_invites:
                old_invite = discord.utils.get(old_invites, code=invite.code)
                if old_invite and invite.uses > old_invite.uses:
                    async with aiosqlite.connect(config.DATABASE) as db:
                        await db.execute(
                            "INSERT OR REPLACE INTO invite_joins (guild_id, user_id, inviter_id, timestamp) VALUES (?, ?, ?, ?)",
                            (member.guild.id, member.id, invite.inviter.id if invite.inviter else 0, datetime.now(timezone.utc).timestamp())
                        )
                        await db.commit()
                    break

            self.invite_cache[member.guild.id] = new_invites
        except:
            pass

        # Welcome message + Autorole
        config_data = await get_config(member.guild.id)

        if config_data and config_data[2]:  # welcome_channel
            channel = member.guild.get_channel(config_data[2])
            if channel:
                message = config_data[3] or "Welcome {user} to **{server}**!"
                message = message.replace("{user}", member.mention).replace("{server}", member.guild.name)
                try:
                    await channel.send(embed=create_embed("👋 Welcome!", message))
                except:
                    pass

        if config_data and config_data[4]:  # autorole
            role = member.guild.get_role(config_data[4])
            if role:
                try:
                    await member.add_roles(role, reason="Autorole")
                except:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Optional: Goodbye message can be added here later
        pass

async def setup(bot):
    await bot.add_cog(Welcome(bot))