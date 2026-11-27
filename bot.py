import discord
from discord.ext import commands
import config
from utils.database import init_db
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

async def load_cogs():
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
            await bot.load_extension(cog)
            print(f"✅ Loaded {cog}")
        except Exception as e:
            print(f"❌ Failed to load {cog}: {e}")

@bot.event
async def on_ready():
    await init_db()
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"✅ Connected to {len(bot.guilds)} servers")

    try:
        if config.GUILD_ID:
            synced = await bot.tree.sync(guild=discord.Object(id=config.GUILD_ID))
        else:
            synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

async def main():
    async with bot:
        await load_cogs()
        await bot.start(config.TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())