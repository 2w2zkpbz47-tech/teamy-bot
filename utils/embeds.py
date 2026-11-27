import discord
from datetime import datetime, timezone
import config

def create_embed(title: str, description: str = "", color: int = config.COLOR_PRIMARY):
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="Teamy • Ultimate Fortnite Bot")
    return embed