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
    print("Ensure all required variables like BOT_TOKEN, API_ID, API_HASH, MONGODB_URI, MONGODB_NAME, ADMIN_USER_ID are present.")
    exit()
except Exception as e:
    print(f"Error importing from config.py: {e}")
    exit()

# --- Initialize Bot and Database ---
bot = Client("ytapi_bot_mongo", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)
mongo_client = None # Initialize to None
try:
    mongo_client = MongoClient(MONGODB_URI)
    # Test connection
    mongo_client.admin.command('ping') 
    db = mongo_client[MONGODB_NAME]
    keys_col = db["api_keys"]
    print("Successfully connected to MongoDB.")
except Exception as e:
    print(f"ERROR: Could not connect to MongoDB. Please check your MONGODB_URI in config.py. Details: {e}")
    if mongo_client:
        mongo_client.close()
    exit()

# --- Helper Functions ---
def generate_api_key_string():
    """Generates a unique API key string."""
    return "MAFIAYT-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

# --- Daily Reset Logic ---
async def reset_usage_daily():
    print("Daily usage reset task started.")
    while True:
        try:
            now = datetime.utcnow()
            # Calculate time until midnight UTC
            next_reset_time = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            sleep_duration = (next_reset_time - now).total_seconds()
            
            if sleep_duration < 0: # Should not happen if logic is correct, but as a safeguard
                sleep_duration += 24 * 60 * 60

            print(f"Next daily reset in: {timedelta(seconds=sleep_duration)}")
            await asyncio.sleep(sleep_duration)

            update_result = keys_col.update_many({}, {"$set": {"used": 0}})
            print(f"Daily API usage reset: {update_result.modified_count} keys updated.")

            # Notify admin
            try:
                await bot.send_message(ADMIN_USER_ID, f"✅ Daily API usage reset completed. {update_result.modified_count} keys updated.")
            except Exception as e_admin_notify:
                print(f"Failed to send daily reset notification to admin: {e_admin_notify}")
        
        except asyncio.CancelledError:
            print("Daily usage reset task was cancelled.")
            break # Exit the loop if cancelled
        except Exception as e:
            print(f"Error during daily reset cycle: {e}")
            try:
                await bot.send_message(ADMIN_USER_ID, f"⚠️ Error during daily API usage reset cycle: {e}")
            except Exception as e_admin_err_notify:
                 print(f"Failed to send daily reset error notification to admin: {e_admin_err_notify}")
            await asyncio.sleep(60*5) # Wait 5 minutes before retrying the loop if an error occurs

# --- Bot Command Handlers ---

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, msg: Message):
    user_name = msg.from_user.first_name
    buttons = [
        [InlineKeyboardButton("📖 API Docs", url=YOUR_API_DOCS_URL)],
        [InlineKeyboardButton("📢 Updates Channel", url=YOUR_UPDATES_CHANNEL_URL)]
    ]
    start_photo_url = "https://i.imgur.com/JxzLWeS.png" 
    
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
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=enums.ParseMode.MARKDOWN
        )
    except Exception as e:
        print(f"Error sending start message with photo: {e}. Sending text only.")
        await msg.reply_text(caption_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.MARKDOWN)


@bot.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, msg: Message):
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
async def my_key_handler(client: Client, msg: Message):
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
async def admin_genkey_handler(client: Client, msg: Message):
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
            "user_id": None, 
            "created_at": created_at_dt,
            "is_active": True
        }
        keys_col.insert_one(key_document)
        
        await msg.reply(
            f"✅ **New Unassigned API Key Generated**\n\n"
            f"🔐 Key: `{api_key_str}`\n"
            f"📦 Limit: {limit} requests/day\n"
            f"🗓 Expires on: {expiry_dt.strftime('%Y-%m-%d %H:%M UTC')} ({days_to_expiry} days from now)",
            parse_mode=enums.ParseMode.MARKDOWN
        )
    except ValueError:
        await msg.reply("❌ Invalid input. Limit and days must be numbers.\nUsage: `/genkey <limit> <days>`")
    except Exception as e:
        await msg.reply(f"An error occurred: {e}")
        print(f"Error in /genkey: {e}")


@bot.on_message(filters.command("assignkey") & filters.user(ADMIN_USER_ID))
async def admin_assignkey_handler(client: Client, msg: Message):
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
                target_user = await client.get_users(user_identifier.lstrip("@"))
            else:
                target_user = await client.get_users(int(user_identifier))
        except Exception as e:
            await msg.reply(f"❌ Could not find user: {user_identifier}. Error: {e}")
            return
        
        if not target_user: # Should be caught by exception but as a safeguard
            await msg.reply(f"❌ User not found: {user_identifier}")
            return

        existing_key = keys_col.find_one({"user_id": target_user.id})
        if existing_key:
            keys_col.delete_one({"user_id": target_user.id})
            await msg.reply(f"ℹ️ User {target_user.first_name} (`{target_user.id}`) already had a key. It has been replaced.", parse_mode=enums.ParseMode.MARKDOWN)

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
        await msg.reply(reply_text, parse_mode=enums.ParseMode.MARKDOWN)
        
        try:
            await client.send_message(
                target_user.id,
                f"🎉 Congratulations! You have been assigned a new API key by the admin.\n\n"
                f"🔐 Key: `{api_key_str}`\n"
                f"📦 Limit: {limit} requests/day\n"
                f"🗓 Expires on: {expiry_dt.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                "Use `/mykey` to check your key details anytime.",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        except Exception as e:
            await msg.reply(f"⚠️ Could not notify the user {target_user.first_name}. They might have blocked the bot. Error: {e}")

    except ValueError:
        await msg.reply("❌ Invalid input. Limit and days must be numbers.\nUsage: `/assignkey <user_id_or_username> <limit> <days>`")
    except Exception as e:
        await msg.reply(f"An error occurred: {e}")
        print(f"Error in /assignkey: {e}")


@bot.on_message(filters.command("listkeys") & filters.user(ADMIN_USER_ID))
async def admin_listkeys_handler(client: Client, msg: Message):
    all_keys = list(keys_col.find())
    if not all_keys:
        await msg.reply("⚠️ No API keys found in the database.")
        return

    base_reply_text = "🔐 **All API Keys in Database:**\n\n"
    current_reply_segment = base_reply_text

    for key_doc in all_keys:
        expiry_str = key_doc['expiry'].strftime('%Y-%m-%d %H:%M UTC') if key_doc.get('expiry') else "N/A"
        user_info = f"User ID: `{key_doc.get('user_id', 'Unassigned')}`"
        if key_doc.get('user_first_name'):
            user_info += f" ({key_doc.get('user_first_name')})"
        if key_doc.get('user_username'):
             user_info += f" @{key_doc.get('user_username')}"


        key_entry_text = (
            f"🔑 Key: `{key_doc['key']}`\n"
            f"  📊 Usage: {key_doc.get('used', 0)}/{key_doc.get('limit', 'N/A')}\n"
            f"  ⏳ Expires: {expiry_str}\n"
            f"  👤 {user_info}\n"
            f"  엑티브: {'Yes' if key_doc.get('is_active', True) else 'No'}\n\n" # Assuming '엑티브' means 'Active'
        )
        
        if len(current_reply_segment) + len(key_entry_text) > 4000: # Telegram message limit is 4096
            await msg.reply(current_reply_segment, parse_mode=enums.ParseMode.MARKDOWN)
            current_reply_segment = key_entry_text # Start new segment
        else:
            current_reply_segment += key_entry_text
    
    if current_reply_segment and current_reply_segment != base_reply_text : # Send any remaining part
        await msg.reply(current_reply_segment, parse_mode=enums.ParseMode.MARKDOWN)
    elif not all_keys: # Should be caught earlier, but as a safeguard
        await msg.reply("⚠️ No API keys found in the database.")


@bot.on_message(filters.command("delkey") & filters.user(ADMIN_USER_ID))
async def admin_delkey_handler(client: Client, msg: Message):
    try:
        parts = msg.text.split()
        if len(parts) != 2:
            await msg.reply("❌ Usage: `/delkey <API_KEY_STRING>`")
            return
        
        key_to_delete = parts[1]
        result = keys_col.delete_one({"key": key_to_delete})
        
        if result.deleted_count > 0:
            await msg.reply(f"🗑 Successfully deleted API key: `{key_to_delete}`", parse_mode=enums.ParseMode.MARKDOWN)
        else:
            await msg.reply(f"❌ API key not found: `{key_to_delete}`", parse_mode=enums.ParseMode.MARKDOWN)
            
    except Exception as e:
        await msg.reply(f"An error occurred: {e}")
        print(f"Error in /delkey: {e}")

@bot.on_message(filters.command("getuserkeys") & filters.user(ADMIN_USER_ID))
async def admin_getuserkeys_handler(client: Client, msg: Message):
    try:
        parts = msg.text.split()
        if len(parts) != 2:
            await msg.reply("❌ Usage: `/getuserkeys <user_id_or_username>`")
            return

        user_identifier = parts[1]
        target_user_id = None
        target_user_info_str = user_identifier # For display

        try:
            if user_identifier.startswith("@"):
                target_user_obj = await client.get_users(user_identifier.lstrip("@"))
                if target_user_obj:
                    target_user_id = target_user_obj.id
                    target_user_info_str = f"{target_user_obj.first_name} (@{target_user_obj.username if target_user_obj.username else 'N/A'}, ID: `{target_user_id}`)"
            else:
                target_user_id = int(user_identifier)
                # Optionally, try to fetch user details for better display
                try:
                    temp_user = await client.get_users(target_user_id)
                    if temp_user:
                         target_user_info_str = f"{temp_user.first_name} (@{temp_user.username if temp_user.username else 'N/A'}, ID: `{target_user_id}`)"
                except:
                    pass # Keep target_user_info_str as the ID if fetching fails
        except Exception as e:
            await msg.reply(f"❌ Could not resolve user: {user_identifier}. Error: {e}")
            return
        
        if not target_user_id:
            await msg.reply(f"❌ User not found or invalid identifier: {user_identifier}")
            return

        user_keys = list(keys_col.find({"user_id": target_user_id}))

        if not user_keys:
            await msg.reply(f"⚠️ No API keys found for user: {target_user_info_str}.", parse_mode=enums.ParseMode.MARKDOWN)
            return

        reply_text = f"🔑 **API Keys for User {target_user_info_str}:**\n\n"
        for key_doc in user_keys:
            expiry_str = key_doc['expiry'].strftime('%Y-%m-%d %H:%M UTC') if key_doc.get('expiry') else "N/A"
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
    global mongo_client # Ensure we can access the global mongo_client instance
    print("Starting bot...")
    daily_reset_task = None
    try:
        await bot.start()
        print("Bot started successfully!")
        
        daily_reset_task = asyncio.create_task(reset_usage_daily())
        
        print("Bot is now idle and listening for commands. Press Ctrl+C to stop.")
        await asyncio.Event().wait() 
    except KeyboardInterrupt:
        print("\nBot stopping due to KeyboardInterrupt...")
    except Exception as e:
        print(f"An unexpected error occurred in main: {e}")
    finally:
        print("Shutting down bot...")
        if daily_reset_task and not daily_reset_task.done():
            daily_reset_task.cancel()
            try:
                await daily_reset_task 
            except asyncio.CancelledError:
                print("Daily reset task successfully cancelled.")
            except Exception as e_task_cancel:
                print(f"Error during daily_reset_task cancellation: {e_task_cancel}")
        
        if bot.is_initialized and bot.is_connected:
            print("Stopping Pyrogram client...")
            await bot.stop()
            print("Pyrogram client stopped.")
        elif bot.is_initialized:
             print("Pyrogram client was initialized but not connected. Attempting stop anyway.")
             await bot.stop() # Attempt to stop even if not connected, might clean up some internal state
             print("Pyrogram client stop attempted.")
        else:
            print("Pyrogram client was not initialized.")

        if mongo_client:
            print("Closing MongoDB connection...")
            mongo_client.close()
            print("MongoDB connection closed.")
        print("Shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())
