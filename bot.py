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

        # Sync slash commands AFTER all cogs are loaded
        try:
            if hasattr(config, "GUILD_ID") and config.GUILD_ID:
                guild = discord.Object(id=config.GUILD_ID)
                # Copy global commands to guild for instant testing
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info(
                    "✅ Synced %s slash commands to guild ID %s",
                    len(synced), config.GUILD_ID
                )
            else:
                synced = await self.tree.sync()
                logger.info(
                    "✅ Successfully registered %s global slash commands.",
                    len(synced)
                )
                if len(synced) == 0:
                    logger.warning(
                        "⚠️ 0 commands synced — this is normal on first run or if "
                        "commands already registered globally. Global sync may take "
                        "up to 1 hour to propagate."
                    )
        except Exception:
            logger.error(
                "❌ COMMAND SYNC FAILED:\n%s",
                traceback.format_exc()
            )

        if self.failed_extensions:
            logger.error(
                "⚠️ TEAMY STARTED WITH %s FAILED COGS: %s",
                len(self.failed_extensions),
                ", ".join(self.failed_extensions)
            )
        else:
            logger.info("✅ ALL COGS LOADED SUCCESSFULLY.")

    async def on_ready(self):
        logger.info("Logged in as %s", self.user)
        logger.info("Connected to %s servers.", len(self.guilds))
        
        if self.failed_extensions:
            logger.warning("⚠️ Some cogs failed to load. Check the startup logs.")
        else:
            logger.info("✅ Teamy is fully operational.")


bot = Teamy()


async def main():
    if not config.TOKEN:
        raise RuntimeError(
            "DISCORD_BOT_TOKEN is missing. "
            "Check your environment variables."
        )
    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())