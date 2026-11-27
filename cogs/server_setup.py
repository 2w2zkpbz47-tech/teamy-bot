import discord
from discord import app_commands
from discord.ext import commands
import logging

logger = logging.getLogger("Teamy")

# ── ROLES TO CREATE ──────────────────────────────────
ROLES_TO_CREATE = [
    {"name": "👑 Admin", "color": discord.Color.red(), "permissions": discord.Permissions(administrator=True), "hoist": True},
    {"name": "🛡️ Moderator", "color": discord.Color.orange(), "permissions": discord.Permissions(
        kick_members=True, ban_members=True, manage_messages=True, read_message_history=True
    ), "hoist": True},
    {"name": "🎫 Ticket Support", "color": discord.Color.blue(), "permissions": discord.Permissions.none(), "hoist": False},
    {"name": "👥 Member", "color": discord.Color.green(), "permissions": discord.Permissions(
        read_messages=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True
    ), "hoist": True},
]

# ── CATEGORIES & CHANNELS ─────────────────────────────
CATEGORIES = [
    {
        "name": "📢 INFORMATION",
        "channels": [
            {"name": "📜│rules", "type": "text", "topic": "Server rules and guidelines"},
            {"name": "📢│announcements", "type": "text", "topic": "Important server announcements"},
            {"name": "👋│welcome", "type": "text", "topic": "Welcome messages for new members"},
        ]
    },
    {
        "name": "💬 COMMUNITY",
        "channels": [
            {"name": "💬│general", "type": "text", "topic": "General chat for everyone"},
            {"name": "🤝│introductions", "type": "text", "topic": "Introduce yourself!"},
            {"name": "💡│suggestions", "type": "text", "topic": "Share your ideas for the server"},
        ]
    },
    {
        "name": "🎫 SUPPORT",
        "channels": [
            {"name": "📩│ticket-panel", "type": "text", "topic": "Open a support ticket here"},
        ]
    },
    {
        "name": "🔒 STAFF AREA",
        "channels": [
            {"name": "📋│staff-dashboard", "type": "text", "topic": "Staff commands & dashboard"},
            {"name": "📝│mod-logs", "type": "text", "topic": "Moderation action logs"},
            {"name": "🎫│ticket-logs", "type": "text", "topic": "Closed ticket transcripts"},
            {"name": "🤖│automod-logs", "type": "text", "topic": "AutoMod alerts and warnings"},
        ],
        # Staff category — hidden from everyone except staff
        "private": True
    },
    {
        "name": "🔊 VOICE CHANNELS",
        "channels": [
            {"name": "General", "type": "voice"},
            {"name": "Gaming", "type": "voice"},
        ]
    }
]

class ServerSetupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need **Administrator** permission to run this command.",
                ephemeral=True
            )
            return False
        return True

    @app_commands.command(
        name="setup-server",
        description="🚀 Creates all recommended roles, categories and channels"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_server(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "🔧 Starting server setup — this may take a moment...\n"
            "Check your server — don't close this message!",
            ephemeral=False
        )
        guild = interaction.guild
        results = {"roles_created": 0, "roles_skipped": 0, "categories_created": 0, "channels_created": 0, "errors": []}

        # ── STEP 1: Create Roles ──
        setup_msg = "> **Step 1/3: Creating Roles...**\n"
        for role_data in ROLES_TO_CREATE:
            existing = discord.utils.get(guild.roles, name=role_data["name"])
            if existing:
                setup_msg += f"⏭️  Skipped — already exists: {role_data['name']}\n"
                results["roles_skipped"] += 1
                continue
            try:
                await guild.create_role(
                    name=role_data["name"],
                    color=role_data["color"],
                    permissions=role_data["permissions"],
                    hoist=role_data.get("hoist", False),
                    reason="Teamy Server Setup"
                )
                setup_msg += f"✅ Created role: {role_data['name']}\n"
                results["roles_created"] += 1
            except Exception as e:
                setup_msg += f"❌ Failed {role_data['name']}: {str(e)}\n"
                results["errors"].append(f"Role {role_data['name']}: {str(e)}")
        await interaction.edit_original_response(content=setup_msg)

        # ── STEP 2: Create Categories & Channels ──
        setup_msg += "\n> **Step 2/3: Creating Categories & Channels...**\n"
        staff_role = discord.utils.get(guild.roles, name="🛡️ Moderator") or discord.utils.get(guild.roles, name="👑 Admin")
        member_role = discord.utils.get(guild.roles, name="👥 Member")

        for cat_data in CATEGORIES:
            existing_cat = discord.utils.get(guild.categories, name=cat_data["name"])
            if existing_cat:
                category = existing_cat
                setup_msg += f"⏭️  Category exists: {cat_data['name']}\n"
            else:
                # Build overwrites for private categories
                overwrites = {}
                if cat_data.get("private"):
                    overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
                    if staff_role:
                        overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
                    admin_role = discord.utils.get(guild.roles, name="👑 Admin")
                    if admin_role:
                        overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

                category = await guild.create_category_channel(
                    name=cat_data["name"],
                    overwrites=overwrites if cat_data.get("private") else {},
                    reason="Teamy Server Setup"
                )
                setup_msg += f"✅ Created category: {cat_data['name']}\n"
                results["categories_created"] += 1

            # Create channels in this category
            for ch_data in cat_data["channels"]:
                ch_type = discord.ChannelType.text if ch_data.get("type", "text") == "text" else discord.ChannelType.voice
                existing_ch = discord.utils.get(guild.channels, name=ch_data["name"].split("│")[-1] if "│" in ch_data["name"] else ch_data["name"])
                if existing_ch and existing_ch.category == category:
                    setup_msg += f"⏭️  Channel exists: {ch_data['name']}\n"
                    continue
                try:
                    if ch_type == discord.ChannelType.text:
                        await guild.create_text_channel(
                            name=ch_data["name"],
                            category=category,
                            topic=ch_data.get("topic", ""),
                            reason="Teamy Server Setup"
                        )
                    else:
                        await guild.create_voice_channel(
                            name=ch_data["name"],
                            category=category,
                            reason="Teamy Server Setup"
                        )
                    results["channels_created"] += 1
                except Exception as e:
                    setup_msg += f"❌ Failed {ch_data['name']}: {str(e)}\n"
                    results["errors"].append(f"Channel {ch_data['name']}: {str(e)}")
        await interaction.edit_original_response(content=setup_msg)

        # ── STEP 3: Summary ──
        summary = "\n> **Step 3/3: Complete!** 🎉\n\n"
        summary += f"✅ **Roles:** Created {results['roles_created']}, Skipped {results['roles_skipped']}\n"
        summary += f"✅ **Categories:** Created {results['categories_created']}\n"
        summary += f"✅ **Channels:** Created {results['channels_created']}\n"
        if results["errors"]:
            summary += f"\n⚠️ **{len(results['errors'])} warnings/errors:**\n"
            for err in results["errors"][:5]:
                summary += f"  • {err}\n"
            if len(results["errors"]) > 5:
                summary += f"  • ...and {len(results['errors']) - 5} more\n"
        summary += "\n**Next steps:**\n"
        summary += "1. Move Teamy's role ABOVE all other roles in Server Settings → Roles\n"
        summary += "2. Check channel permissions — especially the 🔒 STAFF AREA category\n"
        summary += "3. Run `/ticket-panel` in #📩│ticket-panel to post your ticket buttons\n"
        summary += "4. Run `/setup roles` and `/setup channels` to link everything to the bot\n"

        await interaction.edit_original_response(content=setup_msg + summary)


async def setup(bot):
    await bot.add_cog(ServerSetupCog(bot))