
async def create_ticket(interaction, category, appeal_data=None):
    guild = interaction.guild

    if guild is None:
        return await interaction.response.send_message(
            "Tickets can only be created inside a server.",
            ephemeral=True
        )

    # Give Discord an immediate response so the interaction
    # doesn't expire while the ticket is being created.
    await interaction.response.defer(ephemeral=True, thinking=True)

    guild_config = await get_config(guild.id)

    async with aiosqlite.connect(config.DATABASE) as db:
        async with db.execute("""
            SELECT channel_id
            FROM tickets
            WHERE guild_id = ? AND user_id = ? AND closed = 0
        """, (guild.id, interaction.user.id)) as cursor:
            existing = await cursor.fetchone()

    if existing:
        existing_channel = guild.get_channel(existing[0])

        if existing_channel:
            return await interaction.followup.send(
                f"You already have an open ticket: {existing_channel.mention}",
                ephemeral=True
            )

        async with aiosqlite.connect(config.DATABASE) as db:
            await db.execute("""
                UPDATE tickets SET closed = 1
                WHERE channel_id = ?
            """, (existing[0],))
            await db.commit()

    bot_member = guild.me or guild.get_member(interaction.client.user.id)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False
        ),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True
        ),
        bot_member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            manage_messages=True,
            read_message_history=True
        )
    }

    if guild_config and guild_config[5]:
        staff_role = guild.get_role(guild_config[5])
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

    category_channel = None
    if guild_config and guild_config[6]:
        category_channel = guild.get_channel(guild_config[6])

    channel = await guild.create_text_channel(
        name=f"ticket-{interaction.user.name[:18]}",
        overwrites=overwrites,
        category=category_channel,
        topic=f"{category} ticket for {interaction.user} ({interaction.user.id})"
    )

    async with aiosqlite.connect(config.DATABASE) as db:
        await db.execute("""
            INSERT INTO tickets
            (channel_id, guild_id, user_id, category, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            channel.id,
            guild.id,
            interaction.user.id,
            category,
            datetime.now(timezone.utc).timestamp()
        ))
        await db.commit()

    embed = create_embed(
        f"🎫 Ticket Opened — {category}",
        f"Hello {interaction.user.mention}!\n"
        "A staff member will be with you as soon as possible.\n\n"
        f"**Category:** {category}",
        config.COLOR_TICKET
    )

    if appeal_data:
        embed.add_field(
            name="Why were you banned?",
            value=appeal_data["reason"][:300],
            inline=False
        )
        embed.add_field(
            name="Why should we unban you?",
            value=appeal_data["why"][:300],
            inline=False
        )
        embed.add_field(
            name="What will you do differently?",
            value=appeal_data["changes"][:300],
            inline=False
        )

    await channel.send(
        content=interaction.user.mention,
        embed=embed,
        view=TicketControlView()
    )

    await interaction.followup.send(
        f"✅ Your ticket has been created: {channel.mention}",
        ephemeral=True
    )
