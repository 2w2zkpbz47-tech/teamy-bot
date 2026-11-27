
import discord
from discord.ext import commands
import config
import os
import asyncio
import logging
import traceback

from utils.database import init_db


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("Teamy")


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

        self.failed_extensions = []

    async def setup_hook(self):
        logger.info("Initialising Teamy database...")

        await init_db()

        logger.info("Database initialised.")

        cog_folder = "./cogs"

        if not os.path.isdir(cog_folder):
            logger.error("The cogs folder does not exist!")
            return

        extensions = sorted(
            filename[:-3]
            for filename in os.listdir(cog_folder)
            if filename.endswith(".py")
            and not filename.startswith("_")
        )

        logger.info("Found %s cog files.", len(extensions))

        for extension_name in extensions:
            extension = f"cogs.{extension_name}"

            try:
                await self.load_extension(extension)
                logger.info("LOADED: %s", extension)

            except Exception:
                self.failed_extensions.append(extension)
                logger.error(
                    "FAILED TO LOAD: %s\n%s",
                    extension,
                    traceback.format_exc()
                )

        try:
            if config.GUILD_ID:
                synced = await self.tree.sync(
                    guild=discord.Object(id=config.GUILD_ID)
                )
            else:
                synced = await self.tree.sync()

            logger.info(
                "Successfully registered %s slash commands.",
                len(synced)
            )

        except Exception:
            logger.error(
                "COMMAND SYNC FAILED:\n%s",
                traceback.format_exc()
            )

        if self.failed_extensions:
            logger.error(
                "TEAMY STARTED WITH %s FAILED COGS: %s",
                len(self.failed_extensions),
                ", ".join(self.failed_extensions)
            )
        else:
            logger.info("ALL COGS LOADED SUCCESSFULLY.")

    async def on_ready(self):
        logger.info("Logged in as %s", self.user)
        logger.info("Connected to %s servers.", len(self.guilds))

        if self.failed_extensions:
            logger.warning(
                "Some cogs failed to load. Check the startup logs."
            )
        else:
            logger.info("Teamy is fully operational.")


bot = Teamy()


async def main():
    if not config.TOKEN:
        raise RuntimeError(
            "DISCORD_BOT_TOKEN is missing. "
            "Check your Railway environment variables."
        )

    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
