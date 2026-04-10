# main.py - Telegram Bot for SMS Bomber
import os
import logging
import json
import asyncio
import random
import string
from datetime import datetime, timedelta
from typing import Dict, Optional
import sqlite3

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ConversationHandler
)
from telegram.constants import ParseMode

# Import your bomber
import subprocess
import sys

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %%(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = "8590454214:AAGFfuJuqGVOLXUYMDGt7INNV9Q_DrtmbQg"  # Replace with your bot token
ADMIN_ID = 8057802706  # Replace with your Telegram user ID

# States for conversation
WAITING_NUMBER = 1
WAITING_REDEEM_CODE = 2
WAITING_ADMIN_MSG = 3
WAITING_REDEEM_AMOUNT = 4
WAITING_GIFT_USER = 5
WAITING_GIFT_AMOUNT = 6
WAITING_NOTICE_MSG = 7

# Database setup
def init_db():
    conn = sqlite3.connect('bomber_bot.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  credits INTEGER DEFAULT 0,
                  refers INTEGER DEFAULT 0,
                  referred_by INTEGER DEFAULT 0,
                  joined_date TIMESTAMP,
                  last_bonus TIMESTAMP,
                  subscription_end TIMESTAMP)''')
    
    # Redeem codes table
    c.execute('''CREATE TABLE IF NOT EXISTS redeem_codes
                 (code TEXT PRIMARY KEY,
                  credits INTEGER,
                  created_by INTEGER,
                  created_at TIMESTAMP,
                  expires_at TIMESTAMP,
                  used_by INTEGER DEFAULT 0,
                  is_used INTEGER DEFAULT 0)''')
    
    # Attack logs table
    c.execute('''CREATE TABLE IF NOT EXISTS attack_logs
                 (id INTEGER PRIMARY
                 KEY AUTOINCREMENT,
                  user_id INTEGER,
                  target_number TEXT,
                  requests_sent INTEGER,
                  attack_time TIMESTAMP)''')
    
    conn.commit()
    conn.close()

init_db()

# Helper functions
def get_user(user_id: int) -> Optional[Dict]:
    conn = sqlite3.connect('bomber_bot.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    if user:
        return {
            'user_id': user[0],
            'username': user[1],
            'first_name': user[2],
            'credits': user[3],
            'refers': user[4],
            'referred_by': user[5],
            'joined_date': user[6],
            'last_bonus': user[7],
            'subscription_end': user[8]
        }
    return None

def add_user(user_id: int, username: str, first_name: str, referred_by: int = 0):
    conn = sqlite3.connect('bomber_bot.db')
    c = conn.cursor()
    
    # Check if user exists
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if c.fetchone():
        conn.close()
        return
    
    # Add user
    now = datetime.now()
    c.execute("INSERT INTO users (user_id, username, first_name, credits, refers, referred_by, joined_date, last_bonus) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (user_id, username, first_name, 0, 0, referred_by, now, now - timedelta(days=1)))
    
    # Add referral credits if referred
    if referred_by > 0:
        c.execute("UPDATE users SET credits = credits + 5 WHERE user_id = ?", (referred_by,))
        c.execute("UPDATE users SET refers = refers + 1 WHERE user_id = ?", (referred_by,))
    
    conn.commit()
    conn.close()

def update_credits(user_id: int, amount: int):
    conn = sqlite3.connect('bomber_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_daily_bonus(user_id: int) -> bool:
    conn = sqlite3.connect('bomber_bot.db')
    c = conn.cursor()
    c.execute("SELECT last_bonus FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    if result:
        last_bonus = datetime.fromisoformat(result[0]) if result[0] else None
        if last_bonus and datetime.now() - last_bonus < timedelta(days=1):
            conn.close()
            return False
        # Update last bonus
        now = datetime.now()
        c.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (now.isoformat(), user_id))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def check_subscription(user_id: int) -> bool:
    conn = sqlite3.connect('bomber_bot.db')
    c = conn.cursor()
    c.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    if result and result[0]:
        expiry = datetime.fromisoformat(result[0])
        return datetime.now() < expiry
    return False

def add_subscription(user_id: int, days: int):
    conn = sqlite3.connect('bomber_bot.db')
    c = conn.cursor()
    c.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    if result and result[0]:
        expiry = datetime.fromisoformat(result[0])
        if datetime.now() < expiry:
            new_expiry = expiry + timedelta(days=days)
        else:
            new_expiry = datetime.now() + timedelta(days=days)
    else:
        new_expiry = datetime.now() + timedelta(days=days)
    
    c.execute("UPDATE users SET subscription_end = ? WHERE user_id = ?", 
              (new_expiry.isoformat(), user_id))
    conn.commit()
    conn.close()
    def log_attack(user_id: int, target_number: str, requests_sent: int):
    conn = sqlite3.connect('bomber_bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO attack_logs (user_id, target_number, requests_sent, attack_time) VALUES (?, ?, ?, ?)",
              (user_id, target_number, requests_sent, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def create_redeem_code(credits: int, admin_id: int) -> str:
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
    conn = sqlite3.connect('bomber_bot.db')
    c = conn.cursor()
    expires_at = datetime.now() + timedelta(days=1)
    c.execute("INSERT INTO redeem_codes (code, credits, created_by, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
              (code, credits, admin_id, datetime.now().isoformat(), expires_at.isoformat()))
    conn.commit()
    conn.close()
    return code

def redeem_code(code: str, user_id: int) -> int:
    conn = sqlite3.connect('bomber_bot.db')
    c = conn.cursor()
    c.execute("SELECT credits, is_used, expires_at FROM redeem_codes WHERE code = ?", (code,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        return -1  # Invalid code
    
    credits, is_used, expires_at = result
    
    if is_used:
        conn.close()
        return -2  # Already used
    
    if datetime.now() > datetime.fromisoformat(expires_at):
        conn.close()
        return -3  # Expired
    
    # Mark as used and add credits
    c.execute("UPDATE redeem_codes SET is_used = 1, used_by = ? WHERE code = ?", (user_id, code))
    c.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (credits, user_id))
    conn.commit()
    conn.close()
    return credits  # Success

def send_notice_to_all(notice: str):
    conn = sqlite3.connect('bomber_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    return [user[0] for user in users]

async def start_bombing(target_number: str, user_id: int) -> int:
    """Run the bomber script and return number of requests sent"""
    # Create a temporary Python script to run the bomber
    bomber_code = f'''
#!/usr/bin/env python3
import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import and run bomber
from bom import _format_phone_number, _ServiceManager, _state, _clear_screen, _print_banner, _animate_loading
import aiohttp
import asyncio

async def run_bomb():
    phone_data = _format_phone_number("{target_number}")
    service_manager = _ServiceManager(phone_data)
    
    # Set fast mode
    import bom
    bom._current_mode = 'fast'
    
    # Run attack
    await service_manager._run_all_services_fast()
    
    # Return total sent
    return bom._state['total']

if __name__ == "__main__":
    result = asyncio.run(run_bomb())
    print(f"TOTAL_SENT:{{result}}")
'''
    
    # Write to temp file
    with open('temp_bomber.py', 'w', encoding='utf-8') as f:
        f.write(bomber_code)
    
    # Run the bomber
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, 'temp_bomber.py',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        # Clean up
        os.remove('temp_bomber.py')
        
        # Parse output
        output = stdout.decode('utf-8')
        for line in output.split('\n'):
            if line.startswith('TOTAL_SENT:'):
                return int(line.split(':')[1])
                return 0
    except Exception as e:
        logger.error(f"Bombing error: {e}")
        return 0

# Main menu keyboard
def get_main_keyboard(user_id: int):
    user = get_user(user_id)
    credits = user['credits'] if user else 0
    
    keyboard = [
        [InlineKeyboardButton("📟 Start Attack", callback_data="attack")],
        [InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("💎 Buy Subscription", callback_data="buy")],
        [InlineKeyboardButton("📉 Refer & Earn", callback_data="refer")],
        [InlineKeyboardButton("🔋 Daily Bonus", callback_data="bonus")],
        [InlineKeyboardButton("🎫 Redeem Code", callback_data="redeem")],
        [InlineKeyboardButton("📞 Support", callback_data="support")]
    ]
    
    # Add admin buttons if user is admin
    if user_id == ADMIN_ID:
        keyboard.extend([
            [InlineKeyboardButton("🛠️ Admin Panel", callback_data="admin_panel")]
        ])
    
    return InlineKeyboardMarkup(keyboard)

# Admin panel keyboard
def get_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("📟 Make Redeem Code", callback_data="admin_make_redeem")],
        [InlineKeyboardButton("🎁 Gift Credits", callback_data="admin_gift")],
        [InlineKeyboardButton("🧑‍💻 Send Notice", callback_data="admin_notice")],
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Start command
async def start(update: Update, context):
    user = update.effective_user
    
    # Check for refer parameter
    refer_id = context.args[0] if context.args else None
    
    # Add user to database
    add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        referred_by=int(refer_id) if refer_id and refer_id.isdigit() else 0
    )
    
    welcome_text = f"""
🔥 *WELCOME TO ULTIMATE SMS BOMBER BOT* 🔥

━━━━━━━━━━━━━━━━━━━━━━━
💀 *Features:* 
├ 📟 45+ APIs Integration
├ ⚡ Fast & Slow Modes
├ 💳 Credit System
├ 🎁 Daily Bonus
└ 📉 Refer & Earn
━━━━━━━━━━━━━━━━━━━━━━━

⚠️ *WARNING:* Use at your own risk!
📱 Target any Bangladesh number

✅ *Please join our groups to continue:*
"""
    
    # Group join buttons
    keyboard = [
        [InlineKeyboardButton("📢 Group 1", url="https://t.me/join_group_1_link")],
        [InlineKeyboardButton("📢 Group 2", url="https://t.me/join_group_2_link")],
        [InlineKeyboardButton("✅ I've Joined Both", callback_data="check_join")]
    ]
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Check join callback
async def check_join(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    # Here you can implement group join check logic
    # For now, we'll just proceed
    
    await query.edit_message_text(
        "✅ *Verification Complete!*\n\n"
        "Welcome to the bomber! Use the menu below to start bombing.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await query.message.reply_text(
        "🎯 *Main Menu*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard(query.from_user.id)
    )

# Main menu handler
async def main_menu(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🎯 *Main Menu*\n\nSelect an option:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard(query.from_user.id)
    )

# Attack handler
async def attack_start(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    
    # Check credits
    if user['credits'] <= 0 and not check_subscription(user_id):
        await query.edit_message_text(
            "❌ *Insufficient Credits!*\n\n"
            "You need credits to start bombing.\n"
            "• Get Daily Bonus (5 credits/day)\n"
            "• Refer friends (5 credits/refer)\n"
            "• Buy Subscription\n"
            "• Use Redeem Code",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    # Ask for phone number
    await query.edit_message_text(
        "📱 *Enter Target Number*\n\n"
        "Example: `017XXXXXXXX`\n"
        "Or: `01XXXXXXXXX`\n\n"
        "Send the number now:",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_NUMBER

# Handle phone number input
async def handle_number(update: Update, context):
    user_id = update.effective_user.id
    number = update.message.text.strip()
    
    # Validate number
    cleaned = ''.join(filter(str.isdigit, number))
    if not cleaned or len(cleaned) < 10:
        await update.message.reply_text(
            "❌ *Invalid phone number!*\n\n"
            "Please send a valid Bangladesh number.\n"
            "Example: `017XXXXXXXX`",
            parse_mode=ParseMode.MARKDOWN
        )
        return WAITING_NUMBER
    
    await update.message.reply_text(
        f"🚀 *SMS Attack Started!*\n\n"
        f"📱 Target: `{number}`\n"
        f"⚡ Mode: Fast (45+ APIs)\n"
        f"💳 Credits Used: 1\n\n"
        f"⏳ Bombing in progress...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Deduct credit
    update_credits(user_id, -1)
    
    # Start bombing
    sent_count = await start_bombing(number, user_id)
    
    # Log attack
    log_attack(user_id, number, sent_count)
    
    await update.message.reply_text(
        f"✅ *Attack Session Finished!*\n\n"
        f"📱 Target: `{number}`\n"
        f"⚡ Total Sent: `{sent_count}+` SMS\n"
        f"💳 Credits Remaining: {get_user(user_id)['credits']}\n\n"
        f"Use /start to return to main menu.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationHandler.END

# Profile handler
async def profile(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not user:
        await query.edit_message_text("Error: User not found!")
        return
    
    sub_status = "✅ Active" if check_subscription(user_id) else "❌ Inactive"
    if user['subscription_end']:
        expiry = datetime.fromisoformat(user['subscription_end'])
        if datetime.now() < expiry:
            days_left = (expiry - datetime.now()).days
            sub_status = f"✅ Active ({days_left} days left)"
    
    profile_text = f"""
👤 *MY PROFILE*

━━━━━━━━━━━━━━━━━━━━━━━
🆔 *User ID:* `{user['user_id']}`
👤 *Name:* {user['first_name'] or 'Unknown'}
🔰 *Role:* User 👤
💳 *Credits:* `{user['credits']}`
👥 *Refers:* `{user['refers']}`
💎 *Subscription:* {sub_status}
━━━━━━━━━━━━━━━━━━━━━━━

*To get more credits:*
• Daily Bonus (5 credits/day)
• Refer friends (5 credits/refer)
• Buy Subscription
"""
    
    await query.edit_message_text(
        profile_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard(user_id)
    )

# Buy subscription handler
async def buy_subscription(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    buy_text = """
━━━━━━━━━━━━━━━━━
🛒 *BUY SUBSCRIPTION*

┌ 📞 *7 Days Unlimited* — 20 TK
├ 📞 *15 Days Unlimited* — 50 TK
├ 📞 *1 Month Unlimited* — 100 TK
━━━━━━━━━━━━━━━━━

💳 *Payment:* bKash / Nagad
⚡ *Delivery:* Instant

📩 *To subscribe, contact admin:*

👨‍💻 *Admin:* @codex_haseb
"""
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]
    
    await query.edit_message_text(
        buy_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Refer & Earn handler
async def refer_earn(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    bot_username = context.bot.username
    
    refer_link = f"https://t.me/{bot_username}?start={user_id}"
    
    refer_text = f"""
💸 *REFER & EARN*
━━━━━━━━━━━━━━━━━━━━━━━
🔗 *Your Invite Link:*
`{refer_link}`

🎁 *Reward:* 5 Credits/Refer!

📊 *Total Refers:* {get_user(user_id)['refers']}
━━━━━━━━━━━━━━━━━━━━━━━

*How it works:*
1. Share your invite link
2. Friend joins via your link
3. You get 5 credits instantly!
4. Your friend starts with 0 credits

*Share this link with friends!*
"""
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]
    
    await query.edit_message_text(
        refer_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Daily Bonus handler
async def daily_bonus(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if get_daily_bonus(user_id):
        update_credits(user_id, 5)
        user = get_user(user_id)
        
        await query.edit_message_text(
            f"✅ *Daily Bonus Claimed!*\n\n"
            f"🎁 +5 Credits Added!\n"
            f"💳 Total Credits: `{user['credits']}`\n\n"
            f"Come back tomorrow for more!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard(user_id)
        )
    else:
        user = get_user(user_id)
        if user['last_bonus']:
            last_bonus = datetime.fromisoformat(user['last_bonus'])
            next_bonus = last_bonus + timedelta(days=1)
            time_left = next_bonus - datetime.now()
            hours = time_left.seconds // 3600
            minutes = (time_left.seconds % 3600) // 60
            
            await query.edit_message_text(
                f"⏳ *Daily Bonus Already Claimed!*\n\n"
                f"Next bonus available in:\n"
                f"`{hours}h {minutes}m`\n\n"
                f"💳 Current Credits: `{user['credits']}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_main_keyboard(user_id)
            )
        else:
            await query.edit_message_text(
                "❌ *Error!*\n\nPlease try again later.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_main_keyboard(user_id)
            )

# Redeem code handler
async def redeem_start(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🎟️ *Enter Redeem Code*\n\n"
        "Send your redeem code now:",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_REDEEM_CODE

async def handle_redeem(update: Update, context):
    user_id = update.effective_user.id
    code = update.message.text.strip().upper()
    
    result = redeem_code(code, user_id)
    
    if result == -1:
        await update.message.reply_text("❌ *Invalid Redeem Code!*\n\nPlease check and try again.", parse_mode=ParseMode.MARKDOWN)
    elif result == -2:
        await update.message.reply_text("❌ *Code Already Used!*\n\nThis code has already been redeemed.", parse_mode=ParseMode.MARKDOWN)
    elif result == -3:
        await update.message.reply_text("❌ *Code Expired!*\n\nThis code is no longer valid.", parse_mode=ParseMode.MARKDOWN)
    else:
        user = get_user(user_id)
        await update.message.reply_text(
            f"✅ *Redeem Successful!*\n\n"
            f"🎁 +{result} Credits Added!\n"
            f"💳 Total Credits: `{user['credits']}`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    await update.message.reply_text(
        "🎯 *Main Menu*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard(user_id)
    )
    return ConversationHandler.END

# Support handler
async def support(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    support_text = """
☎️ *SUPPORT CENTER*
━━━━━━━━━━━━━━━━━━━━━━━
👨‍💻 *Admin:* @codex_haseb
🛠️ *Developer:* @codex_haseb
📧 *Contact for:* 
  • Issues/Bugs
  • Subscription Purchase
  • Report Problems
  • Feature Requests
━━━━━━━━━━━━━━━━━━━━━━━

*Response Time:* Within 24 hours
"""
    
    await query.edit_message_text(
        support_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard(user_id)
    )

# Admin Panel
async def admin_panel(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ Access Denied!", reply_markup=get_main_keyboard(query.from_user.id))
        return
    
    await query.edit_message_text(
        "🛠️ *Admin Panel*\n\nSelect an option:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )

async def admin_make_redeem(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    await query.edit_message_text(
        "📟 *Create Redeem Code*\n\n"
        "Enter the amount of credits for this code:",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_REDEEM_AMOUNT

async def handle_redeem_amount(update: Update, context):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return ConversationHandler.END
    
    try:
        amount = int(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid amount! Please enter a positive number.")
        return WAITING_REDEEM_AMOUNT
    
    code = create_redeem_code(amount, user_id)
    
    await update.message.reply_text(
        f"✅ *Redeem Code Created!*\n\n"
        f"💳 Credits: `{amount}`\n"
        f"🔑 Code: `{code}`\n"
        f"⏰ Expires: 24 hours\n\n"
        f"Share this code with users!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )
    return ConversationHandler.END

async def admin_gift(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    await query.edit_message_text(
        "🎁 *Gift Credits*\n\n"
        "Enter the user ID to gift:",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_GIFT_USER

async def handle_gift_user(update: Update, context):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return ConversationHandler.END
    
    try:
        target_user = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID! Please enter a number.")
        return WAITING_GIFT_USER
    
    context.user_data['gift_target'] = target_user
    
    await update.message.reply_text(
        f"📝 Enter credit amount to gift to user `{target_user}`:",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_GIFT_AMOUNT

async def handle_gift_amount(update: Update, context):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return ConversationHandler.END
    
    try:
        amount = int(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid amount! Please enter a positive number.")
        return WAITING_GIFT_AMOUNT
    
    target_user = context.user_data.get('gift_target')
    if target_user:
        update_credits(target_user, amount)
        await update.message.reply_text(
            f"✅ *Gift Sent!*\n\n"
            f"🎁 +{amount} credits to user `{target_user}`\n\n"
            f"User can check their updated balance in profile.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )
    
    return ConversationHandler.END

async def admin_notice(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    await query.edit_message_text(
        "📢 *Send Notice*\n\n"
        "Enter the message to broadcast to all users:",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_NOTICE_MSG

async def handle_notice(update: Update, context):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return ConversationHandler.END
    
    notice = update.message.text.strip()
    users = send_notice_to_all(notice)
    
    sent = 0
    for uid in users:
        try:
            await context.bot.send_message(
                uid,
                f"📢 *NOTICE FROM ADMIN*\n\n{notice}",
                parse_mode=ParseMode.MARKDOWN
            )
            sent += 1
            await asyncio.sleep(0.1)  # Rate limit
        except:
            pass
    
    await update.message.reply_text(
        f"✅ *Notice Sent!*\n\n"
        f"📨 Delivered to: `{sent}` users",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )
    return ConversationHandler.END

async def admin_stats(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    conn = sqlite3.connect('bomber_bot.db')
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    c.execute("SELECT SUM(credits) FROM users")
    total_credits = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM redeem_codes WHERE is_used = 0")
    active_codes = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM attack_logs WHERE attack_time > datetime('now', '-7 days')")
    attacks_week = c.fetchone()[0]
    
    conn.close()
    
    stats_text = f"""
📊 *BOT STATISTICS*
━━━━━━━━━━━━━━━━━━━━━━━
👥 *Total Users:* `{total_users}`
💳 *Total Credits:* `{total_credits}`
🎫 *Active Codes:* `{active_codes}`
⚡ *Attacks (7d):* `{attacks_week}`
━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    await query.edit_message_text(
        stats_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )

# Cancel handler
async def cancel(update: Update, context):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

def main():
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Attack conversation
    attack_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(attack_start, pattern="attack")],
        states={
            WAITING_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_number)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Redeem conversation
    redeem_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(redeem_start, pattern="redeem")],
        states={
            WAITING_REDEEM_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_redeem)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Admin redeem conversation
    admin_redeem_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_make_redeem, pattern="admin_make_redeem")],
        states={
            WAITING_REDEEM_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_redeem_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Admin gift conversation
    admin_gift_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_gift, pattern="admin_gift")],
        states={
            WAITING_GIFT_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gift_user)],
            WAITING_GIFT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gift_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Admin notice conversation
    admin_notice_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_notice, pattern="admin_notice")],
        states={
            WAITING_NOTICE_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_notice)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(check_join, pattern="check_join"))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="back_to_main"))
    application.add_handler(CallbackQueryHandler(profile, pattern="profile"))
    application.add_handler(CallbackQueryHandler(buy_subscription, pattern="buy"))
    application.add_handler(CallbackQueryHandler(refer_earn, pattern="refer"))
    application.add_handler(CallbackQueryHandler(daily_bonus, pattern="bonus"))
    application.add_handler(CallbackQueryHandler(support, pattern="support"))
    application.add_handler(CallbackQueryHandler(admin_panel, pattern="admin_panel"))
    application.add_handler(CallbackQueryHandler(admin_stats, pattern="admin_stats"))
    
    application.add_handler(attack_conv)
    application.add_handler(redeem_conv)
    application.add_handler(admin_redeem_conv)
    application.add_handler(admin_gift_conv)
    application.add_handler(admin_notice_conv)
    
    # Start bot
    print("🤖 Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()