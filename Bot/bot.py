import os
import asyncio
import random
import string
from datetime import datetime, timedelta

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient

# --- Configuration ---
try:
    from config import (
        BOT_TOKEN, MONGODB_URI, MONGODB_NAME, ADMIN_USER_ID,
        API_ID, API_HASH, YOUR_API_BASE_URL, YOUR_API_DOCS_URL,
        YOUR_UPDATES_CHANNEL_URL, YOUR_USERNAME
    )
except ImportError:
    print("ERROR: config.py not found or missing variables. Please create it and fill in your details.")
    exit()

# --- Initialize Bot and Database ---
bot = Client("ytapi_bot_mongo", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)
try:
    mongo_client = MongoClient(MONGODB_URI)
    db = mongo_client[MONGODB_NAME]
    keys_col = db["api_keys"]
    print("Successfully connected to MongoDB.")
except Exception as e:
    print(f"ERROR: Could not connect to MongoDB. Please check your MONGODB_URI in config.py. Details: {e}")
    exit()

# --- Helper Functions ---
def generate_api_key_string():
    """Generates a unique API key string."""
    return "MAFIAYT-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

# --- Daily Reset Logic ---
async def reset_usage_daily():
    print("Daily usage reset task started.")
    while True:
        now = datetime.utcnow()
        # Calculate time until midnight UTC
        next_reset_time = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        sleep_duration = (next_reset_time - now).total_seconds()
        
        print(f"Next daily reset in: {timedelta(seconds=sleep_duration)}")
        await asyncio.sleep(sleep_duration)

        try:
            update_result = keys_col.update_many({}, {"$set": {"used": 0}})
            print(f"Daily API usage reset: {update_result.modified_count} keys updated.")

            # Notify users (optional, can be resource-intensive for many users)
            # for key_doc in keys_col.find({"user_id": {"$ne": None}}):
            #     try:
            #         await bot.send_message(
            #             key_doc["user_id"],
            #             f"🔁 Your API key `{key_doc['key']}` usage has been reset for today."
            #         )
            #     except Exception as e:
            #         print(f"Failed to send reset notification to user {key_doc['user_id']}: {e}")
            
            await bot.send_message(ADMIN_USER_ID, "✅ Daily API usage reset completed for all keys.")
        except Exception as e:
            print(f"Error during daily reset: {e}")
            await bot.send_message(ADMIN_USER_ID, f"⚠️ Error during daily API usage reset: {e}")


# --- Bot Command Handlers ---

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(_, msg: Message):
    user_name = msg.from_user.first_name
    buttons = [
        [InlineKeyboardButton("📖 API Docs", url=YOUR_API_DOCS_URL)],
        [InlineKeyboardButton("📢 Updates Channel", url=YOUR_UPDATES_CHANNEL_URL)]
    ]
    start_photo_url = "https://i.imgur.com/JxzLWeS.png" # Default photo
    
    caption_text = (
        f"👋 **Hello {user_name}**, Welcome to `MAFIA YT API Bot`\n\n"
        "🚀 Access fast YouTube audio APIs.\n"
        "🔐 Use `/mykey` to view your API key details.\n"
        "ℹ️ Use `/help` to learn how to use the API.\n\n"
        f"Built by @{YOUR_USERNAME}"
    )
    try:
        await msg.reply_photo(
            photo=start_photo_url,
            caption=caption_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        print(f"Error sending start message with photo: {e}. Sending text only.")
        await msg.reply_text(caption_text, reply_markup=InlineKeyboardMarkup(buttons))


@bot.on_message(filters.command("help") & filters.private)
async def help_handler(_, msg: Message):
    help_text = (
        "**📚 How to Use This Bot & API:**\n\n"
        "`/start` - Welcome message and main links.\n"
        "`/mykey` - View your personal API key, its usage, and expiry date.\n"
        "`/help` - Shows this help message.\n\n"
        "🔗 **API Usage Example:**\n"
        f"`{YOUR_API_BASE_URL}/yt?query=your+song+name&apikey=YOUR_API_KEY`\n\n"
        "Replace `your+song+name` with the URL-encoded song name or video ID, and `YOUR_API_KEY` with the key obtained from `/mykey`.\n\n"
        "**👑 Admin Commands (Only for Bot Admin):**\n"
        "`/genkey <limit> <days>` – Generate a new API key (not assigned to a user).\n"
        "`/assignkey <user_id_or_username> <limit> <days>` - Generate and assign a key to a user.\n"
        "`/listkeys` – List all API keys in the database.\n"
        "`/delkey <API_KEY_STRING>` – Delete a specific API key.\n"
        "`/getuserkeys <user_id_or_username>` - List keys assigned to a specific user."
    )
    await msg.reply(help_text, parse_mode=enums.ParseMode.MARKDOWN)


@bot.on_message(filters.command("mykey") & filters.private)
async def my_key_handler(_, msg: Message):
    user_id = msg.from_user.id
    key_data = keys_col.find_one({"user_id": user_id})
    
    if not key_data:
        return await msg.reply("❌ You don’t have an API key assigned to you yet. Contact the admin if you need one.")
    
    expiry_date_str = key_data['expiry'].strftime('%Y-%m-%d %H:%M UTC') if key_data.get('expiry') else "Never"
    reply_text = (
        f"🔐 **Your API Key Details:**\n\n"
        f"🔑 Key: `{key_data['key']}`\n"
        f"📊 Usage Today: {key_data.get('used', 0)} / {key_data.get('limit', 'Unlimited')}\n"
        f"⏳ Expires: {expiry_date_str}"
    )
    await msg.reply(reply_text, parse_mode=enums.ParseMode.MARKDOWN)

# --- Admin Commands ---

@bot.on_message(filters.command("genkey") & filters.user(ADMIN_USER_ID))
async def admin_genkey_handler(_, msg: Message):
    try:
        parts = msg.text.split()
        if len(parts) != 3:
            await msg.reply("❌ Usage: `/genkey <limit> <days_to_expiry>`\nExample: `/genkey 100 30` (100 requests/day, expires in 30 days)")
            return
        
        limit = int(parts[1])
        days_to_expiry = int(parts[2])
        
        api_key_str = generate_api_key_string()
        created_at_dt = datetime.utcnow()
        expiry_dt = created_at_dt + timedelta(days=days_to_expiry)
        
        key_document = {
            "key": api_key_str,
            "limit": limit,
            "used": 0,
            "expiry": expiry_dt,
            "user_id": None, # Not assigned to a specific user by this command
            "created_at": created_at_dt,
            "is_active": True
        }
        keys_col.insert_one(key_document)
        
        await msg.reply(
            f"✅ **New Unassigned API Key Generated**\n\n"
            f"🔐 Key: `{api_key_str}`\n"
            f"📦 Limit: {limit} requests/day\n"
            f"🗓 Expires on: {expiry_dt.strftime('%Y-%m-%d %H:%M UTC')} ({days_to_expiry} days from now)"
        )
    except ValueError:
        await msg.reply("❌ Invalid input. Limit and days must be numbers.\nUsage: `/genkey <limit> <days>`")
    except Exception as e:
        await msg.reply(f"An error occurred: {e}")
        print(f"Error in /genkey: {e}")


@bot.on_message(filters.command("assignkey") & filters.user(ADMIN_USER_ID))
async def admin_assignkey_handler(_, msg: Message):
    try:
        parts = msg.text.split()
        if len(parts) != 4:
            await msg.reply("❌ Usage: `/assignkey <user_id_or_username> <limit> <days>`\nExample: `/assignkey @username 100 30` or `/assignkey 123456789 50 7`")
            return

        user_identifier = parts[1]
        limit = int(parts[2])
        days_to_expiry = int(parts[3])

        target_user = None
        try:
            if user_identifier.startswith("@"):
                target_user = await bot.get_users(user_identifier.lstrip("@"))
            else:
                target_user = await bot.get_users(int(user_identifier))
        except Exception as e:
            await msg.reply(f"❌ Could not find user: {user_identifier}. Error: {e}")
            return
        
        if not target_user:
            await msg.reply(f"❌ User not found: {user_identifier}")
            return

        # Check if user already has a key, optionally update or disallow
        existing_key = keys_col.find_one({"user_id": target_user.id})
        if existing_key:
            # For simplicity, we'll overwrite. You might want to ask for confirmation or disallow.
            keys_col.delete_one({"user_id": target_user.id})
            await msg.reply(f"ℹ️ User {target_user.first_name} ({target_user.id}) already had a key. It will be replaced.")


        api_key_str = generate_api_key_string()
        created_at_dt = datetime.utcnow()
        expiry_dt = created_at_dt + timedelta(days=days_to_expiry)

        key_document = {
            "key": api_key_str,
            "limit": limit,
            "used": 0,
            "expiry": expiry_dt,
            "user_id": target_user.id,
            "user_first_name": target_user.first_name,
            "user_username": target_user.username,
            "created_at": created_at_dt,
            "is_active": True
        }
        keys_col.insert_one(key_document)

        reply_text = (
            f"✅ **API Key Generated and Assigned**\n\n"
            f"👤 User: {target_user.first_name} (@{target_user.username if target_user.username else 'N/A'}, ID: `{target_user.id}`)\n"
            f"🔐 Key: `{api_key_str}`\n"
            f"📦 Limit: {limit} requests/day\n"
            f"🗓 Expires on: {expiry_dt.strftime('%Y-%m-%d %H:%M UTC')} ({days_to_expiry} days)"
        )
        await msg.reply(reply_text)
        
        # Notify the user
        try:
            await bot.send_message(
                target_user.id,
                f"🎉 Congratulations! You have been assigned a new API key by the admin.\n\n"
                f"🔐 Key: `{api_key_str}`\n"
                f"📦 Limit: {limit} requests/day\n"
                f"🗓 Expires on: {expiry_dt.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                "Use `/mykey` to check your key details anytime."
            )
        except Exception as e:
            await msg.reply(f"⚠️ Could not notify the user {target_user.first_name}. They might have blocked the bot. Error: {e}")

    except ValueError:
        await msg.reply("❌ Invalid input. Limit and days must be numbers.\nUsage: `/assignkey <user_id_or_username> <limit> <days>`")
    except Exception as e:
        await msg.reply(f"An error occurred: {e}")
        print(f"Error in /assignkey: {e}")


@bot.on_message(filters.command("listkeys") & filters.user(ADMIN_USER_ID))
async def admin_listkeys_handler(_, msg: Message):
    all_keys = list(keys_col.find())
    if not all_keys:
        await msg.reply("⚠️ No API keys found in the database.")
        return

    reply_text = "🔐 **All API Keys in Database:**\n\n"
    for key_doc in all_keys:
        expiry_str = key_doc['expiry'].strftime('%Y-%m-%d') if key_doc.get('expiry') else "N/A"
        user_info = f"User ID: {key_doc.get('user_id', 'Unassigned')}"
        if key_doc.get('user_first_name'):
            user_info += f" ({key_doc.get('user_first_name')})"

        reply_text += (
            f"🔑 Key: `{key_doc['key']}`\n"
            f"  📊 Usage: {key_doc.get('used', 0)}/{key_doc.get('limit', 'N/A')}\n"
            f"  ⏳ Expires: {expiry_str}\n"
            f"  👤 {user_info}\n"
            f"  Active: {'Yes' if key_doc.get('is_active', True) else 'No'}\n\n"
        )
        # Telegram message length limit
        if len(reply_text) > 3500:
            await msg.reply(reply_text, parse_mode=enums.ParseMode.MARKDOWN)
            reply_text = "" # Reset for next chunk
    
    if reply_text: # Send any remaining part
        await msg.reply(reply_text, parse_mode=enums.ParseMode.MARKDOWN)


@bot.on_message(filters.command("delkey") & filters.user(ADMIN_USER_ID))
async def admin_delkey_handler(_, msg: Message):
    try:
        parts = msg.text.split()
        if len(parts) != 2:
            await msg.reply("❌ Usage: `/delkey <API_KEY_STRING>`")
            return
        
        key_to_delete = parts[1]
        result = keys_col.delete_one({"key": key_to_delete})
        
        if result.deleted_count > 0:
            await msg.reply(f"🗑 Successfully deleted API key: `{key_to_delete}`")
        else:
            await msg.reply(f"❌ API key not found: `{key_to_delete}`")
            
    except Exception as e:
        await msg.reply(f"An error occurred: {e}")
        print(f"Error in /delkey: {e}")

@bot.on_message(filters.command("getuserkeys") & filters.user(ADMIN_USER_ID))
async def admin_getuserkeys_handler(_, msg: Message):
    try:
        parts = msg.text.split()
        if len(parts) != 2:
            await msg.reply("❌ Usage: `/getuserkeys <user_id_or_username>`")
            return

        user_identifier = parts[1]
        target_user_id = None

        try:
            if user_identifier.startswith("@"):
                target_user_obj = await bot.get_users(user_identifier.lstrip("@"))
                target_user_id = target_user_obj.id if target_user_obj else None
            else:
                target_user_id = int(user_identifier)
        except Exception as e:
            await msg.reply(f"❌ Could not resolve user: {user_identifier}. Error: {e}")
            return
        
        if not target_user_id:
            await msg.reply(f"❌ User not found or invalid identifier: {user_identifier}")
            return

        user_keys = list(keys_col.find({"user_id": target_user_id}))

        if not user_keys:
            await msg.reply(f"⚠️ No API keys found for user ID: `{target_user_id}`.")
            return

        reply_text = f"🔑 **API Keys for User ID `{target_user_id}`:**\n\n"
        for key_doc in user_keys:
            expiry_str = key_doc['expiry'].strftime('%Y-%m-%d') if key_doc.get('expiry') else "N/A"
            reply_text += (
                f"  Key: `{key_doc['key']}`\n"
                f"  Usage: {key_doc.get('used', 0)}/{key_doc.get('limit', 'N/A')}\n"
                f"  Expires: {expiry_str}\n"
                f"  Active: {'Yes' if key_doc.get('is_active', True) else 'No'}\n\n"
            )
        await msg.reply(reply_text, parse_mode=enums.ParseMode.MARKDOWN)

    except ValueError:
        await msg.reply("❌ Invalid User ID format. It should be a number or @username.")
    except Exception as e:
        await msg.reply(f"An error occurred: {e}")
        print(f"Error in /getuserkeys: {e}")


# --- Main Bot Execution ---
async def main():
    print("Starting bot...")
    await bot.start()
    print("Bot started successfully!")
    
    # Start the daily reset task
    asyncio.create_task(reset_usage_daily())
    
    print("Bot is now idle and listening for commands. Press Ctrl+C to stop.")
    await asyncio.Event().wait() # Keep the bot running (replaces idle())

if __name__ == "__main__":
    asyncio.run(main())
