import os
import asyncio
import random
import string
from datetime import datetime, timedelta

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from config import BOT_TOKEN, MONGODB_URI, MONGODB_NAME, ADMIN_USER_ID

# Initialize bot and database
bot = Client("ytapi_bot", bot_token=BOT_TOKEN, api_id=12345, api_hash="your_api_hash")  # Replace api_id/hash
mongo = MongoClient(MONGODB_URI)
db = mongo[MONGODB_NAME]
keys_col = db["api_keys"]

# Generate unique API key
def generate_key():
    return "MAFIAYT-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

# Daily reset logic
async def reset_usage_daily():
    while True:
        now = datetime.utcnow()
        next_reset = datetime.combine(now + timedelta(days=1), datetime.min.time())
        await asyncio.sleep((next_reset - now).total_seconds())

        keys_col.update_many({}, {"$set": {"used": 0}})
        # Notify users
        for key in keys_col.find():
            if key.get("user_id"):
                try:
                    await bot.send_message(
                        key["user_id"],
                        f"🔁 Your API key `{key['key']}` usage has been reset for today."
                    )
                except: pass
        # Notify admin
        await bot.send_message(ADMIN_USER_ID, "✅ Daily API usage reset completed for all keys.")

# Start command with buttons
@bot.on_message(filters.command("start"))
async def start_handler(_, msg: Message):
    user = msg.from_user.first_name
    buttons = [
        [InlineKeyboardButton("📖 API Docs", url="https://yourapi.com/docs")],
        [InlineKeyboardButton("📢 Updates", url="https://t.me/YourChannel")]
    ]
    if msg.from_user.id == ADMIN_USER_ID:
        buttons.append([InlineKeyboardButton("⚙️ Admin Commands", callback_data="admin_cmds")])

    await msg.reply_photo(
        photo="https://i.imgur.com/JxzLWeS.png",
        caption=(
            f"👋 **Hello {user}**, Welcome to `MAFIA YT API Bot`\n\n"
            "🚀 Access fast YouTube audio APIs\n"
            "🔐 Use `/mykey` to see your key\n"
            "ℹ️ Use `/help` to learn how to use\n\n"
            "Built by @YourUsername"
        ),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# Help command
@bot.on_message(filters.command("help"))
async def help_handler(_, msg: Message):
    await msg.reply(
        "**📚 How to Use:**\n\n"
        "`/mykey` – View your API key, usage, expiry\n\n"
        "🔗 **Use API like:**\n"
        "`https://yourapi.com/yt?query=your+song&apikey=YOUR_KEY`\n\n"
        "**Admin Commands:** See admin button on /start."
    )

# Show user their key
@bot.on_message(filters.command("mykey"))
async def my_key_handler(_, msg: Message):
    user_id = msg.from_user.id
    key_data = keys_col.find_one({"user_id": user_id})
    if not key_data:
        return await msg.reply("❌ You don’t have an API key yet.")
    await msg.reply(
        f"🔐 **Your API Key:** `{key_data['key']}`\n"
        f"📊 Used: {key_data['used']}/{key_data['limit']} today\n"
        f"⏳ Expires: {key_data['expiry'].strftime('%Y-%m-%d')}"
    )

# Admin inline button
@bot.on_callback_query(filters.regex("admin_cmds"))
async def admin_panel(_, cb: CallbackQuery):
    if cb.from_user.id != ADMIN_USER_ID:
        return await cb.answer("Unauthorized", show_alert=True)
    await cb.message.edit(
        "**🛠 Admin Commands:**\n"
        "`/genkey <limit> <days>` – Create new key\n"
        "`/listkeys` – List all keys\n"
        "`/delkey <KEY>` – Delete specific key",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Back", callback_data="back_start")]]
        )
    )

# Back to start button
@bot.on_callback_query(filters.regex("back_start"))
async def back_start(_, cb: CallbackQuery):
    await start_handler(_, cb.message)

# Admin generate key
@bot.on_message(filters.command("genkey") & filters.user(ADMIN_USER_ID))
async def genkey(_, msg: Message):
    try:
        _, limit, days = msg.text.split()
        key = generate_key()
        keys_col.insert_one({
            "key": key,
            "limit": int(limit),
            "used": 0,
            "expiry": datetime.utcnow() + timedelta(days=int(days)),
            "user_id": None,
            "created_at": datetime.utcnow()
        })
        await msg.reply(
            f"✅ **New API Key Generated**\n\n"
            f"🔐 Key: `{key}`\n📦 Limit: {limit} per day\n🗓 Expiry: {days} days"
        )
    except:
        await msg.reply("❌ Usage: `/genkey <limit> <days>`")

# Admin list all keys
@bot.on_message(filters.command("listkeys") & filters.user(ADMIN_USER_ID))
async def list_keys(_, msg: Message):
    text = "🔐 **All API Keys:**\n\n"
    for k in keys_col.find():
        text += (
            f"`{k['key']}`\n"
            f"Used: {k['used']}/{k['limit']} | Expires: {k['expiry'].strftime('%Y-%m-%d')}\n\n"
        )
    await msg.reply(text or "⚠️ No API keys found.")

# Admin delete key
@bot.on_message(filters.command("delkey") & filters.user(ADMIN_USER_ID))
async def del_key(_, msg: Message):
    try:
        _, key = msg.text.split()
        res = keys_col.delete_one({"key": key})
        if res.deleted_count:
            await msg.reply(f"🗑 Deleted key: `{key}`")
        else:
            await msg.reply("❌ Key not found.")
    except:
        await msg.reply("❌ Usage: `/delkey <API_KEY>`")

# Start bot and daily reset loop
bot.start()
asyncio.create_task(reset_usage_daily())
bot.idle()
