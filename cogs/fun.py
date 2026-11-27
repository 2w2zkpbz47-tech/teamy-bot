import discord
from discord import app_commands
from discord.ext import commands
import random
import aiohttp
import config
from utils.embeds import create_embed

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="8ball", description="Ask the magic 8ball a question")
    async def eightball(self, interaction: discord.Interaction, question: str):
        responses = [
            "It is certain.", "Without a doubt.", "Yes definitely.",
            "You may rely on it.", "As I see it, yes.", "Most likely.",
            "Outlook good.", "Yes.", "Signs point to yes.",
            "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
            "Cannot predict now.", "Concentrate and ask again.",
            "Don't count on it.", "My reply is no.", "My sources say no.",
            "Outlook not so good.", "Very doubtful."
        ]
        embed = create_embed("🎱 Magic 8-Ball", f"**Question:** {question}\n**Answer:** {random.choice(responses)}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coinflip", description="Flip a coin")
    async def coinflip(self, interaction: discord.Interaction):
        result = random.choice(["Heads", "Tails"])
        embed = create_embed("🪙 Coinflip", f"The coin landed on **{result}**!")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rps", description="Play Rock Paper Scissors")
    @app_commands.describe(choice="Your choice")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Rock", value="rock"),
        app_commands.Choice(name="Paper", value="paper"),
        app_commands.Choice(name="Scissors", value="scissors")
    ])
    async def rps(self, interaction: discord.Interaction, choice: app_commands.Choice[str]):
        bot_choice = random.choice(["rock", "paper", "scissors"])
        user = choice.value

        if user == bot_choice:
            result = "It's a tie!"
        elif (user == "rock" and bot_choice == "scissors") or \
             (user == "paper" and bot_choice == "rock") or \
             (user == "scissors" and bot_choice == "paper"):
            result = "You win!"
        else:
            result = "I win!"

        embed = create_embed(
            "🪨📄✂️ Rock Paper Scissors",
            f"**You chose:** {user.capitalize()}\n**I chose:** {bot_choice.capitalize()}\n\n**{result}**"
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="choose", description="Let the bot choose for you")
    async def choose(self, interaction: discord.Interaction, option1: str, option2: str, option3: str = None):
        options = [option1, option2]
        if option3:
            options.append(option3)
        chosen = random.choice(options)
        embed = create_embed("🤔 Choice", f"I choose **{chosen}**!")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="joke", description="Get a random joke")
    async def joke(self, interaction: discord.Interaction):
        jokes = [
            "Why don't scientists trust atoms? Because they make up everything!",
            "Why did the scarecrow win an award? Because he was outstanding in his field!",
            "Why don't eggs tell jokes? They'd crack each other up!",
            "What do you call a fake noodle? An impasta!",
            "Why did the bicycle fall over? Because it was two tired!"
        ]
        embed = create_embed("😂 Random Joke", random.choice(jokes))
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Fun(bot))