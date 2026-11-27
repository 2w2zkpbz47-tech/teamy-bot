
import discord
from discord.ext import commands
import config
import os
import asyncio

from utils.database import init_db


class Teamy(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.voice_states = True

        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):
        await init_db()

        for filename in sorted(os.listdir("./cogs")):
            if filename.endswith(".py") and not filename.startswith("_"):
                extension = f"cogs.{filename[:-3]}"

                try:
                    await self.load_extension(extension)
                    print(f"Loaded {extension}")
                except Exception as error:
                    print(f"Failed {extension}: {error}")

        try:
            if config.GUILD_ID:
                synced = await self.tree.sync(
                    guild=discord.Object(id=config.GUILD_ID)
                )
            else:
                synced = await self.tree.sync()

            print(f"Registered {len(synced)} slash commands")

        except Exception as error:
            print(f"Command sync failed: {error}")

    async def on_ready(self):
        print(f"Logged in as {self.user}")
        print(f"Connected to {len(self.guilds)} servers")


bot = Teamy()


async def main():
    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
