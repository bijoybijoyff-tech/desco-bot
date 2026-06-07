import logging
import json
import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
)

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DATA_FILE = "users.json"
DHAKA_TZ = pytz.timezone("Asia/Dhaka")
NOTIFY_HOUR = 21   # 9 PM
NOTIFY_MINUTE = 0

# Conversation states
ASK_METER, ASK_SCHEDULE = range(2)

# ─────────────────────────────────────────────
# Persistence helpers
# ─────────────────────────────────────────────
def load_users() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ─────────────────────────────────────────────
# DESCO balance scraper
# ─────────────────────────────────────────────
def fetch_balance(meter_no: str) -> str:
    """
    Scrape balance from DESCO prepaid portal.
    Returns a formatted string or an error message.
    """
    url = "https://prepaid.desco.org.bd/api/bill/selectedMeterInfo"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://prepaid.desco.org.bd/",
        "Origin": "https://prepaid.desco.org.bd",
    }
    payload = {"meteringPoint": meter_no}

    try:
        resp = requests.post(url, headers=headers, data=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # DESCO returns a list; pick the first item
        if isinstance(data, list) and len(data) > 0:
            item = data[0]
        elif isinstance(data, dict):
            item = data
        else:
            return None

        balance = item.get("currentBalance") or item.get("balance") or item.get("CurrentBalance")
        name    = item.get("customerName") or item.get("CustomerName") or "N/A"
        account = item.get("accountNo") or item.get("AccountNo") or meter_no

        if balance is None:
            return None

        now = datetime.now(DHAKA_TZ).strftime("%d %b %Y, %I:%M %p")
        return (
            f"Meter No   : {account}\n"
            f"Customer   : {name}\n"
            f"Balance    : {balance} BDT\n"
            f"Checked at : {now} (BD Time)"
        )

    except Exception as e:
        logger.error("fetch_balance error: %s", e)
        return None

# ─────────────────────────────────────────────
# Scheduled job
# ─────────────────────────────────────────────
def send_daily_notifications(context: CallbackContext):
    users = load_users()
    for chat_id, info in users.items():
        if not info.get("notify"):
            continue
        meter_no = info.get("meter_no")
        if not meter_no:
            continue
        result = fetch_balance(meter_no)
        if result:
            msg = f"Good evening! Your daily balance update:\n\n{result}"
        else:
            msg = (
                f"Could not fetch balance for meter {meter_no}. "
                "The DESCO portal may be temporarily unavailable."
            )
        try:
            context.bot.send_message(chat_id=int(chat_id), text=msg)
        except Exception as e:
            logger.error("Failed to notify %s: %s", chat_id, e)

# ─────────────────────────────────────────────
# /start command
# ─────────────────────────────────────────────
def start(update: Update, context: CallbackContext) -> int:
    update.message.reply_text(
        "Welcome to the DESCO Prepaid Meter Balance Bot!\n\n"
        "Please enter your prepaid meter number to check your balance."
    )
    return ASK_METER

# ─────────────────────────────────────────────
# Receive meter number
# ─────────────────────────────────────────────
def receive_meter(update: Update, context: CallbackContext) -> int:
    meter_no = update.message.text.strip()

    if not re.match(r"^\d{6,20}$", meter_no):
        update.message.reply_text(
            "Invalid meter number. Please enter a valid numeric meter number (6-20 digits)."
        )
        return ASK_METER

    update.message.reply_text("Fetching your balance, please wait...")
    result = fetch_balance(meter_no)

    if result is None:
        update.message.reply_text(
            "Could not fetch balance. Please check the meter number and try again.\n\n"
            "If the problem persists, the DESCO portal may be temporarily down."
        )
        return ASK_METER

    update.message.reply_text(f"Balance Details:\n\n{result}")

    # Save meter number temporarily
    context.user_data["meter_no"] = meter_no

    # Ask about daily notification
    reply_keyboard = [["Yes", "No"]]
    update.message.reply_text(
        "Would you like to receive an automatic balance notification every day at 9:00 PM (BD Time)?",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return ASK_SCHEDULE

# ─────────────────────────────────────────────
# Receive schedule preference
# ─────────────────────────────────────────────
def receive_schedule(update: Update, context: CallbackContext) -> int:
    choice = update.message.text.strip().lower()
    chat_id = str(update.effective_chat.id)
    meter_no = context.user_data.get("meter_no")

    users = load_users()
    users[chat_id] = {
        "meter_no": meter_no,
        "notify": choice == "yes",
    }
    save_users(users)

    if choice == "yes":
        update.message.reply_text(
            "Great! You will receive daily balance notifications at 9:00 PM (BD Time).\n\n"
            "Use /stop to cancel notifications anytime.\n"
            "Use /check to check balance manually.",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        update.message.reply_text(
            "No problem! No scheduled notifications will be sent.\n\n"
            "Use /check anytime to check your balance manually.",
            reply_markup=ReplyKeyboardRemove(),
        )

    return ConversationHandler.END

# ─────────────────────────────────────────────
# /check command — manual balance check
# ─────────────────────────────────────────────
def check(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    users = load_users()
    user = users.get(chat_id)

    if not user or not user.get("meter_no"):
        update.message.reply_text(
            "No meter number saved. Please use /start to register your meter."
        )
        return

    update.message.reply_text("Fetching your balance, please wait...")
    result = fetch_balance(user["meter_no"])

    if result:
        update.message.reply_text(f"Balance Details:\n\n{result}")
    else:
        update.message.reply_text(
            "Could not fetch balance. The DESCO portal may be temporarily unavailable. "
            "Please try again later."
        )

# ─────────────────────────────────────────────
# /stop command — cancel notifications
# ─────────────────────────────────────────────
def stop(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    users = load_users()

    if chat_id in users:
        users[chat_id]["notify"] = False
        save_users(users)
        update.message.reply_text(
            "Daily notifications have been cancelled.\n"
            "Use /check to check your balance manually anytime."
        )
    else:
        update.message.reply_text("You have no active notifications to cancel.")

# ─────────────────────────────────────────────
# /status command
# ─────────────────────────────────────────────
def status(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    users = load_users()
    user = users.get(chat_id)

    if not user:
        update.message.reply_text("No data found. Use /start to register.")
        return

    notify_status = "Enabled (9:00 PM daily)" if user.get("notify") else "Disabled"
    update.message.reply_text(
        f"Your registered meter : {user.get('meter_no', 'N/A')}\n"
        f"Daily notification    : {notify_status}\n\n"
        "Commands:\n"
        "/check  - Check balance now\n"
        "/stop   - Cancel notifications\n"
        "/start  - Change meter number"
    )

# ─────────────────────────────────────────────
# /cancel — cancel conversation
# ─────────────────────────────────────────────
def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text(
        "Cancelled. Use /start to begin again.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher
    jq = updater.job_queue

    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_METER: [MessageHandler(Filters.text & ~Filters.command, receive_meter)],
            ASK_SCHEDULE: [MessageHandler(Filters.text & ~Filters.command, receive_schedule)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler("check", check))
    dp.add_handler(CommandHandler("stop", stop))
    dp.add_handler(CommandHandler("status", status))

    # Schedule daily notification at 9 PM Dhaka time = 15:00 UTC
    jq.run_daily(
        send_daily_notifications,
        time=datetime.now(DHAKA_TZ).replace(
            hour=NOTIFY_HOUR, minute=NOTIFY_MINUTE, second=0, microsecond=0
        ).timetz(),
    )

    logger.info("Bot started. Polling...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
