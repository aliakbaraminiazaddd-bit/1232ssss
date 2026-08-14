import logging
import aiosqlite
import random
import string
import json
import io
import asyncio
import os
import time

from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputFile, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes,
    JobQueue
)
from telegram.constants import ParseMode
import qrcode
import httpx

# ==================== تنظیمات ====================
BOT_TOKEN = "8865620196:AAHzsrcyh5Ql0oAqGPlTfn0DSfwPZ7vyzxE"
ADMIN_ID = 8837001390
CHANNEL_USERNAME = "@nexroofficial"
SUPPORT_USERNAME = "@RoTex8"
CARD_NUMBER = "6037701156614445"
CARD_NAME = "حبیب صادقی"
REFERRAL_BONUS = 5000

PANEL_URL = "https://marzban-panel-production-7c00.up.railway.app"
PANEL_USERNAME = "admin"
PANEL_PASSWORD = "12345678sina"

# ==================== محدودیت‌ها ====================
MAX_PENDING_ORDERS = 2
USAGE_WARNING_PERCENT = 85
EXPIRE_WARN_HOURS = 24
AUTO_RENEW_HOURS = 24
BALANCE_WARN_HOURS = 72
TEST_DELETE_AFTER_HOURS = 48

PROXY_PRICE_HOLLAND = 50000
PROXY_PRICE_AMERICA = 35000
PROXY_PRICE_SINGAPORE = 25000
PROXY_PRICE_PER_DAY = 500
PROXY_MIN_QTY = 1
PROXY_MAX_QTY = 50
PROXY_MIN_DAYS = 1
PROXY_MAX_DAYS = 90

# ==================== States ====================
(
    WAITING_USERNAME, WAITING_RECEIPT, WAITING_DISCOUNT,
    WAITING_WALLET_AMOUNT, WAITING_WALLET_RECEIPT,
    ADMIN_ADD_TARIFF_GB, ADMIN_ADD_TARIFF_PRICE,
    ADMIN_WELCOME, ADMIN_RULES, ADMIN_DISCOUNT_CODE,
    ADMIN_DISCOUNT_PERCENT, ADMIN_DISCOUNT_LIMIT, ADMIN_DISCOUNT_EXPIRE,
    ADMIN_BAN, ADMIN_UNBAN, ADMIN_BROADCAST,
    ADMIN_MSG_USER_ID, ADMIN_MSG_TEXT,
    ADMIN_TEST_RECHARGE, ADMIN_ADD_BALANCE_ID,
    ADMIN_ADD_BALANCE_AMOUNT, ADMIN_ADD_BALANCE_NOTE,
    ADMIN_ALL_BALANCE,
    ADMIN_DEDUCT_ID, ADMIN_DEDUCT_AMOUNT,
    ADMIN_SEARCH_USER,
    ADMIN_SET_REFERRAL, ADMIN_SET_MIN_CHARGE,
    ADMIN_SET_SERVICE_DAYS,
    ADMIN_PANEL_NAME, ADMIN_PANEL_URL, ADMIN_PANEL_USER, ADMIN_PANEL_PASS,
    ADMIN_EDIT_TARIFF_GB, ADMIN_EDIT_TARIFF_PRICE,
    WAITING_TICKET, ADMIN_REPLY_TICKET,
    RENEW_WAITING_RECEIPT,
    ADMIN_ADD_ADMIN_ID,
    ADMIN_SET_CHANNEL,
    ADMIN_BROADCAST_ADMINS,
    ADMIN_MSG_ADMIN_TARGET,
    ADMIN_MSG_ADMIN_TEXT,
    ADMIN_WARN_TARGET,
    ADMIN_WARN_TEXT,
    ADMIN_CLEAR_WARN_TARGET,
    CUSTOM_WAITING_GB,
    CUSTOM_WAITING_DAYS,
    ADMIN_SET_CUSTOM_GB_PRICE,
    ADMIN_SET_CUSTOM_DAY_PRICE,
    TRANSFER_WAITING_TARGET,
    TRANSFER_CONFIRM,
    ADMIN_TRACKING_SEARCH,
    ADMIN_SET_TEST_VOLUME,
    WAITING_DURATION,
    PROXY_WAITING_RECEIPT,
    ADMIN_PROXY_CHARGE,
    ADMIN_PROXY_SET_PRICE,
    ADMIN_REJECT_REASON,
    TRACK_ORDER_CODE,
    ADMIN_FAQ,
    ADMIN_GIFT_CODE,
    ADMIN_GIFT_VOLUME,
    ADMIN_GIFT_DAYS,
    ADMIN_GIFT_SERVER,
    ADMIN_GIFT_MAX_USES,
    WAITING_GIFT_CODE,
    SPECIAL_DISCOUNTS,  # <-- جدید
    WAITING_DISCOUNT,   # برای دکمه تخفیف‌های ویژه
) = range(68)

# ==================== دیتابیس ====================
async def init_db():
    async with aiosqlite.connect("bot.db") as db:
        # ... (تمام کد قبلی دیتابیس بدون تغییر)
        await db.commit()

        # اضافه کردن ستون‌های جدید برای سه قابلیت جدید
        for col, typ in [
            ("personal_link", "TEXT"),
            ("special_discounts", "TEXT DEFAULT '10% for >200k'"),
        ]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
            except:
                pass

        # تنظیمات تخفیف‌های ویژه
        async with db.execute("SELECT value FROM settings WHERE key = 'special_discounts'") as cur:
            if not await cur.fetchone():
                await db.execute("INSERT INTO settings (key, value) VALUES (?, ?)",
                               ("special_discounts", "10% for purchases above 200000"))

        await db.commit()

# ==================== منوی اصلی (با سه قابلیت جدید) ====================
def main_keyboard(is_admin: bool = False):
    buttons = [
        [InlineKeyboardButton("🛒 خرید سرویس", callback_data="buy_service")],
        [InlineKeyboardButton("🌐 پروکسی", callback_data="proxy_menu")],
        [
            InlineKeyboardButton("📦 سرویس‌های من", callback_data="my_services"),
            InlineKeyboardButton("🔄 تمدید سریع", callback_data="quick_renew"),
        ],
        [
            InlineKeyboardButton("📊 وضعیت سرویس‌ها", callback_data="service_status"),
            InlineKeyboardButton("📋 تاریخچه سفارشات", callback_data="order_history"),
        ],
        [
            InlineKeyboardButton("🧪 اکانت تست", callback_data="test_account"),
            InlineKeyboardButton("🔍 پیگیری سفارش", callback_data="track_order"),
        ],
        [
            InlineKeyboardButton("💰 کیف پول", callback_data="wallet"),
            InlineKeyboardButton("🎁 کد هدیه", callback_data="redeem_gift"),
        ],
        [
            InlineKeyboardButton("💬 پشتیبانی", callback_data="support"),
            InlineKeyboardButton("❓ راهنما / سوالات متداول", callback_data="faq"),
        ],
        [
            InlineKeyboardButton("👥 دعوت از دوستان", callback_data="referral"),
            InlineKeyboardButton("📜 قوانین", callback_data="rules"),
        ],
        # ==================== سه قابلیت جدید ====================
        [
            InlineKeyboardButton("📲 تخفیف‌های ویژه", callback_data="special_discounts"),
            InlineKeyboardButton("📲 لینک خرید شخصی", callback_data="personal_link"),
        ],
        [
            InlineKeyboardButton("🔄 اشتراک‌گذاری کانفیگ", callback_data="share_config"),
            InlineKeyboardButton("⚙️ تنظیمات پیشرفته", callback_data="advanced_settings"),
        ],
        [
            InlineKeyboardButton("📱 اپلیکیشن اتصال", callback_data="connect_app"),
            InlineKeyboardButton("🛠 پنل مدیریت", callback_data="admin_panel"),
        ],
    ]

    if is_admin:
        buttons.append([InlineKeyboardButton("🛠 پنل مدیریت", callback_data="admin_panel")])

    return InlineKeyboardMarkup(buttons)

# ==================== سه قابلیت جدید ====================

# 1. تخفیف‌های ویژه (دکمه)
async def special_discounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = (
        "🎟 <b>تخفیف‌های ویژه فعال</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "• <b>۱۰٪</b> تخفیف برای خرید بالای ۲۰۰٬۰۰۰ تومان\n"
        "• <b>۱۵٪</b> تخفیف برای خرید بالای ۵۰۰٬۰۰۰ تومان\n"
        "• <b>۲۰٪</b> تخفیف برای خرید بالای ۱٬۰۰۰٬۰۰۰ تومان\n"
        "• <b>کد هدیه ۵٪</b> برای هر کاربر جدید (حداکثر ۳ بار)\n"
        "• <b>هدیه رایگان ۱ گیگ</b> بعد از ۵ خرید\n\n"
        "کد تخفیف خود را وارد کنید:"
    )
    
    await query.edit_message_text(text, parse_mode=ParseMode.HTML)
    return WAITING_DISCOUNT

# 2. تخفیف ۱۰٪ ویژه (در فرآیند خرید)
async def receive_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        code = update.message.text.strip().upper()
        # ... (کد قبلی تخفیف)
        
        # اضافه کردن تخفیف ویژه ۱۰٪
        base = context.user_data["price"]
        days = context.user_data.get("selected_days") or context.user_data.get("custom_days") or 0
        total_before = base + (days * await get_int_setting("price_per_day", 1000))
        
        if total_before >= 200000:
            final = int(total_before * 0.9)
            context.user_data["final_price"] = final
            await update.message.reply_text("✅ <b>تخفیف ۱۰٪ ویژه</b> اعمال شد (خرید بالای ۲۰۰ هزار تومان).")
        else:
            await update.message.reply_text("✅ کد تخفیف اعمال شد.")
        
        return await show_invoice(update, context)
    except:
        await update.message.reply_text("❌ کد تخفیف معتبر نیست.")
        return WAITING_DISCOUNT

# 3. اشتراک‌گذاری کانفیگ (دکمه «شار»)
async def share_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # گرفتن آخرین سرویس کاربر
    async with aiosqlite.connect("bot.db") as db:
        async with db.execute(
            """SELECT o.id, o.config_name, o.config_data, u.username 
               FROM orders o JOIN users u ON o.user_id = u.user_id 
               WHERE o.user_id = ? AND o.status = 'paid' 
               ORDER BY o.created_at DESC LIMIT 1""",
            (query.from_user.id,)
        ) as cur:
            row = await cur.fetchone()
    
    if not row:
        await query.edit_message_text("❌ هیچ سرویس فعالی برای اشتراک‌گذاری پیدا نشد.")
        return
    
    order_id, config_name, config_data, username = row
    
    try:
        config = json.loads(config_data)
        sub_url = config.get("subscription_url") or config.get("config_link")
    except:
        sub_url = "لینک فعال نیست"
    
    text = (
        f"🔗 <b>لینک کانفیگ شما</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📦 {config_name}\n"
        f"🔗 <code>{sub_url}</code>\n\n"
        f"👤 اشتراک‌گذاری با دوست:\n"
        f"📲 لینک شخصی: https://t.me/{BOT_USERNAME}?start=ref_{query.from_user.id}\n\n"
        f"✅ دوستت با این لینک می‌تونه سرویس رو خرید کنه."
    )
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 کپی لینک", callback_data=f"copy_link_{sub_url}")],
        [InlineKeyboardButton("📤 ارسال به دوست", callback_data=f"send_to_friend_{order_id}")],
        [back_button()]
    ])
    
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

# ==================== هندلرها (جدید) ====================
application = Application.builder().token(BOT_TOKEN).build()

# اضافه کردن هندلرها برای سه قابلیت جدید
application.add_handler(CallbackQueryHandler(special_discounts, pattern="^special_discounts$"))
application.add_handler(CallbackQueryHandler(share_config, pattern="^share_config$"))

# بقیه کد اصلی (بدون تغییر)

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    # ... (بقیه کد اصلی بدون تغییر)
    application.add_handler(CallbackQueryHandler(special_discounts, pattern="^special_discounts$"))
    application.add_handler(CallbackQueryHandler(share_config, pattern="^share_config$"))
    # ... بقیه کد اصلی
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()