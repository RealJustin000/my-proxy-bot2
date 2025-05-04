import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import os
from keep_alive import keep_alive
import io

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DB_FILE = "bridges.db"

@bot.event
async def on_ready():
    await bot.wait_until_ready()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Sync failed: {e}")
    print(f"Logged in as {bot.user}")
    # Initialize DB
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bridges (
                source_channel_id INTEGER,
                target_channel_id INTEGER
            )
        """)
        await db.commit()

@bot.tree.command(name="proxy", description="Bridge two channels across servers")
@app_commands.describe(channel="The channel you want to link this one to")
async def proxy(interaction: discord.Interaction, channel: discord.TextChannel):
    source = interaction.channel.id
    target = channel.id

    if source == target:
        await interaction.response.send_message("You can't proxy a channel to itself.", ephemeral=True)
        return

    async with aiosqlite.connect(DB_FILE) as db:
        # Check if already exists
        async with db.execute("SELECT 1 FROM bridges WHERE (source_channel_id=? AND target_channel_id=?) OR (source_channel_id=? AND target_channel_id=?)", (source, target, target, source)) as cursor:
            if await cursor.fetchone():
                await interaction.response.send_message("These channels are already bridged.", ephemeral=True)
                return

        await db.execute("INSERT INTO bridges (source_channel_id, target_channel_id) VALUES (?, ?)", (source, target))
        await db.commit()
        await interaction.response.send_message(f"🔗 Bridged this channel with {channel.mention}")

@bot.tree.command(name="unproxy", description="Remove a bridge between this and another channel")
@app_commands.describe(channel="The channel to disconnect from")
async def unproxy(interaction: discord.Interaction, channel: discord.TextChannel):
    source = interaction.channel.id
    target = channel.id

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM bridges WHERE (source_channel_id=? AND target_channel_id=?) OR (source_channel_id=? AND target_channel_id=?)", (source, target, target, source))
        await db.commit()
    await interaction.response.send_message(f"⛔ Unbridged this channel and {channel.mention}")

@bot.tree.command(name="listproxies", description="List active bridges involving this server")
async def listproxies(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    matching = []

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT source_channel_id, target_channel_id FROM bridges") as cursor:
            async for src, tgt in cursor:
                src_ch = bot.get_channel(src)
                tgt_ch = bot.get_channel(tgt)
                if src_ch and tgt_ch and (src_ch.guild.id == guild_id or tgt_ch.guild.id == guild_id):
                    matching.append(f"{src_ch.mention if src_ch else src} ↔️ {tgt_ch.mention if tgt_ch else tgt}")

    if matching:
        await interaction.response.send_message("**🔗 Active Bridges:**
" + "\n".join(matching))
    else:
        await interaction.response.send_message("📭 No bridges involving this server.")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT target_channel_id FROM bridges WHERE source_channel_id=?", (message.channel.id,)) as cursor:
            targets = [row[0] for row in await cursor.fetchall()]
        async with db.execute("SELECT source_channel_id FROM bridges WHERE target_channel_id=?", (message.channel.id,)) as cursor:
            targets += [row[0] for row in await cursor.fetchall()]

    for channel_id in targets:
        target_channel = bot.get_channel(channel_id)
        if target_channel:
            files = []
            for attachment in message.attachments:
                fp = await attachment.read()
                files.append(discord.File(io.BytesIO(fp), filename=attachment.filename))
            await target_channel.send(f"**{message.author.display_name}** from {message.guild.name}:
{message.content}", files=files)

keep_alive()
bot.run(os.getenv("BOT_TOKEN"))