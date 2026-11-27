import discord
from discord.ext import commands
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import re
import config
from utils.embeds import create_embed

class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.spam_tracker = defaultdict(list)  # user_id: [timestamps]
        self.invite_pattern = re.compile(
            r"(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/)",
            re.IGNORECASE
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # ---------- Anti-Spam ----------
        now = datetime.now(timezone.utc).timestamp()
        user_id = message.author.id

        # Keep only recent messages (last 7 seconds)
        self.spam_tracker[user_id] = [t for t in self.spam_tracker[user_id] if now - t < 7]
        self.spam_tracker[user_id].append(now)

        if len(self.spam_tracker[user_id]) >= 6:
            try:
                await message.author.timeout(
                    datetime.now(timezone.utc) + timedelta(minutes=5),
                    reason="AutoMod: Spamming"
                )
                await message.channel.send(
                    embed=create_embed(
                        "🛡️ AutoMod",
                        f"{message.author.mention} has been timed out for **spamming**.",
                        config.COLOR_ERROR
                    ),
                    delete_after=8
                )
            except:
                pass
            self.spam_tracker[user_id].clear()
            return

        # ---------- Anti-Invite Links ----------
        if self.invite_pattern.search(message.content):
            # Allow if user has manage_messages permission
            if not message.author.guild_permissions.manage_messages:
                try:
                    await message.delete()
                    await message.channel.send(
                        embed=create_embed(
                            "🛡️ AutoMod",
                            f"{message.author.mention}, invite links are not allowed.",
                            config.COLOR_WARN
                        ),
                        delete_after=6
                    )
                except:
                    pass

async def setup(bot):
    await bot.add_cog(AutoMod(bot))