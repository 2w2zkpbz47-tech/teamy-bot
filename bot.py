
import discord
from discord.ext import commands
import config
from utils.database import init_db
import asyncio
import os
import importlib


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True


class TeamyBot(commands.Bot):

    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents
        )

    async def setup_hook(self):

        print("\n========== TEAMY COG LOADER ==========")

        cog_folder = "cogs"

        cog_files = sorted(
            file[:-3]
            for file in os.listdir(cog_folder)
            if file.endswith(".py") and not file.startswith("_")
        )

        for cog in cog_files:

            extension = f"{cog_folder}.{cog}"

            try:
                await self.load_extension(extension)
                print(f"✅ Loaded: {extension}")

            except Exception as e:
                print(f"❌ Failed: {extension}")
                print(f"   Error: {type(e).__name__}: {e}")

        print("\n========== DATABASE ==========")

        try:
            await init_db()
            print("✅ Database initialized")
        except Exception as e:
            print(f"❌ Database error: {e}")

        print("\n========== COMMAND SYNC ==========")

        try:
            print(
                f"Registered commands: "
                f"{len(self.tree.get_commands())}"
            )

            if config.GUILD_ID:
                guild = discord.Object(id=config.GUILD_ID)

                self.tree.copy_global_to(guild=guild)

                synced = await self.tree.sync(guild=guild)

                print(
                    f"✅ Synced {len(synced)} guild commands"
                )

            else:
                synced = await self.tree.sync()

                print(
                    f"✅ Synced {len(synced)} global commands"
                )

            for command in synced:
                print(f"   /{command.name}")

        except Exception as e:
            print(f"❌ Sync failed: {type(e).__name__}: {e}")

        print("\n========== LOADED COGS ==========")

        for name in self.cogs:
            print(f"📁 {name}")

        print(f"\nTotal loaded cogs: {len(self.cogs)}")
        print("=================================\n")


bot = TeamyBot()


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"✅ Connected to {len(bot.guilds)} servers")
    print(f"✅ Registered commands: {len(bot.tree.get_commands())}")


async def main():
    token = config.TOKEN

    if not token:
        raise ValueError("Discord bot token is missing!")

    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
