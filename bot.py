
import discord
from discord.ext import commands
import config
from utils.database import init_db

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned,
    intents=intents
)

class TeamyBot(commands.Bot):
    async def setup_hook(self):
        cogs = [
            "cogs.team_finder",
            "cogs.moderation",
            "cogs.tickets",
            "cogs.leveling",
            "cogs.welcome",
            "cogs.utility",
            "cogs.admin",
        ]

        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f"✅ Loaded {cog}")
            except Exception as e:
                print(f"❌ Failed to load {cog}: {e}")

        await init_db()

        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"✅ Synced {len(synced)} guild slash commands")
            for command in synced:
                print(f"  /{command.name}")
        else:
            synced = await self.tree.sync()
            print(f"✅ Synced {len(synced)} global slash commands")
            for command in synced:
                print(f"  /{command.name}")


bot = TeamyBot(command_prefix=commands.when_mentioned, intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"✅ Connected to {len(bot.guilds)} servers")
    print(f"✅ Registered commands: {len(bot.tree.get_commands())}")


async def main():
    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
