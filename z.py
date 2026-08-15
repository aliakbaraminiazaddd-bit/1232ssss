import logging
import sqlite3
import random
import string
import asyncio
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

# ================== تنظیمات ==================
BOT_TOKEN = "8861292927:AAHnVqTaPiLdPOAuRoEIe3gzJHwkw6ZJYqM"          # توکن ربات
ADMIN_ID = 8837001390                  # آیدی عددی ادمین

CHANNEL_USERNAMES = [
    "@Sovexsc",
    "@N4TConfig",
    "@nexroofficial"
]

SUPPORT_USERNAME = "@RoTex8"

# ---------- تنظیمات پنل مرزبان (اکانت تست) ----------
MARZBAN_URL = "https://marzban-panel-production-eb8b.up.railway.app"   # آدرس پنل بدون اسلش آخر
MARZBAN_USERNAME = "sinaking"                  # یوزرنیم ادمین پنل
MARZBAN_PASSWORD = "sinasadhghi"               # پسورد ادمین پنل

# پروتکل‌ها و اینباندها — باید با پنل خودت یکی باشد
MARZBAN_PROXIES = {
    "vless": {}
}
MARZBAN_INBOUNDS = {}

# مدت اعتبار اکانت تست به روز (۰ = بدون انقضا)
MARZBAN_EXPIRE_DAYS = 1  # تست = ۱ روز (در کد ساخت هم override می‌شود)

# ---------- تنظیمات پنل پاسارگاد / PasarGuard (کانفیگ اصلی) ----------
# آدرس پنل بدون اسلش آخر را وارد کنید
PASARGAD_URL = "https://pasarguard-production-6082.up.railway.app"   # <-- آدرس پنل پاسارگاد
PASARGAD_USERNAME = "admin"                        # <-- یوزرنیم ادمین
PASARGAD_PASSWORD = "PaSarGuard2026!sina"                     # <-- پسورد ادمین
# شناسه گروه(ها) — از پنل پاسارگاد > Groups بردارید (مثلاً [1] یا [1, 2])
PASARGAD_GROUP_IDS = [1]
# مدت اعتبار کانفیگ اصلی به روز (۰ = بدون انقضا)
PASARGAD_EXPIRE_DAYS = 30

# جوایز گردونه شانس (فقط اگر تاس ۶ بیاید یکی از این‌ها به‌صورت شانسی انتخاب می‌شود)
WHEEL_REWARDS = [1, 2, 3, 5, 10]
# رایگان — هر ۲۴ ساعت یک‌بار

# وضعیت‌های مکالمه
(
    WAITING_SEARCH_ID,
    WAITING_DELETE_ID,
    WAITING_UNBLOCK_ID,
    WAITING_GIFT_CODE,
    WAITING_BROADCAST,
    WAITING_SPECIFIC_ID,
    WAITING_SPECIFIC_MSG,
    WAITING_CREATE_GIFT_POINTS,
    WAITING_CREATE_GIFT_USES,
    WAITING_CREATE_GIFT_EXPIRES,
    WAITING_TRANSFER_ID,
    WAITING_TRANSFER_AMOUNT,
    WAITING_ADMIN_GIFT_ALL_POINTS,
    WAITING_ADMIN_GIFT_ALL_DESC,
    WAITING_ADMIN_GIFT_ONE_ID,
    WAITING_ADMIN_GIFT_ONE_POINTS,
    WAITING_ADMIN_GIFT_ONE_DESC,
    WAITING_DEDUCT_ONE_ID,
    WAITING_DEDUCT_ONE_AMOUNT,
    WAITING_DEDUCT_ALL_AMOUNT,
    WAITING_WARNING_ID,
    WAITING_WARNING_DESC,
    WAITING_RESET_WHEEL_ID,
    WAITING_DISABLE_SERVICE_DESC,
    WAITING_SERVICE_USERNAME,
    WAITING_RESET_TEST_ID,
    WAITING_CONFIG_DURATION,
) = range(27)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== دیتابیس ==================
def init_db():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        points INTEGER DEFAULT 0,
        referrer_id INTEGER,
        configs_received INTEGER DEFAULT 0,
        joined_date TEXT,
        is_blocked INTEGER DEFAULT 0,
        last_daily TEXT,
        warnings INTEGER DEFAULT 0,
        last_wheel TEXT
    )''')

    for col, typedef in [
        ("last_daily", "TEXT"),
        ("warnings", "INTEGER DEFAULT 0"),
        ("last_wheel", "TEXT"),
        ("last_test", "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {typedef}")
        except:
            pass

    c.execute('''CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER UNIQUE,
        date TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS config_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        volume INTEGER,
        tracking_code TEXT,
        date TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS gift_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        points INTEGER,
        is_used INTEGER DEFAULT 0,
        used_by INTEGER,
        created_date TEXT,
        max_uses INTEGER DEFAULT 1,
        used_count INTEGER DEFAULT 0,
        expires_date TEXT
    )''')
    # ستون‌های اضافی برای جدول قدیمی
    for col, typedef in [
        ("max_uses", "INTEGER DEFAULT 1"),
        ("used_count", "INTEGER DEFAULT 0"),
        ("expires_date", "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE gift_codes ADD COLUMN {col} {typedef}")
        except:
            pass

    # تاریخچه امتیاز
    c.execute('''CREATE TABLE IF NOT EXISTS points_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        reason TEXT,
        date TEXT
    )''')

    # استفاده‌کنندگان کد هدیه گروهی
    c.execute('''CREATE TABLE IF NOT EXISTS gift_code_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT,
        user_id INTEGER,
        date TEXT,
        UNIQUE(code, user_id)
    )''')

    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row


def add_user(user_id, username, first_name, referrer_id=None):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if c.fetchone():
        conn.close()
        return False
    c.execute(
        "INSERT INTO users (user_id, username, first_name, points, referrer_id, joined_date, warnings) VALUES (?, ?, ?, 0, ?, ?, 0)",
        (user_id, username, first_name, referrer_id, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    if referrer_id:
        # امتیاز پایه + بونوس سطح
        bonus = get_level_bonus(referrer_id)
        total_add = 1 + bonus
        c.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (total_add, referrer_id))
        c.execute(
            "INSERT INTO referrals (referrer_id, referred_id, date) VALUES (?, ?, ?)",
            (referrer_id, user_id, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        log_points(referrer_id, total_add, f"دعوت کاربر جدید (+{bonus} بونوس سطح)" if bonus else "دعوت کاربر جدید")
    conn.commit()
    conn.close()
    return True


def log_points(user_id, amount, reason):
    """ثبت تاریخچه امتیاز"""
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO points_log (user_id, amount, reason, date) VALUES (?, ?, ?, ?)",
        (user_id, amount, reason, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    conn.close()


def get_points_history(user_id, limit=15):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute(
        "SELECT amount, reason, date FROM points_log WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows


def update_points(user_id, amount, reason="تغییر امتیاز"):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    if amount != 0:
        log_points(user_id, amount, reason)


def set_points(user_id, amount, reason="تنظیم امتیاز"):
    current = get_points(user_id)
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("UPDATE users SET points = ? WHERE user_id = ?", (max(0, amount), user_id))
    conn.commit()
    conn.close()
    diff = max(0, amount) - current
    if diff != 0:
        log_points(user_id, diff, reason)


def get_points(user_id):
    user = get_user(user_id)
    return user[3] if user else 0


def add_config_history(user_id, volume, tracking_code, deduct_points=True, reason=None):
    """volume به گیگ (برای تست می‌تواند ۰ باشد). اگر deduct_points=False امتیاز کم نمی‌شود."""
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO config_history (user_id, volume, tracking_code, date) VALUES (?, ?, ?, ?)",
        (user_id, volume, tracking_code, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    if deduct_points and volume:
        c.execute(
            "UPDATE users SET configs_received = configs_received + 1, points = points - ? WHERE user_id = ?",
            (volume, user_id)
        )
        conn.commit()
        conn.close()
        log_points(user_id, -volume, reason or f"دریافت کانفیگ {volume} گیگ")
    else:
        c.execute(
            "UPDATE users SET configs_received = configs_received + 1 WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        conn.close()
        if reason:
            log_points(user_id, 0, reason)


def get_user_stats(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT points, configs_received, joined_date, warnings FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    refs = c.fetchone()[0]
    c.execute("SELECT volume, tracking_code, date FROM config_history WHERE user_id = ? ORDER BY id DESC", (user_id,))
    history = c.fetchall()
    conn.close()
    return user, refs, history


def get_referral_count(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count


def get_user_level(user_id):
    """مدال کاربر بر اساس تعداد زیرمجموعه"""
    refs = get_referral_count(user_id)
    if refs >= 100:
        return "👑 Legend", refs, 5
    if refs >= 60:
        return "💎 Diamond", refs, 3
    if refs >= 30:
        return "🥇 Gold", refs, 2
    if refs >= 10:
        return "🥈 Silver", refs, 1
    return "🥉 Bronze", refs, 0


def get_level_bonus(user_id):
    _, _, bonus = get_user_level(user_id)
    return bonus


def block_user(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def unblock_user(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("UPDATE users SET is_blocked = 0, warnings = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def is_blocked(user_id):
    user = get_user(user_id)
    return user and user[7] == 1


def get_warnings(user_id):
    user = get_user(user_id)
    if user and len(user) > 9:
        return user[9] or 0
    return 0


def add_warning(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("UPDATE users SET warnings = COALESCE(warnings, 0) + 1 WHERE user_id = ?", (user_id,))
    c.execute("SELECT warnings FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.commit()
    conn.close()
    return row[0] if row else 0


def generate_tracking_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


# ================== API مرزبان ==================
_marzban_token = None
_marzban_token_time = None


def _marzban_request(method, path, data=None, token=None, form=False):
    """درخواست HTTP به API مرزبان"""
    url = MARZBAN_URL.rstrip("/") + path
    headers = {"Accept": "application/json"}
    body = None

    if form:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        body = urllib.parse.urlencode(data or {}).encode("utf-8")
    elif data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")

    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(err_body)
            detail = err_json.get("detail", err_body)
        except Exception:
            detail = err_body
        raise Exception(f"Marzban HTTP {e.code}: {detail}")
    except Exception as e:
        raise Exception(f"Marzban error: {e}")


def marzban_get_token():
    """دریافت یا تمدید توکن ادمین"""
    global _marzban_token, _marzban_token_time
    # توکن را حدود ۵۰ دقیقه نگه می‌داریم
    if _marzban_token and _marzban_token_time:
        if datetime.now() - _marzban_token_time < timedelta(minutes=50):
            return _marzban_token

    result = _marzban_request(
        "POST",
        "/api/admin/token",
        data={"username": MARZBAN_USERNAME, "password": MARZBAN_PASSWORD, "grant_type": "password"},
        form=True,
    )
    _marzban_token = result.get("access_token")
    _marzban_token_time = datetime.now()
    if not _marzban_token:
        raise Exception("توکن مرزبان دریافت نشد. یوزر/پسورد را چک کنید.")
    return _marzban_token


def marzban_create_user(
    telegram_user_id: int,
    volume_gb=None,
    volume_mb=None,
    expire_days=None,
    note_extra="",
    custom_username=None,
):
    """
    ساخت کاربر در مرزبان.
    volume_gb: حجم به گیگ (عدد صحیح مثل 1, 2, 5)
    volume_mb: حجم به مگ (عدد صحیح مثل 100) — برای دقت دقیق
    custom_username: نام دلخواه کاربر (a-z 0-9 _) یا None برای خودکار
    """
    token = marzban_get_token()

    if custom_username:
        username = custom_username.lower().strip()[:20]
    else:
        username = f"u{telegram_user_id}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=5))}"
        username = username[:20]

    if volume_mb is not None:
        data_limit = int(volume_mb) * 1024 * 1024  # دقیق به مگ
        vol_label = f"{int(volume_mb)}MB"
    else:
        volume_gb = float(volume_gb or 1)
        data_limit = int(volume_gb) * 1024 * 1024 * 1024  # دقیق به گیگ صحیح
        vol_label = f"{int(volume_gb)}GB"

    if data_limit < 1:
        data_limit = 100 * 1024 * 1024
        vol_label = "100MB"

    days = MARZBAN_EXPIRE_DAYS if expire_days is None else expire_days
    expire = 0
    if days and days > 0:
        expire = int((datetime.now() + timedelta(days=days)).timestamp())

    note = f"tg:{telegram_user_id} | {vol_label} | bot"
    if note_extra:
        note += f" | {note_extra}"

    payload = {
        "username": username,
        "proxies": MARZBAN_PROXIES,
        "inbounds": MARZBAN_INBOUNDS if MARZBAN_INBOUNDS else {},
        "expire": expire if expire else 0,
        "data_limit": data_limit,
        "data_limit_reset_strategy": "no_reset",
        "status": "active",
        "note": note,
    }

    result = _marzban_request("POST", "/api/user", data=payload, token=token)

    # لینک ساب دقیقاً مثل خروجی اصلی پنل مرزبان
    sub_url = (result.get("subscription_url") or "").strip()
    if sub_url and not sub_url.startswith("http://") and not sub_url.startswith("https://"):
        if not sub_url.startswith("/"):
            sub_url = "/" + sub_url
        sub_url = MARZBAN_URL.rstrip("/") + sub_url

    links = result.get("links") or []
    return {
        "username": result.get("username", username),
        "subscription_url": sub_url,
        "links": links,
        "data_limit": data_limit,
        "expire": expire,
        "vol_label": vol_label,
        "panel": "marzban",
    }


# ================== API پاسارگاد / PasarGuard ==================
_pasargad_token = None
_pasargad_token_time = None


def _pasargad_request(method, path, data=None, token=None, form=False):
    """درخواست HTTP به API پاسارگاد (PasarGuard)"""
    url = PASARGAD_URL.rstrip("/") + path
    headers = {"Accept": "application/json"}
    body = None

    if form:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        body = urllib.parse.urlencode(data or {}).encode("utf-8")
    elif data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")

    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(err_body)
            detail = err_json.get("detail", err_body)
        except Exception:
            detail = err_body
        raise Exception(f"Pasargad HTTP {e.code}: {detail}")
    except Exception as e:
        raise Exception(f"Pasargad error: {e}")


def pasargad_get_token():
    """دریافت یا تمدید توکن ادمین پاسارگاد"""
    global _pasargad_token, _pasargad_token_time
    if _pasargad_token and _pasargad_token_time:
        if datetime.now() - _pasargad_token_time < timedelta(minutes=50):
            return _pasargad_token

    result = _pasargad_request(
        "POST",
        "/api/admin/token",
        data={"username": PASARGAD_USERNAME, "password": PASARGAD_PASSWORD, "grant_type": "password"},
        form=True,
    )
    _pasargad_token = result.get("access_token")
    _pasargad_token_time = datetime.now()
    if not _pasargad_token:
        raise Exception("توکن پاسارگاد دریافت نشد. یوزر/پسورد و آدرس پنل را چک کنید.")
    return _pasargad_token


def pasargad_create_user(
    telegram_user_id: int,
    volume_gb=None,
    volume_mb=None,
    expire_days=None,
    note_extra="",
    custom_username=None,
):
    """
    ساخت کاربر در پنل پاسارگاد (PasarGuard) — برای کانفیگ‌های اصلی
    از group_ids استفاده می‌کند (برخلاف مرزبان که inbounds دارد)
    """
    token = pasargad_get_token()

    if custom_username:
        username = custom_username.lower().strip()[:20]
    else:
        username = f"u{telegram_user_id}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=5))}"
        username = username[:20]

    if volume_mb is not None:
        data_limit = int(volume_mb) * 1024 * 1024
        vol_label = f"{int(volume_mb)}MB"
    else:
        volume_gb = float(volume_gb or 1)
        data_limit = int(volume_gb) * 1024 * 1024 * 1024
        vol_label = f"{int(volume_gb)}GB"

    if data_limit < 1:
        data_limit = 100 * 1024 * 1024
        vol_label = "100MB"

    days = PASARGAD_EXPIRE_DAYS if expire_days is None else expire_days
    expire = 0
    if days and days > 0:
        expire = int((datetime.now() + timedelta(days=days)).timestamp())

    note = f"tg:{telegram_user_id} | {vol_label} | bot"
    if note_extra:
        note += f" | {note_extra}"

    # PasarGuard: group_ids به‌جای inbounds
    payload = {
        "username": username,
        "status": "active",
        "expire": expire if expire else 0,
        "data_limit": data_limit,
        "data_limit_reset_strategy": "no_reset",
        "group_ids": PASARGAD_GROUP_IDS if PASARGAD_GROUP_IDS else [],
        "note": note,
    }

    result = _pasargad_request("POST", "/api/user", data=payload, token=token)

    sub_url = (result.get("subscription_url") or "").strip()
    if sub_url and not sub_url.startswith("http://") and not sub_url.startswith("https://"):
        if not sub_url.startswith("/"):
            sub_url = "/" + sub_url
        sub_url = PASARGAD_URL.rstrip("/") + sub_url

    links = result.get("links") or []
    return {
        "username": result.get("username", username),
        "subscription_url": sub_url,
        "links": links,
        "data_limit": data_limit,
        "expire": expire,
        "vol_label": vol_label,
        "panel": "pasargad",
    }


def is_valid_panel_username(name: str) -> tuple:
    """بررسی نام کاربری: حروف لاتین کوچک/عدد/_ ، طول ۳ تا ۲۰"""
    name = (name or "").strip().lower()
    if len(name) < 3:
        return False, "نام کاربری باید حداقل ۳ کاراکتر باشد."
    if len(name) > 20:
        return False, "نام کاربری حداکثر ۲۰ کاراکتر می‌تواند باشد."
    allowed = set(string.ascii_lowercase + string.digits + "_")
    if not all(c in allowed for c in name):
        return False, "فقط حروف لاتین (a-z)، عدد و _ مجاز است."
    return True, name


def qr_code_url(data: str, size: int = 400) -> str:
    """لینک تصویر QR از سرویس عمومی"""
    return (
        "https://api.qrserver.com/v1/create-qr-code/"
        f"?size={size}x{size}&margin=10&data={urllib.parse.quote(data)}"
    )


def marzban_get_users(offset=0, limit=50, status="active"):
    """لیست کاربران پنل مرزبان"""
    token = marzban_get_token()
    path = f"/api/users?offset={offset}&limit={limit}"
    if status:
        path += f"&status={status}"
    return _marzban_request("GET", path, token=token)


def marzban_disable_user(username: str):
    """قطع (غیرفعال کردن) کاربر در مرزبان"""
    token = marzban_get_token()
    payload = {"status": "disabled"}
    return _marzban_request("PUT", f"/api/user/{urllib.parse.quote(username)}", data=payload, token=token)


def parse_tg_from_note(note: str):
    """استخراج آیدی تلگرام از فیلد note (فرمت: tg:123 | 5GB | bot)"""
    if not note:
        return None
    try:
        for part in note.split("|"):
            part = part.strip()
            if part.startswith("tg:"):
                return int(part.replace("tg:", "").strip())
    except Exception:
        pass
    return None


def format_bytes_gb(data_limit):
    """تبدیل بایت به گیگ برای نمایش"""
    if not data_limit:
        return "∞"
    try:
        gb = data_limit / (1024 * 1024 * 1024)
        if gb >= 1:
            return f"{gb:.0f}" if gb == int(gb) else f"{gb:.1f}"
        return f"{gb:.2f}"
    except Exception:
        return "?"


def create_gift_code(points, max_uses=1, expires_hours=None):
    """expires_hours: None یا 0 = بدون انقضا | عدد = ساعت تا انقضا"""
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    expires_date = None
    if expires_hours and expires_hours > 0:
        expires_date = (datetime.now() + timedelta(hours=expires_hours)).strftime("%Y-%m-%d %H:%M")
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO gift_codes (code, points, created_date, max_uses, used_count, expires_date) VALUES (?, ?, ?, ?, 0, ?)",
        (code, points, datetime.now().strftime("%Y-%m-%d %H:%M"), max_uses, expires_date)
    )
    conn.commit()
    conn.close()
    return code, expires_date


def use_gift_code(code, user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    code = code.upper()
    c.execute("SELECT points, is_used, max_uses, used_count, expires_date FROM gift_codes WHERE code = ?", (code,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None, "کد هدیه نامعتبر است."

    points, is_used, max_uses, used_count, expires_date = row
    max_uses = max_uses or 1
    used_count = used_count or 0

    # چک تاریخ انقضا
    if expires_date:
        try:
            exp = datetime.strptime(expires_date, "%Y-%m-%d %H:%M")
            if datetime.now() > exp:
                conn.close()
                return None, "مهلت استفاده از این کد به پایان رسیده است."
        except:
            pass

    # کد یک‌بار مصرف
    if max_uses <= 1:
        if is_used:
            conn.close()
            return None, "این کد هدیه قبلاً استفاده شده است."
        c.execute("UPDATE gift_codes SET is_used = 1, used_by = ?, used_count = 1 WHERE code = ?", (user_id, code))
    else:
        # کد گروهی
        if used_count >= max_uses:
            conn.close()
            return None, "ظرفیت استفاده از این کد تمام شده است."
        c.execute("SELECT id FROM gift_code_users WHERE code = ? AND user_id = ?", (code, user_id))
        if c.fetchone():
            conn.close()
            return None, "شما قبلاً از این کد استفاده کرده‌اید."
        c.execute("UPDATE gift_codes SET used_count = used_count + 1 WHERE code = ?", (code,))
        c.execute(
            "INSERT INTO gift_code_users (code, user_id, date) VALUES (?, ?, ?)",
            (code, user_id, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        if used_count + 1 >= max_uses:
            c.execute("UPDATE gift_codes SET is_used = 1 WHERE code = ?", (code,))

    c.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (points, user_id))
    conn.commit()
    conn.close()
    log_points(user_id, points, f"کد هدیه ({code})")
    return points, None


def get_all_user_ids():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE is_blocked = 0")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_leaderboard(limit=10):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("""
        SELECT u.user_id, u.first_name, u.username, COUNT(r.referred_id) as refs
        FROM users u
        LEFT JOIN referrals r ON u.user_id = r.referrer_id
        WHERE u.is_blocked = 0
        GROUP BY u.user_id
        ORDER BY refs DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


def claim_daily(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT last_daily FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    now = datetime.now()
    if row and row[0]:
        try:
            last = datetime.strptime(row[0], "%Y-%m-%d %H:%M")
            if now - last < timedelta(hours=24):
                remaining = timedelta(hours=24) - (now - last)
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                conn.close()
                return False, f"⏳ هنوز {hours} ساعت و {minutes} دقیقه تا جایزه بعدی باقی مانده."
        except:
            pass
    c.execute("UPDATE users SET points = points + 1, last_daily = ? WHERE user_id = ?",
              (now.strftime("%Y-%m-%d %H:%M"), user_id))
    conn.commit()
    conn.close()
    log_points(user_id, 1, "جایزه روزانه")
    return True, None


def can_claim_test(user_id):
    """اکانت تست هر ۲۴ ساعت یک‌بار"""
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    try:
        c.execute("SELECT last_test FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
    except Exception:
        conn.close()
        return True, None
    conn.close()
    now = datetime.now()
    if row and row[0]:
        try:
            last = datetime.strptime(row[0], "%Y-%m-%d %H:%M")
            if now - last < timedelta(hours=24):
                remaining = timedelta(hours=24) - (now - last)
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                return False, f"⏳ هنوز {hours} ساعت و {minutes} دقیقه تا اکانت تست بعدی باقی مانده."
        except Exception:
            pass
    return True, None


def set_last_test(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute(
        "UPDATE users SET last_test = ? WHERE user_id = ?",
        (datetime.now().strftime("%Y-%m-%d %H:%M"), user_id)
    )
    conn.commit()
    conn.close()


def reset_test(user_id):
    """صفر کردن زمان اکانت تست تا کاربر دوباره بتواند بگیرد"""
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("UPDATE users SET last_test = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_bot_stats():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1")
    blocked = c.fetchone()[0]
    c.execute("SELECT SUM(points) FROM users")
    total_points = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM referrals")
    total_refs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM config_history")
    total_configs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM gift_codes")
    total_gifts = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM gift_codes WHERE is_used = 1")
    used_gifts = c.fetchone()[0]
    conn.close()
    return {
        "total_users": total_users,
        "blocked": blocked,
        "total_points": total_points,
        "total_refs": total_refs,
        "total_configs": total_configs,
        "total_gifts": total_gifts,
        "used_gifts": used_gifts,
    }


def transfer_points(from_id, to_id, amount):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE user_id = ?", (from_id,))
    row = c.fetchone()
    if not row or row[0] < amount:
        conn.close()
        return False, "امتیاز کافی ندارید."
    c.execute("SELECT user_id, first_name FROM users WHERE user_id = ?", (to_id,))
    target = c.fetchone()
    if not target:
        conn.close()
        return False, "کاربری با این آیدی یافت نشد."
    c.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (amount, from_id))
    c.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, to_id))
    conn.commit()
    conn.close()
    log_points(from_id, -amount, f"انتقال به {to_id}")
    log_points(to_id, amount, f"دریافت از {from_id}")
    return True, target[1]


def deduct_points(user_id, amount, reason="کسر توسط مدیریت"):
    current = get_points(user_id)
    new_points = max(0, current - amount)
    set_points(user_id, new_points, reason)
    return current - new_points


def get_users_page(page=0, per_page=10):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    offset = page * per_page
    c.execute("""
        SELECT user_id, username, first_name, points, is_blocked, joined_date, warnings
        FROM users
        ORDER BY joined_date DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    conn.close()
    return rows, total


# ---------- گردونه ----------
def can_spin_wheel(user_id):
    """بررسی اینکه آیا کاربر می‌تواند گردونه بزند (هر ۲۴ ساعت یک‌بار)"""
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    try:
        c.execute("SELECT last_wheel FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
    except:
        conn.close()
        return True, None
    conn.close()
    now = datetime.now()
    if row and row[0]:
        try:
            last = datetime.strptime(row[0], "%Y-%m-%d %H:%M")
            if now - last < timedelta(hours=24):
                remaining = timedelta(hours=24) - (now - last)
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                return False, f"⏳ هنوز {hours} ساعت و {minutes} دقیقه تا گردونه بعدی باقی مانده."
        except:
            pass
    return True, None


def set_last_wheel(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute(
        "UPDATE users SET last_wheel = ? WHERE user_id = ?",
        (datetime.now().strftime("%Y-%m-%d %H:%M"), user_id)
    )
    conn.commit()
    conn.close()


def reset_wheel(user_id):
    """صفر کردن زمان گردونه تا کاربر دوباره بتواند بزند"""
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("UPDATE users SET last_wheel = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def reward_for_dice(dice_value: int) -> int:
    """اگر تاس ۶ باشد جایزه شانسی برمی‌گرداند، وگرنه ۰"""
    if dice_value == 6:
        return random.choice(WHEEL_REWARDS)
    return 0


# ================== چک جوین اجباری ==================
async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    for channel in CHANNEL_USERNAMES:
        try:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception:
            return False
    return True


async def get_missing_channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> list:
    user_id = update.effective_user.id
    missing = []
    for channel in CHANNEL_USERNAMES:
        try:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                missing.append(channel)
        except Exception:
            missing.append(channel)
    return missing


async def require_membership(update: Update, context: ContextTypes.DEFAULT_TYPE, already_answered: bool = False) -> bool:
    if await check_membership(update, context):
        return True

    missing = await get_missing_channels(update, context)
    channels_to_show = missing if missing else CHANNEL_USERNAMES

    keyboard = []
    for ch in channels_to_show:
        keyboard.append([
            InlineKeyboardButton(
                f"📢 عضویت در {ch}",
                url=f"https://t.me/{ch.replace('@', '')}"
            )
        ])
    keyboard.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")])

    channels_text = "\n".join([f"👉 {ch}" for ch in channels_to_show])
    text = (
        "⛔️ برای استفاده از ربات باید ابتدا در کانال‌های زیر عضو شوید:\n\n"
        f"{channels_text}\n\n"
        "بعد از عضویت در همه کانال‌ها روی دکمه «عضو شدم» کلیک کنید."
    )

    if update.callback_query:
        if not already_answered:
            await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    return False


# ================== چک عضویت دوره‌ای ==================
async def periodic_membership_check(context: ContextTypes.DEFAULT_TYPE):
    """هر چند ساعت عضویت همه کاربران را چک می‌کند"""
    bot = context.bot
    user_ids = get_all_user_ids()
    left_users = []  # [(uid, name, missing_channels), ...]

    for uid in user_ids:
        if uid == ADMIN_ID:
            continue
        missing = []
        for channel in CHANNEL_USERNAMES:
            try:
                member = await bot.get_chat_member(chat_id=channel, user_id=uid)
                if member.status not in ["member", "administrator", "creator"]:
                    missing.append(channel)
            except Exception:
                missing.append(channel)

        if missing:
            user = get_user(uid)
            name = (user[2] if user else None) or "کاربر"
            left_users.append((uid, name, missing))
            try:
                channels_text = "\n".join([f"👉 {ch}" for ch in missing])
                keyboard = []
                for ch in missing:
                    keyboard.append([
                        InlineKeyboardButton(
                            f"📢 عضویت در {ch}",
                            url=f"https://t.me/{ch.replace('@', '')}"
                        )
                    ])
                keyboard.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")])
                await bot.send_message(
                    chat_id=uid,
                    text=(
                        "⚠️ شما از یک یا چند کانال اجباری خارج شده‌اید!\n\n"
                        f"{channels_text}\n\n"
                        "تا زمان عضویت مجدد، امکان استفاده از ربات را ندارید."
                    ),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception:
                pass

    if left_users:
        text = f"🔔 *چک عضویت دوره‌ای*\n\n"
        text += f"تعداد: *{len(left_users)}* کاربر از کانال خارج شده‌اند:\n\n"
        for uid, name, missing in left_users:
            chs = ", ".join(missing)
            text += f"• {name}\n  🆔 `{uid}`\n  📢 {chs}\n\n"

        # محدودیت طول پیام تلگرام
        if len(text) > 4000:
            text = text[:3900] + "\n\n... (لیست طولانی‌تر از حد مجاز)"

        try:
            await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown")
        except Exception:
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🔔 چک عضویت:\n{len(left_users)} کاربر خارج شده‌اند.\nآیدی‌ها:\n" +
                         "\n".join([str(u[0]) for u in left_users[:50]])
                )
            except Exception:
                pass


# ================== کیبوردها ==================
def main_keyboard(user_id):
    keyboard = [
        [KeyboardButton("🎁 دریافت کانفینگ رایگان")],
        [KeyboardButton("🧪 اکانت تست")],
        [
            KeyboardButton("👥 زیرمجموعه گیری"),
            KeyboardButton("👤 حساب کاربری")
        ],
        [
            KeyboardButton("📅 جایزه روزانه"),
            KeyboardButton("🏆 جدول رتبه‌بندی")
        ],
        [
            KeyboardButton("🎡 گردونه شانس"),
            KeyboardButton("📜 تاریخچه امتیاز")
        ],
        [
            KeyboardButton("💸 انتقال امتیاز"),
            KeyboardButton("🎁 کد هدیه")
        ],
        [
            KeyboardButton("ℹ️ راهنما"),
            KeyboardButton("📞 پشتیبانی")
        ]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton("🛠 پنل مدیریت")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def admin_keyboard():
    keyboard = [
        [
            KeyboardButton("🔍 جستجوی آیدی کاربر"),
            KeyboardButton("📊 آمار کاربر")
        ],
        [
            KeyboardButton("🗑 حذف کاربر از ربات"),
            KeyboardButton("✅ رفع مسدودیت کاربر")
        ],
        [KeyboardButton("🎁 ساخت کد هدیه")],
        [
            KeyboardButton("🎁 امتیاز به همه کاربران"),
            KeyboardButton("🎁 امتیاز به کاربر دلخواه")
        ],
        [
            KeyboardButton("➖ کسر امتیاز از کاربر"),
            KeyboardButton("➖ کسر امتیاز از تمامی کاربران")
        ],
        [KeyboardButton("📢 پیام به کاربران ربات")],
        [KeyboardButton("✉️ پیام به کاربر دلخواه")],
        [KeyboardButton("⚠️ اخطار دهی")],
        [
            KeyboardButton("🎡 گردونه شانس مجدد"),
            KeyboardButton("🧪 اکانت تست مجدد")
        ],
        [KeyboardButton("🔌 قطع سرویس")],
        [KeyboardButton("📋 نمایش تمام کاربران")],
        [KeyboardButton("📊 آمار کلی ربات")],
        [KeyboardButton("🔙 بازگشت")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ================== هندلرها ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if is_blocked(user_id):
        await update.message.reply_text("⛔️ شما از ربات مسدود شده‌اید.")
        return

    if context.args:
        ref_arg = context.args[0]
        if ref_arg.startswith("ref_"):
            try:
                referrer_id = int(ref_arg.replace("ref_", ""))
                if referrer_id != user_id:
                    context.user_data["pending_referrer"] = referrer_id
            except:
                pass

    if not await require_membership(update, context):
        return

    referrer_id = context.user_data.pop("pending_referrer", None)
    is_new = add_user(user_id, user.username, user.first_name, referrer_id)

    text = (
        "✨ *به ربات کانفینگ رایگان خوش آمدید* ✨\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🔥 با دعوت دوستان خود امتیاز جمع کنید\n"
        "و کانفینگ رایگان دریافت کنید!\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "📌 هر ۱ امتیاز = ۱ گیگ کانفینگ رایگان"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard(user_id))

    if is_new and referrer_id:
        try:
            level_name, _, bonus = get_user_level(referrer_id)
            bonus_text = f" (+{bonus} بونوس سطح {level_name})" if bonus else ""
            await context.bot.send_message(
                chat_id=referrer_id,
                text=f"🎉 یک نفر از طریق لینک شما وارد ربات شد!\n+{1 + bonus} امتیاز{bonus_text}"
            )
        except:
            pass


async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if await check_membership(update, context):
        await query.answer("✅ عضویت شما تایید شد!")
        try:
            await query.message.delete()
        except:
            pass

        user = query.from_user
        user_id = user.id

        if is_blocked(user_id):
            await context.bot.send_message(chat_id=user_id, text="⛔️ شما از ربات مسدود شده‌اید.")
            return

        referrer_id = context.user_data.pop("pending_referrer", None)
        is_new = add_user(user_id, user.username, user.first_name, referrer_id)

        text = (
            "✨ *به ربات کانفینگ رایگان خوش آمدید* ✨\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔥 با دعوت دوستان خود امتیاز جمع کنید\n"
            "و کانفینگ رایگان دریافت کنید!\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "📌 هر ۱ امتیاز = ۱ گیگ کانفینگ رایگان"
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=main_keyboard(user_id)
        )

        if is_new and referrer_id:
            try:
                level_name, _, bonus = get_user_level(referrer_id)
                bonus_text = f" (+{bonus} بونوس سطح {level_name})" if bonus else ""
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎉 یک نفر از طریق لینک شما وارد ربات شد!\n+{1 + bonus} امتیاز{bonus_text}"
                )
            except:
                pass
    else:
        await query.answer(
            "❌ هنوز در همه کانال‌ها عضو نیستید!\nلطفاً در تمام کانال‌ها عضو شوید و دوباره امتحان کنید.",
            show_alert=True
        )
        await require_membership(update, context, already_answered=True)


async def get_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_blocked(user_id):
        await update.message.reply_text("⛔️ شما از ربات مسدود شده‌اید.")
        return
    if not await require_membership(update, context):
        return

    points = get_points(user_id)
    if points < 2:  # حداقل ۱ گیگ + ۳۰ روز
        await update.message.reply_text(
            "❌ امتیاز کافی برای دریافت کانفینگ ندارید!\n\n"
            "حداقل ۲ امتیاز لازم است (۱ گیگ + ۳۰ روز).\n"
            "برای جمع‌آوری امتیاز از دکمه «👥 زیرمجموعه گیری» استفاده کنید."
        )
        return

    buttons = []
    options = [1, 2, 5, 10]
    row = []
    for vol in options:
        # حداقل vol + ۱ امتیاز (برای ۳۰ روز)
        if points >= vol + 1:
            row.append(InlineKeyboardButton(f"{vol} گیگ", callback_data=f"config_{vol}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
    if row:
        buttons.append(row)

    if not buttons:
        await update.message.reply_text(
            f"❌ امتیاز شما (*{points}*) برای هیچ حجمی کافی نیست.\n"
            f"هر گیگ = ۱ امتیاز + هر ۳۰ روز = ۱ امتیاز",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        f"✅ شما *{points}* امتیاز دارید.\n\n"
        f"📊 *حجم* کانفینگ را انتخاب کنید:\n"
        f"(هر ۱ گیگ = ۱ امتیاز)\n\n"
        f"در مرحله بعد *مدت اعتبار* را انتخاب می‌کنید:\n"
        f"(هر ۳۰ روز = ۱ امتیاز)",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


def _config_cost(volume_gb: int, days: int) -> int:
    """امتیاز لازم = حجم(گیگ) + تعداد بلوک‌های ۳۰ روزه"""
    return int(volume_gb) + max(1, int(days) // 30)


def _duration_keyboard(volume: int, days: int, points: int) -> InlineKeyboardMarkup:
    cost = _config_cost(volume, days)
    rows = [
        [
            InlineKeyboardButton("➖", callback_data="time_minus"),
            InlineKeyboardButton(f"📅 {days} روز", callback_data="time_noop"),
            InlineKeyboardButton("➕", callback_data="time_plus"),
        ],
        [InlineKeyboardButton(
            f"✅ تأیید ({cost} امتیاز)",
            callback_data="time_confirm"
        )],
        [InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="username_cancel")],
    ]
    return InlineKeyboardMarkup(rows)


def _duration_text(volume: int, days: int, points: int) -> str:
    cost = _config_cost(volume, days)
    time_points = max(1, days // 30)
    return (
        f"🛒 سرویس انتخاب‌شده\n\n"
        f"📊 حجم: *{volume} گیگابایت*  ←  {volume} امتیاز\n"
        f"📅 مدت: *{days} روز*  ←  {time_points} امتیاز\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⭐ امتیاز لازم: *{cost}*\n"
        f"💰 موجودی شما: *{points}*\n\n"
        f"با ➕ و ➖ مدت را تغییر دهید\n"
        f"(هر ۳۰ روز = ۱ امتیاز)"
    )


async def confirm_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بعد از انتخاب حجم — انتخاب مدت اعتبار"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if is_blocked(user_id):
        await query.edit_message_text("⛔️ شما از ربات مسدود شده‌اید.")
        return ConversationHandler.END
    if not await require_membership(update, context):
        return ConversationHandler.END

    data = query.data
    if not data.startswith("config_"):
        return ConversationHandler.END
    try:
        volume = int(data.replace("config_", ""))
    except Exception:
        await query.edit_message_text("❌ خطا در انتخاب حجم.")
        return ConversationHandler.END

    points = get_points(user_id)
    if points < volume + 1:
        await query.edit_message_text(
            f"❌ امتیاز کافی ندارید!\n"
            f"برای {volume} گیگ + حداقل ۳۰ روز، *{volume + 1}* امتیاز لازم است.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    days = 30
    context.user_data["svc_type"] = "config"
    context.user_data["svc_volume_gb"] = volume
    context.user_data["svc_volume_mb"] = None
    context.user_data["svc_expire_days"] = days
    context.user_data["svc_note"] = ""
    context.user_data["svc_vol_display"] = f"{volume} گیگابایت"

    await query.edit_message_text(
        _duration_text(volume, days, points),
        parse_mode="Markdown",
        reply_markup=_duration_keyboard(volume, days, points)
    )
    return WAITING_CONFIG_DURATION


async def config_duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دکمه‌های + / − / تأیید مدت"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    volume = context.user_data.get("svc_volume_gb")
    days = context.user_data.get("svc_expire_days", 30)
    if volume is None:
        await query.answer("جلسه منقضی شده. دوباره از منو شروع کنید.", show_alert=True)
        return ConversationHandler.END

    points = get_points(user_id)

    if data == "time_noop":
        await query.answer()
        return WAITING_CONFIG_DURATION

    if data == "time_plus":
        days = days + 30
        # سقف: به اندازه امتیاز موجود
        max_days = max(30, (points - volume) * 30)
        if days > max_days:
            days = max_days
            await query.answer("به سقف امتیاز موجود رسیدید.", show_alert=True)
        else:
            await query.answer(f"+۳۰ روز → {days} روز")
        context.user_data["svc_expire_days"] = days
        await query.edit_message_text(
            _duration_text(volume, days, points),
            parse_mode="Markdown",
            reply_markup=_duration_keyboard(volume, days, points)
        )
        return WAITING_CONFIG_DURATION

    if data == "time_minus":
        if days <= 30:
            await query.answer("حداقل ۳۰ روز است.", show_alert=True)
            return WAITING_CONFIG_DURATION
        days = days - 30
        await query.answer(f"−۳۰ روز → {days} روز")
        context.user_data["svc_expire_days"] = days
        await query.edit_message_text(
            _duration_text(volume, days, points),
            parse_mode="Markdown",
            reply_markup=_duration_keyboard(volume, days, points)
        )
        return WAITING_CONFIG_DURATION

    if data == "time_confirm":
        cost = _config_cost(volume, days)
        if points < cost:
            await query.answer(
                f"امتیاز کافی نیست! لازم: {cost} | موجودی: {points}",
                show_alert=True
            )
            return WAITING_CONFIG_DURATION

        context.user_data["svc_expire_days"] = days
        context.user_data["svc_total_cost"] = cost
        await query.answer()

        keyboard = [
            [InlineKeyboardButton("خودکار انتخاب کن", callback_data="username_auto")],
            [InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="username_cancel")],
        ]
        await query.edit_message_text(
            f"🛒 سرویس مورد نظر انتخاب شد.\n"
            f"📊 حجم: *{volume} گیگابایت*\n"
            f"📅 مدت: *{days} روز*\n"
            f"⭐ امتیاز کسر می‌شود: *{cost}*\n\n"
            f"لطفا یک نام کاربری با حروف لاتین به طول حداکثر ۲۰ کاراکتر وارد نمایید. 👇",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_SERVICE_USERNAME

    await query.answer()
    return WAITING_CONFIG_DURATION


async def ask_username_for_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع اکانت تست — درخواست نام کاربری"""
    user_id = update.effective_user.id
    if is_blocked(user_id):
        await update.message.reply_text("⛔️ شما از ربات مسدود شده‌اید.")
        return ConversationHandler.END
    if not await require_membership(update, context):
        return ConversationHandler.END

    ok, msg = can_claim_test(user_id)
    if not ok:
        await update.message.reply_text(msg)
        return ConversationHandler.END

    context.user_data["svc_type"] = "test"
    context.user_data["svc_volume_gb"] = None
    context.user_data["svc_volume_mb"] = 100
    context.user_data["svc_expire_days"] = 1
    context.user_data["svc_note"] = "test"
    context.user_data["svc_vol_display"] = "100 مگابایت"

    keyboard = [
        [InlineKeyboardButton("خودکار انتخاب کن", callback_data="username_auto")],
        [InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="username_cancel")],
    ]
    await update.message.reply_text(
        "🛒 سرویس مورد نظر انتخاب شد.\n"
        "📊 حجم: *100 مگابایت*\n"
        "⏰ اعتبار: *1 روز*\n\n"
        "لطفا یک نام کاربری با حروف لاتین به طول حداکثر ۲۰ کاراکتر وارد نمایید. 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_SERVICE_USERNAME


async def service_username_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت نام کاربری دستی"""
    user_id = update.effective_user.id
    if is_blocked(user_id):
        return ConversationHandler.END

    raw = update.message.text.strip()
    ok, result = is_valid_panel_username(raw)
    if not ok:
        await update.message.reply_text(
            f"❌ {result}\n\nدوباره وارد کنید یا روی «انتخاب خودکار» بزنید:"
        )
        return WAITING_SERVICE_USERNAME

    await create_service_with_username(update, context, custom_username=result)
    return ConversationHandler.END


async def service_username_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب خودکار نام کاربری"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if is_blocked(user_id):
        await query.edit_message_text("⛔️ شما از ربات مسدود شده‌اید.")
        return ConversationHandler.END

    await query.edit_message_text("⏳ در حال ساخت سرویس...")
    await create_service_with_username(query, context, custom_username=None, from_query=True)
    return ConversationHandler.END


async def service_username_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو و بازگشت به منوی اصلی"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    for k in list(context.user_data.keys()):
        if k.startswith("svc_"):
            context.user_data.pop(k, None)
    await query.edit_message_text("🏠 به منوی اصلی بازگشتید.")
    await context.bot.send_message(
        chat_id=user_id,
        text="منوی اصلی",
        reply_markup=main_keyboard(user_id)
    )
    return ConversationHandler.END


def build_service_keyboard(vol_btn: str, time_btn: str) -> InlineKeyboardMarkup:
    """کیبورد استایل فروشگاهی برای نمایش سرویس"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(time_btn, callback_data="svcinfo_time"),
            InlineKeyboardButton("📅 زمان اشتراک", callback_data="svcinfo_time"),
        ],
        [
            InlineKeyboardButton(vol_btn, callback_data="svcinfo_vol"),
            InlineKeyboardButton("🌐 حجم سرویس", callback_data="svcinfo_vol"),
        ],
        [InlineKeyboardButton("📱 دریافت QR Code", callback_data="svc_get_qr")],
        [InlineKeyboardButton("📚 آموزش نصب", callback_data="svc_install_guide")],
        [InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="svc_back_main")],
    ])


async def create_service_with_username(update_or_query, context, custom_username=None, from_query=False):
    """ساخت نهایی سرویس در مرزبان و ارسال به سبک فروشگاهی (QR + جزئیات)"""
    if from_query:
        user_id = update_or_query.from_user.id
        chat_id = user_id
        async def reply(text, **kwargs):
            try:
                await update_or_query.edit_message_text(text, **kwargs)
            except Exception:
                await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
    else:
        user_id = update_or_query.effective_user.id
        chat_id = user_id
        async def reply(text, **kwargs):
            await update_or_query.message.reply_text(text, **kwargs)

    svc_type = context.user_data.get("svc_type", "config")
    volume_gb = context.user_data.get("svc_volume_gb")
    volume_mb = context.user_data.get("svc_volume_mb")
    expire_days = context.user_data.get("svc_expire_days")
    note_extra = context.user_data.get("svc_note", "")
    vol_display = context.user_data.get("svc_vol_display", "")

    total_cost = context.user_data.get("svc_total_cost")
    if svc_type == "config":
        if total_cost is None and volume_gb and expire_days:
            total_cost = _config_cost(volume_gb, expire_days)
        points = get_points(user_id)
        if points < (total_cost or volume_gb or 0):
            await reply("❌ امتیاز کافی ندارید!")
            return
    elif svc_type == "test":
        ok, msg = can_claim_test(user_id)
        if not ok:
            await reply(msg)
            return

    if not from_query:
        await reply("⏳ در حال ساخت سرویس...")

    # اکانت تست → مرزبان | کانفیگ اصلی → پاسارگاد
    create_fn = marzban_create_user if svc_type == "test" else pasargad_create_user
    panel_name = "مرزبان" if svc_type == "test" else "پاسارگاد"

    try:
        result = await asyncio.to_thread(
            create_fn,
            user_id,
            volume_gb,
            volume_mb,
            expire_days,
            note_extra or "",
            custom_username,
        )
    except Exception as e:
        logger.exception("%s create user failed", panel_name)
        err_text = (
            f"❌ ساخت سرویس ناموفق بود ({panel_name}).\n"
            f"{'امتیازی از شما کسر نشد.' if svc_type == 'config' else ''}\n\n"
            f"لطفاً بعداً دوباره تلاش کنید یا به پشتیبانی پیام دهید:\n"
            f"👉 {SUPPORT_USERNAME}\n\n"
            f"خطا: `{e}`"
        )
        await reply(err_text, parse_mode="Markdown")
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"⚠️ خطا در ساخت سرویس ({panel_name})\n"
                    f"کاربر: `{user_id}`\nنوع: {svc_type}\nحجم: {vol_display}\nخطا: {e}"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass
        return

    tracking = generate_tracking_code()
    if svc_type == "test":
        set_last_test(user_id)
        add_config_history(user_id, 0, tracking, deduct_points=False, reason="اکانت تست 100 مگابایت")
    else:
        # کسر امتیاز = حجم + زمان (هر ۳۰ روز ۱ امتیاز)
        cost = total_cost or volume_gb
        add_config_history(
            user_id, cost, tracking,
            deduct_points=True,
            reason=f"کانفیگ {volume_gb} گیگ / {expire_days or 0} روز"
        )

    sub_url = result.get("subscription_url") or ""
    panel_user = result.get("username") or "-"

    # حجم و زمان دقیق برای نمایش
    if volume_mb:
        vol_btn = f"{int(volume_mb)} مگابایت"
        vol_text = f"{int(volume_mb)} مگابایت"
    else:
        vol_btn = f"{int(volume_gb)} گیگابایت"
        vol_text = f"{int(volume_gb)} گیگابایت"

    if svc_type == "test":
        time_btn = "1 روز"
        expire_days_show = 1
    elif expire_days and expire_days > 0:
        time_btn = f"{int(expire_days)} روز"
        expire_days_show = int(expire_days)
    else:
        time_btn = "نامحدود"
        expire_days_show = 0

    # ذخیره برای دکمه‌های بعدی (QR و ...)
    context.user_data["last_sub_url"] = sub_url
    context.user_data["last_panel_user"] = panel_user

    # کپشن استایل فروشگاهی (HTML برای لینک قابل‌کلیک بدون مشکل _)
    caption = (
        f"🔑 <b>اشتراک شما با موفقیت ساخته شد.</b>\n\n"
        f"👤 نام کاربری شما :\n"
        f"<code>{panel_user}</code>\n\n"
        f"🔗 لینک اشتراک شما:\n"
        f"{sub_url if sub_url else '—'}\n\n"
        f"👆 برای کپی کردن لینک بالا فقط کافیست آدرس لینک را یک بار لمس کنید!"
    )
    if svc_type == "config":
        caption += f"\n\n⭐ امتیاز باقی‌مانده: <b>{get_points(user_id)}</b>"
    elif svc_type == "test":
        caption += "\n\n📌 هر ۲۴ ساعت یک‌بار می‌توانید اکانت تست بگیرید."

    keyboard = build_service_keyboard(vol_btn, time_btn)

    # اول پیام در حال ساخت را به نتیجه تبدیل کن
    if from_query:
        try:
            await update_or_query.edit_message_text("✅ سرویس آماده شد.")
        except Exception:
            pass

    # ارسال QR بزرگ با کپشن استایل فروشگاهی
    if sub_url:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=qr_code_url(sub_url, size=500),
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except Exception:
            logger.exception("ارسال QR ناموفق")
            await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption + f"\n\n⚠️ لینک خالی برگشت. پشتیبانی: {SUPPORT_USERNAME}",
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    try:
        uname = "-"
        if from_query:
            uname = update_or_query.from_user.first_name or "-"
        else:
            uname = update_or_query.effective_user.first_name or "-"
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"{'🧪' if svc_type == 'test' else '📦'} *سرویس ساخته شد*\n\n"
                f"👤 {uname} (`{user_id}`)\n"
                f"📊 حجم: *{vol_text}*\n"
                f"⏰ زمان: *{time_btn}*\n"
                f"🖥 یوزر پنل: `{panel_user}`\n"
                f"🔑 کد: `{tracking}`"
            ),
            parse_mode="Markdown"
        )
    except Exception:
        pass

    for k in list(context.user_data.keys()):
        if k.startswith("svc_"):
            context.user_data.pop(k, None)


async def service_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دکمه‌های اطلاعاتی / QR / آموزش نصب بعد از ساخت سرویس"""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    if data in ("svcinfo_time", "svcinfo_vol"):
        await query.answer("اطلاعات سرویس شما ✅", show_alert=False)
        return

    if data == "svc_get_qr":
        sub_url = context.user_data.get("last_sub_url")
        if not sub_url:
            await query.answer("لینک ساب یافت نشد. دوباره سرویس بگیرید.", show_alert=True)
            return
        await query.answer()
        try:
            await context.bot.send_photo(
                chat_id=user_id,
                photo=qr_code_url(sub_url, size=500),
                caption="📱 کد QR لینک اشتراک شما"
            )
        except Exception:
            await query.answer("ارسال QR ناموفق بود.", show_alert=True)
        return

    if data == "svc_install_guide":
        await query.answer()
        guide = (
            "📚 *آموزش نصب*\n\n"
            "1️⃣ اپ مناسب سیستم خود را نصب کنید:\n"
            "• اندروید: *v2rayNG* یا *Hiddify*\n"
            "• آیفون: *Streisand* یا *V2Box*\n"
            "• ویندوز: *Hiddify* یا *v2rayN*\n\n"
            "2️⃣ لینک اشتراک را کپی کنید\n"
            "3️⃣ در اپ روی ➕ یا Import from clipboard بزنید\n"
            "4️⃣ سرویس را وصل کنید ✅\n\n"
            f"در صورت مشکل به پشتیبانی پیام دهید:\n👉 {SUPPORT_USERNAME}"
        )
        await context.bot.send_message(chat_id=user_id, text=guide, parse_mode="Markdown")
        return

    if data == "svc_back_main":
        await query.answer()
        await context.bot.send_message(
            chat_id=user_id,
            text="🏠 منوی اصلی",
            reply_markup=main_keyboard(user_id)
        )
        return


async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_blocked(user_id):
        return
    if not await require_membership(update, context):
        return

    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    level_name, refs, bonus = get_user_level(user_id)

    await update.message.reply_text(
        f"🔗 *لینک اختصاصی دعوت شما:*\n\n"
        f"`{link}`\n\n"
        f"🏅 سطح شما: *{level_name}*\n"
        f"👥 زیرمجموعه: *{refs}*\n"
        f"⭐ امتیاز هر دعوت: *{1 + bonus}*\n\n"
        f"هر کسی که از طریق این لینک ربات را استارت کند و قبلاً عضو نبوده باشد،\n"
        f"امتیاز به حساب شما اضافه می‌شود.",
        parse_mode="Markdown"
    )


async def account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if is_blocked(user_id):
        return
    if not await require_membership(update, context):
        return

    stats, refs, history = get_user_stats(user_id)
    if stats:
        points, configs, joined, warnings = stats
    else:
        points, configs, joined, warnings = 0, 0, "-", 0

    level_name, _, bonus = get_user_level(user_id)

    text = (
        f"👤 *حساب کاربری شما*\n\n"
        f"🆔 آیدی عددی: `{user_id}`\n"
        f"👤 نام: {user.first_name}\n"
        f"📅 تاریخ عضویت: {joined}\n"
        f"🏅 سطح: *{level_name}*\n"
        f"⭐ امتیاز فعلی: *{points}*\n"
        f"👥 تعداد زیرمجموعه: *{refs}*\n"
        f"🎁 تعداد کانفینگ دریافتی: *{configs}*\n"
        f"⚠️ تعداد اخطار: *{warnings}/3*\n"
        f"💎 بونوس دعوت: *+{bonus}* امتیاز\n"
    )
    if history:
        text += "\n📜 *تاریخچه کانفینگ‌ها:*\n"
        for vol, code, date in history[:5]:
            text += f"• {vol} گیگ | کد: `{code}` | {date}\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def points_history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_blocked(user_id):
        return
    if not await require_membership(update, context):
        return

    rows = get_points_history(user_id, 15)
    if not rows:
        await update.message.reply_text("📜 هنوز تاریخچه امتیازی ندارید.")
        return

    text = "📜 *تاریخچه امتیاز (۱۵ مورد آخر)*\n\n"
    for amount, reason, date in rows:
        sign = "+" if amount > 0 else ""
        emoji = "🟢" if amount > 0 else "🔴"
        text += f"{emoji} `{sign}{amount}` | {reason}\n   └ {date}\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_membership(update, context):
        return

    await update.message.reply_text(
        f"📞 *پشتیبانی*\n\n"
        f"برای ارتباط با پشتیبانی به آیدی زیر پیام دهید:\n"
        f"👉 {SUPPORT_USERNAME}",
        parse_mode="Markdown"
    )


async def help_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_membership(update, context):
        return

    text = (
        "ℹ️ *راهنمای استفاده از ربات*\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🎁 *دریافت کانفینگ رایگان*\n"
        "هر ۱ امتیاز = ۱ گیگ — همراه با کد QR\n\n"
        "🧪 *اکانت تست*\n"
        "۱۰۰ مگ رایگان — هر ۲۴ ساعت یک‌بار\n\n"
        "👥 *زیرمجموعه‌گیری*\n"
        "هر دعوت = حداقل ۱ امتیاز (+ بونوس سطح)\n\n"
        "🏅 *مدال‌ها (بر اساس دعوت)*\n"
        "🥉 Bronze: ۰–۹ دعوت\n"
        "🥈 Silver: ۱۰–۲۹ دعوت (+۱ بونوس)\n"
        "🥇 Gold: ۳۰–۵۹ دعوت (+۲ بونوس)\n"
        "💎 Diamond: ۶۰–۹۹ دعوت (+۳ بونوس)\n"
        "👑 Legend: ۱۰۰+ دعوت (+۵ بونوس)\n\n"
        "📅 *جایزه روزانه*: هر ۲۴ ساعت ۱ امتیاز\n\n"
        "🎡 *گردونه شانس*: رایگان — هر ۲۴ ساعت یک تاس\n"
        "اگر ۶ بیاید جایزه شانسی می‌گیری\n\n"
        "📜 *تاریخچه امتیاز*: تمام تغییرات امتیاز\n\n"
        "📞 *پشتیبانی*: ارتباط با مدیریت\n\n"
        "⚠️ با ۳ اخطار حساب مسدود می‌شود.\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_blocked(user_id):
        return
    if not await require_membership(update, context):
        return

    rows = get_leaderboard(10)
    if not rows:
        await update.message.reply_text("هنوز کسی زیرمجموعه نگرفته!")
        return

    text = "🏆 *جدول رتبه‌بندی برترین‌ها*\n\n"
    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7

    for i, (uid, first_name, username, refs) in enumerate(rows):
        name = first_name or "کاربر"
        if username:
            name = f"{name} (@{username})"
        medal = medals[i] if i < len(medals) else "🔹"
        level_name, _, _ = get_user_level(uid)
        text += f"{medal} *{i+1}.* {name}\n   └ زیرمجموعه: *{refs}* | {level_name}\n\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def daily_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_blocked(user_id):
        return
    if not await require_membership(update, context):
        return

    success, msg = claim_daily(user_id)
    if success:
        points = get_points(user_id)
        await update.message.reply_text(
            f"🎉 *جایزه روزانه دریافت شد!*\n\n"
            f"+۱ امتیاز به حساب شما اضافه شد.\n"
            f"⭐ امتیاز فعلی: *{points}*",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(msg)


# ================== گردونه شانس ==================
async def wheel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_blocked(user_id):
        return
    if not await require_membership(update, context):
        return

    ok, msg = can_spin_wheel(user_id)
    if not ok:
        await update.message.reply_text(msg)
        return

    keyboard = [[
        InlineKeyboardButton("🎲 انداختن تاس", callback_data="spin_wheel"),
        InlineKeyboardButton("❌ انصراف", callback_data="wheel_cancel")
    ]]
    await update.message.reply_text(
        "🎡 *گردونه شانس*\n\n"
        "✅ کاملاً *رایگان*\n"
        "⏰ هر *۲۴ ساعت* یک‌بار\n\n"
        "🎲 یک تاس انداخته می‌شود (۱ تا ۶)\n"
        "اگر *۶* بیاید، جایزه شانسی می‌گیری:\n"
        "• ۱ / ۲ / ۳ / ۵ / ۱۰ امتیاز\n\n"
        "اگر عدد دیگری بیاید، این بار چیزی نمی‌بری.\n\n"
        "آماده‌ای؟",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def wheel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "wheel_cancel":
        await query.edit_message_text("لغو شد.")
        return

    if query.data != "spin_wheel":
        return

    if is_blocked(user_id):
        await query.edit_message_text("⛔️ شما از ربات مسدود شده‌اید.")
        return

    ok, msg = can_spin_wheel(user_id)
    if not ok:
        await query.edit_message_text(msg)
        return

    # ثبت زمان استفاده (حتی اگر جایزه نگیرد)
    set_last_wheel(user_id)

    try:
        await query.message.delete()
    except Exception:
        pass

    # ارسال ایموجی تاس واقعی تلگرام — خودش می‌چرخه و عدد نهایی را نشان می‌دهد
    dice_msg = await context.bot.send_dice(chat_id=user_id, emoji="🎲")
    dice = dice_msg.dice.value

    # صبر تا انیمیشن تمام شود و عدد روی تاس دیده شود
    await asyncio.sleep(4)

    reward = reward_for_dice(dice)

    if reward > 0:
        update_points(user_id, reward, f"جایزه گردونه شانس (تاس ۶ / +{reward})")
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 *۶ اومد!* +*{reward}* امتیاز گرفتی\n"
                f"⭐ امتیاز فعلی: *{get_points(user_id)}*"
            ),
            parse_mode="Markdown"
        )
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"😔 این بار ۶ نشد. ۲۴ ساعت بعد دوباره بیا.\n⭐ امتیاز: *{get_points(user_id)}*",
            parse_mode="Markdown"
        )


# ================== انتقال امتیاز ==================
async def transfer_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_blocked(user_id):
        return
    if not await require_membership(update, context):
        return

    points = get_points(user_id)
    if points < 1:
        await update.message.reply_text("❌ شما امتیازی برای انتقال ندارید!")
        return

    await update.message.reply_text(
        f"💸 *انتقال امتیاز*\n\n"
        f"امتیاز فعلی شما: *{points}*\n\n"
        f"آیدی عددی کاربری که می‌خواهید به او امتیاز بدهید را وارد کنید:",
        parse_mode="Markdown"
    )
    return WAITING_TRANSFER_ID


async def transfer_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        target_id = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ آیدی نامعتبر است. دوباره وارد کنید:")
        return WAITING_TRANSFER_ID

    if target_id == user_id:
        await update.message.reply_text("❌ نمی‌توانید به خودتان امتیاز منتقل کنید!\nآیدی دیگری وارد کنید:")
        return WAITING_TRANSFER_ID

    target = get_user(target_id)
    if not target:
        await update.message.reply_text("❌ کاربری با این آیدی در ربات یافت نشد.\nآیدی دیگری وارد کنید:")
        return WAITING_TRANSFER_ID

    if is_blocked(target_id):
        await update.message.reply_text("❌ این کاربر مسدود شده و نمی‌تواند امتیاز دریافت کند.")
        return ConversationHandler.END

    context.user_data["transfer_target"] = target_id
    context.user_data["transfer_name"] = target[2] or "کاربر"

    await update.message.reply_text(
        f"✅ کاربر پیدا شد: *{context.user_data['transfer_name']}*\n\n"
        f"حالا تعداد امتیازی که می‌خواهید منتقل کنید را وارد کنید:",
        parse_mode="Markdown"
    )
    return WAITING_TRANSFER_AMOUNT


async def transfer_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        amount = int(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ عدد معتبر و بزرگ‌تر از صفر وارد کنید:")
        return WAITING_TRANSFER_AMOUNT

    target_id = context.user_data.get("transfer_target")
    target_name = context.user_data.get("transfer_name", "کاربر")

    success, result = transfer_points(user_id, target_id, amount)
    if not success:
        await update.message.reply_text(f"❌ {result}")
        return ConversationHandler.END

    new_points = get_points(user_id)
    await update.message.reply_text(
        f"✅ *انتقال موفق!*\n\n"
        f"⭐ {amount} امتیاز به *{target_name}* (`{target_id}`) منتقل شد.\n"
        f"امتیاز باقی‌مانده شما: *{new_points}*",
        parse_mode="Markdown",
        reply_markup=main_keyboard(user_id)
    )

    try:
        sender = update.effective_user
        sender_name = sender.first_name or "یک کاربر"
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"🎉 *امتیاز دریافت کردید!*\n\n"
                f"کاربر *{sender_name}* (`{user_id}`) به شما *{amount}* امتیاز هدیه داد.\n"
                f"امتیاز فعلی شما: *{get_points(target_id)}*"
            ),
            parse_mode="Markdown"
        )
    except:
        pass
    return ConversationHandler.END


# ================== کد هدیه ==================
async def gift_code_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_blocked(user_id):
        return
    if not await require_membership(update, context):
        return

    await update.message.reply_text("🎁 کد هدیه خود را وارد کنید:")
    return WAITING_GIFT_CODE


async def gift_code_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    code = update.message.text.strip()
    points, error = use_gift_code(code, user_id)
    if error:
        await update.message.reply_text(f"❌ {error}")
    else:
        await update.message.reply_text(
            f"✅ کد هدیه با موفقیت اعمال شد!\n"
            f"+{points} امتیاز به حساب شما اضافه شد.\n"
            f"امتیاز فعلی: {get_points(user_id)}"
        )
    return ConversationHandler.END


# ================== پنل مدیریت ==================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "🛠 *پنل مدیریت*\n\nیکی از گزینه‌ها را انتخاب کنید:",
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
    )


async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "بازگشت به منوی اصلی",
        reply_markup=main_keyboard(update.effective_user.id)
    )
    return ConversationHandler.END


async def bot_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    s = get_bot_stats()
    text = (
        "📊 *آمار کلی ربات*\n\n"
        f"👥 کل کاربران: *{s['total_users']}*\n"
        f"⛔️ مسدود شده: *{s['blocked']}*\n"
        f"⭐ مجموع امتیازهای موجود: *{s['total_points']}*\n"
        f"🔗 کل دعوت‌ها: *{s['total_refs']}*\n"
        f"🎁 کل کانفینگ‌های تحویل‌شده: *{s['total_configs']}*\n"
        f"🎫 کل کدهای هدیه: *{s['total_gifts']}*\n"
        f"✅ کدهای استفاده‌شده: *{s['used_gifts']}*"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=admin_keyboard())



# ---------- نمایش کاربران ----------
async def show_all_users_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await send_users_page(update, context, page=0)


async def send_users_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    per_page = 10
    rows, total = get_users_page(page, per_page)

    if not rows and page == 0:
        text = "❌ هیچ کاربری در ربات ثبت نشده است."
        if update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text, reply_markup=admin_keyboard())
        return

    if not rows:
        if update.callback_query:
            await update.callback_query.answer("صفحه دیگری وجود ندارد.", show_alert=True)
        return

    total_pages = (total + per_page - 1) // per_page
    start_num = page * per_page + 1

    text = f"📋 *لیست تمام کاربران*\n"
    text += f"صفحه *{page + 1}* از *{total_pages}* | کل: *{total}* کاربر\n"
    text += "━━━━━━━━━━━━━━━━━━\n\n"

    for i, (uid, username, first_name, points, is_blocked_flag, joined, warnings) in enumerate(rows):
        name = first_name or "بدون نام"
        uname = f"@{username}" if username else "بدون یوزرنیم"
        status = "⛔️ مسدود" if is_blocked_flag else "✅ فعال"
        warnings = warnings or 0
        level_name, _, _ = get_user_level(uid)
        text += (
            f"*{start_num + i}.* {name}\n"
            f"   🆔 `{uid}` | {uname}\n"
            f"   ⭐ {points} | {status} | {level_name}\n"
            f"   ⚠️ {warnings}/3 | 📅 {joined or '-'}\n\n"
        )

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ صفحه قبل", callback_data=f"users_page_{page - 1}"))
    if (page + 1) * per_page < total:
        buttons.append(InlineKeyboardButton("صفحه بعد ➡️", callback_data=f"users_page_{page + 1}"))

    keyboard = []
    if buttons:
        keyboard.append(buttons)
    keyboard.append([InlineKeyboardButton("🔙 بستن", callback_data="users_close")])
    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def users_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return

    data = query.data
    if data == "users_close":
        await query.edit_message_text("✅ لیست بسته شد.")
        await context.bot.send_message(chat_id=ADMIN_ID, text="بازگشت به پنل مدیریت", reply_markup=admin_keyboard())
        return

    if data.startswith("users_page_"):
        try:
            page = int(data.replace("users_page_", ""))
            await send_users_page(update, context, page=page)
        except:
            await query.answer("خطا در بارگذاری صفحه.", show_alert=True)


# ---------- امتیاز به همه ----------
async def admin_gift_all_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("🎁 تعداد امتیازی که می‌خواهید به *همه کاربران* بدهید را وارد کنید:")
    return WAITING_ADMIN_GIFT_ALL_POINTS


async def admin_gift_all_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        points = int(update.message.text.strip())
        if points <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ عدد معتبر و بزرگ‌تر از صفر وارد کنید:")
        return WAITING_ADMIN_GIFT_ALL_POINTS

    context.user_data["admin_gift_points"] = points
    keyboard = [[InlineKeyboardButton("ادامه بدون توضیحات", callback_data="admin_gift_all_skip")]]
    await update.message.reply_text(
        f"✅ تعداد امتیاز: *{points}*\n\n"
        f"حالا توضیحات پیام را بنویسید (اختیاری):\n"
        f"یا روی دکمه زیر بزنید تا بدون توضیحات ارسال شود.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_ADMIN_GIFT_ALL_DESC


async def admin_gift_all_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    points = context.user_data.get("admin_gift_points", 0)
    description = update.message.text.strip()
    user_ids = get_all_user_ids()
    success = 0
    fail = 0

    await update.message.reply_text(f"⏳ در حال ارسال {points} امتیاز به {len(user_ids)} کاربر...")

    msg = f"🎉 *هدیه از طرف مدیریت!*\n\n⭐ *{points}* امتیاز به حساب شما اضافه شد."
    if description:
        msg += f"\n\n📝 *توضیحات:*\n{description}"

    for uid in user_ids:
        try:
            update_points(uid, points, "هدیه مدیریت (همه)")
            await context.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
            success += 1
        except:
            fail += 1

    await update.message.reply_text(
        f"✅ عملیات تمام شد.\n\nامتیاز داده‌شده: *{points}*\nموفق: {success}\nناموفق: {fail}",
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
    )
    return ConversationHandler.END


async def admin_gift_all_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return ConversationHandler.END

    points = context.user_data.get("admin_gift_points", 0)
    user_ids = get_all_user_ids()
    success = 0
    fail = 0

    await query.edit_message_text(f"⏳ در حال ارسال {points} امتیاز به {len(user_ids)} کاربر...")
    msg = f"🎉 *هدیه از طرف مدیریت!*\n\n⭐ *{points}* امتیاز به حساب شما اضافه شد."

    for uid in user_ids:
        try:
            update_points(uid, points, "هدیه مدیریت (همه)")
            await context.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
            success += 1
        except:
            fail += 1

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"✅ عملیات تمام شد.\n\nامتیاز داده‌شده: *{points}*\nموفق: {success}\nناموفق: {fail}",
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
    )
    return ConversationHandler.END


# ---------- امتیاز به یک کاربر ----------
async def admin_gift_one_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("🎁 آیدی عددی کاربری که می‌خواهید به او امتیاز بدهید را وارد کنید:")
    return WAITING_ADMIN_GIFT_ONE_ID


async def admin_gift_one_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        uid = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ آیدی نامعتبر است. دوباره وارد کنید:")
        return WAITING_ADMIN_GIFT_ONE_ID

    user = get_user(uid)
    if not user:
        await update.message.reply_text("❌ کاربری با این آیدی یافت نشد. دوباره وارد کنید:")
        return WAITING_ADMIN_GIFT_ONE_ID

    context.user_data["admin_gift_one_uid"] = uid
    context.user_data["admin_gift_one_name"] = user[2] or "کاربر"

    await update.message.reply_text(
        f"✅ کاربر پیدا شد: *{context.user_data['admin_gift_one_name']}* (`{uid}`)\n\n"
        f"حالا تعداد امتیاز را وارد کنید:",
        parse_mode="Markdown"
    )
    return WAITING_ADMIN_GIFT_ONE_POINTS


async def admin_gift_one_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        points = int(update.message.text.strip())
        if points <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ عدد معتبر و بزرگ‌تر از صفر وارد کنید:")
        return WAITING_ADMIN_GIFT_ONE_POINTS

    context.user_data["admin_gift_one_points"] = points
    keyboard = [[InlineKeyboardButton("ادامه بدون توضیحات", callback_data="admin_gift_one_skip")]]
    await update.message.reply_text(
        f"✅ تعداد امتیاز: *{points}*\n\n"
        f"حالا توضیحات پیام را بنویسید (اختیاری):\n"
        f"یا روی دکمه زیر بزنید تا بدون توضیحات ارسال شود.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_ADMIN_GIFT_ONE_DESC


async def admin_gift_one_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    uid = context.user_data.get("admin_gift_one_uid")
    points = context.user_data.get("admin_gift_one_points", 0)
    name = context.user_data.get("admin_gift_one_name", "کاربر")
    description = update.message.text.strip()

    update_points(uid, points, "هدیه مدیریت")

    msg = f"🎉 *هدیه از طرف مدیریت!*\n\n⭐ *{points}* امتیاز به حساب شما اضافه شد."
    if description:
        msg += f"\n\n📝 *توضیحات:*\n{description}"

    try:
        await context.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
        await update.message.reply_text(
            f"✅ *{points}* امتیاز با موفقیت به *{name}* (`{uid}`) ارسال شد.",
            parse_mode="Markdown",
            reply_markup=admin_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ ارسال پیام ناموفق بود (امتیاز اضافه شد).\nخطا: {e}",
            reply_markup=admin_keyboard()
        )
    return ConversationHandler.END


async def admin_gift_one_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return ConversationHandler.END

    uid = context.user_data.get("admin_gift_one_uid")
    points = context.user_data.get("admin_gift_one_points", 0)
    name = context.user_data.get("admin_gift_one_name", "کاربر")

    update_points(uid, points, "هدیه مدیریت")
    msg = f"🎉 *هدیه از طرف مدیریت!*\n\n⭐ *{points}* امتیاز به حساب شما اضافه شد."

    try:
        await context.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
        await query.edit_message_text(
            f"✅ *{points}* امتیاز با موفقیت به *{name}* (`{uid}`) ارسال شد.",
            parse_mode="Markdown"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text="بازگشت به پنل مدیریت", reply_markup=admin_keyboard())
    except Exception as e:
        await query.edit_message_text(f"❌ ارسال پیام ناموفق بود (امتیاز اضافه شد).\nخطا: {e}")
        await context.bot.send_message(chat_id=ADMIN_ID, text=".", reply_markup=admin_keyboard())
    return ConversationHandler.END


# ---------- کسر امتیاز ----------
async def deduct_one_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("➖ آیدی عددی کاربری که می‌خواهید از او امتیاز کسر کنید را وارد کنید:")
    return WAITING_DEDUCT_ONE_ID


async def deduct_one_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        uid = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ آیدی نامعتبر است. دوباره وارد کنید:")
        return WAITING_DEDUCT_ONE_ID

    user = get_user(uid)
    if not user:
        await update.message.reply_text("❌ کاربری با این آیدی یافت نشد. دوباره وارد کنید:")
        return WAITING_DEDUCT_ONE_ID

    points = get_points(uid)
    context.user_data["deduct_one_uid"] = uid
    context.user_data["deduct_one_name"] = user[2] or "کاربر"
    context.user_data["deduct_one_current"] = points

    keyboard = [[InlineKeyboardButton("کسر کل امتیازها", callback_data="deduct_one_all")]]
    await update.message.reply_text(
        f"👤 کاربر: *{context.user_data['deduct_one_name']}* (`{uid}`)\n"
        f"⭐ موجودی فعلی: *{points}* امتیاز\n\n"
        f"تعداد امتیازی که می‌خواهید کسر کنید را وارد کنید:\n"
        f"یا روی دکمه زیر بزنید تا *همه* امتیازها کسر شود.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_DEDUCT_ONE_AMOUNT


async def deduct_one_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        amount = int(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ عدد معتبر و بزرگ‌تر از صفر وارد کنید:")
        return WAITING_DEDUCT_ONE_AMOUNT

    uid = context.user_data.get("deduct_one_uid")
    name = context.user_data.get("deduct_one_name", "کاربر")

    deducted = deduct_points(uid, amount, "کسر توسط مدیریت")
    new_points = get_points(uid)

    await update.message.reply_text(
        f"✅ *کسر امتیاز انجام شد*\n\n"
        f"👤 کاربر: *{name}* (`{uid}`)\n"
        f"➖ کسر شده: *{deducted}* امتیاز\n"
        f"⭐ موجودی جدید: *{new_points}*",
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
    )
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=f"⚠️ مدیریت *{deducted}* امتیاز از حساب شما کسر کرد.\nامتیاز فعلی: *{new_points}*",
            parse_mode="Markdown"
        )
    except:
        pass
    return ConversationHandler.END


async def deduct_one_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return ConversationHandler.END

    uid = context.user_data.get("deduct_one_uid")
    name = context.user_data.get("deduct_one_name", "کاربر")
    current = context.user_data.get("deduct_one_current", 0)

    set_points(uid, 0, "کسر کل امتیاز توسط مدیریت")

    await query.edit_message_text(
        f"✅ *تمام امتیازها کسر شد*\n\n"
        f"👤 کاربر: *{name}* (`{uid}`)\n"
        f"➖ کسر شده: *{current}* امتیاز\n"
        f"⭐ موجودی جدید: *0*",
        parse_mode="Markdown"
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text="بازگشت به پنل", reply_markup=admin_keyboard())
    try:
        await context.bot.send_message(
            chat_id=uid,
            text="⚠️ مدیریت *تمام* امتیازهای شما را کسر کرد.\nامتیاز فعلی: *0*",
            parse_mode="Markdown"
        )
    except:
        pass
    return ConversationHandler.END


async def deduct_all_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    keyboard = [[InlineKeyboardButton("کسر کل امتیازها", callback_data="deduct_all_zero")]]
    await update.message.reply_text(
        "➖ *کسر امتیاز از تمامی کاربران*\n\n"
        "تعداد امتیازی که می‌خواهید از *هر کاربر* کسر شود را وارد کنید:\n"
        "یا روی دکمه زیر بزنید تا امتیاز *همه کاربران* صفر شود.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_DEDUCT_ALL_AMOUNT


async def deduct_all_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        amount = int(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ عدد معتبر و بزرگ‌تر از صفر وارد کنید:")
        return WAITING_DEDUCT_ALL_AMOUNT

    user_ids = get_all_user_ids()
    success = 0
    total_deducted = 0

    await update.message.reply_text(f"⏳ در حال کسر {amount} امتیاز از {len(user_ids)} کاربر...")

    for uid in user_ids:
        try:
            deducted = deduct_points(uid, amount, "کسر گروهی توسط مدیریت")
            total_deducted += deducted
            success += 1
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"⚠️ مدیریت *{deducted}* امتیاز از حساب شما کسر کرد.\nامتیاز فعلی: *{get_points(uid)}*",
                    parse_mode="Markdown"
                )
            except:
                pass
        except:
            pass

    await update.message.reply_text(
        f"✅ عملیات تمام شد.\n\n"
        f"➖ از هر کاربر حداکثر *{amount}* امتیاز کسر شد\n"
        f"👥 تعداد کاربران: {success}\n"
        f"📉 مجموع امتیاز کسر شده: *{total_deducted}*",
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
    )
    return ConversationHandler.END


async def deduct_all_zero(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return ConversationHandler.END

    user_ids = get_all_user_ids()
    success = 0
    total_deducted = 0

    await query.edit_message_text(f"⏳ در حال صفر کردن امتیاز {len(user_ids)} کاربر...")

    for uid in user_ids:
        try:
            current = get_points(uid)
            set_points(uid, 0, "صفر کردن امتیاز توسط مدیریت")
            total_deducted += current
            success += 1
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text="⚠️ مدیریت *تمام* امتیازهای شما را کسر کرد.\nامتیاز فعلی: *0*",
                    parse_mode="Markdown"
                )
            except:
                pass
        except:
            pass

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"✅ عملیات تمام شد.\n\n"
            f"➖ امتیاز همه کاربران صفر شد\n"
            f"👥 تعداد کاربران: {success}\n"
            f"📉 مجموع امتیاز کسر شده: *{total_deducted}*"
        ),
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
    )
    return ConversationHandler.END


# ---------- اخطار ----------
async def warning_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("⚠️ آیدی عددی کاربری که می‌خواهید به او اخطار دهید را وارد کنید:")
    return WAITING_WARNING_ID


async def warning_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        uid = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ آیدی نامعتبر است. دوباره وارد کنید:")
        return WAITING_WARNING_ID

    user = get_user(uid)
    if not user:
        await update.message.reply_text("❌ کاربری با این آیدی یافت نشد. دوباره وارد کنید:")
        return WAITING_WARNING_ID

    if is_blocked(uid):
        await update.message.reply_text("❌ این کاربر قبلاً مسدود شده است.", reply_markup=admin_keyboard())
        return ConversationHandler.END

    context.user_data["warning_uid"] = uid
    context.user_data["warning_name"] = user[2] or "کاربر"
    current_warnings = get_warnings(uid)

    keyboard = [[InlineKeyboardButton("ادامه بدون توضیحات", callback_data="warning_skip")]]
    await update.message.reply_text(
        f"✅ کاربر پیدا شد: *{context.user_data['warning_name']}* (`{uid}`)\n"
        f"⚠️ اخطار فعلی: *{current_warnings}/3*\n\n"
        f"حالا توضیحات اخطار را بنویسید (اختیاری):\n"
        f"یا روی دکمه زیر بزنید تا بدون توضیحات ارسال شود.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_WARNING_DESC


async def process_warning(update_or_query, context, description=None):
    uid = context.user_data.get("warning_uid")
    name = context.user_data.get("warning_name", "کاربر")
    new_warnings = add_warning(uid)

    msg = "⚠️ *اخطار از طرف مدیریت*\n\n"
    if description:
        msg += f"📝 *توضیحات:*\n{description}\n\n"
    else:
        msg += "لطفاً قوانین ربات را رعایت کنید.\n\n"
    msg += f"⚠️ تعداد اخطارهای شما: *{new_warnings}/3*"

    if new_warnings >= 3:
        block_user(uid)
        msg += "\n\n⛔️ *به دلیل دریافت ۳ اخطار، حساب شما از ربات مسدود شد.*"
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⛔️ کاربر *{name}* (`{uid}`) به دلیل ۳ اخطار به‌صورت خودکار مسدود شد.",
                parse_mode="Markdown"
            )
        except:
            pass

    try:
        await context.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")

        if hasattr(update_or_query, 'message') and update_or_query.message:
            reply_text = f"✅ اخطار با موفقیت به *{name}* (`{uid}`) ارسال شد.\n⚠️ اخطار جدید: *{new_warnings}/3*"
            if new_warnings >= 3:
                reply_text += "\n\n⛔️ کاربر به دلیل ۳ اخطار *مسدود* شد."
            await update_or_query.message.reply_text(reply_text, parse_mode="Markdown", reply_markup=admin_keyboard())
        else:
            reply_text = f"✅ اخطار با موفقیت به *{name}* (`{uid}`) ارسال شد.\n⚠️ اخطار جدید: *{new_warnings}/3*"
            if new_warnings >= 3:
                reply_text += "\n\n⛔️ کاربر به دلیل ۳ اخطار *مسدود* شد."
            await update_or_query.edit_message_text(reply_text, parse_mode="Markdown")
            await context.bot.send_message(chat_id=ADMIN_ID, text="بازگشت به پنل مدیریت", reply_markup=admin_keyboard())
    except Exception as e:
        error_msg = f"❌ ارسال اخطار ناموفق بود.\nخطا: {e}"
        if hasattr(update_or_query, 'message') and update_or_query.message:
            await update_or_query.message.reply_text(error_msg, reply_markup=admin_keyboard())
        else:
            await update_or_query.edit_message_text(error_msg)
            await context.bot.send_message(chat_id=ADMIN_ID, text=".", reply_markup=admin_keyboard())


async def warning_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    description = update.message.text.strip()
    await process_warning(update, context, description)
    return ConversationHandler.END


async def warning_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return ConversationHandler.END
    await process_warning(query, context, description=None)
    return ConversationHandler.END


# ---------- جستجو ----------
async def search_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("🔍 آیدی عددی کاربر را وارد کنید:")
    return WAITING_SEARCH_ID


async def search_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        uid = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ آیدی نامعتبر است. دوباره وارد کنید:")
        return WAITING_SEARCH_ID

    stats, refs, history = get_user_stats(uid)
    if not stats:
        await update.message.reply_text("❌ کاربری با این آیدی یافت نشد.", reply_markup=admin_keyboard())
        return ConversationHandler.END

    points, configs, joined, warnings = stats
    user = get_user(uid)
    username = user[1] if user else None
    first_name = user[2] if user else "-"
    is_blocked_status = "⛔️ مسدود" if (user and user[7] == 1) else "✅ فعال"
    warnings = warnings or 0
    level_name, _, bonus = get_user_level(uid)

    text = (
        f"📊 *آمار کاربر*\n\n"
        f"🆔 آیدی: `{uid}`\n"
        f"👤 نام: {first_name}\n"
        f"🔗 یوزرنیم: @{username if username else 'ندارد'}\n"
        f"📅 تاریخ عضویت: {joined}\n"
        f"📌 وضعیت: {is_blocked_status}\n"
        f"🏅 سطح: *{level_name}* (بونوس: +{bonus})\n"
        f"⚠️ تعداد اخطار: *{warnings}/3*\n\n"
        f"⭐ امتیاز فعلی: *{points}*\n"
        f"👥 تعداد زیرمجموعه: *{refs}*\n"
        f"🎁 تعداد کانفینگ دریافتی: *{configs}*\n"
    )
    if history:
        text += "\n📜 *تاریخچه کانفینگ‌ها (۵ مورد آخر):*\n"
        for vol, code, date in history[:5]:
            text += f"• {vol} گیگ | `{code}` | {date}\n"

    # تاریخچه امتیاز
    ph = get_points_history(uid, 5)
    if ph:
        text += "\n💰 *آخرین تغییرات امتیاز:*\n"
        for amount, reason, date in ph:
            sign = "+" if amount > 0 else ""
            text += f"• `{sign}{amount}` | {reason} | {date}\n"

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=admin_keyboard())
    return ConversationHandler.END


# ---------- مسدود / رفع مسدود ----------
async def delete_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("🗑 آیدی عددی کاربری که می‌خواهید مسدود کنید را وارد کنید:")
    return WAITING_DELETE_ID


async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        uid = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ آیدی نامعتبر است.")
        return WAITING_DELETE_ID

    if uid == ADMIN_ID:
        await update.message.reply_text("❌ نمی‌توانید خودتان را مسدود کنید!", reply_markup=admin_keyboard())
        return ConversationHandler.END

    block_user(uid)
    await update.message.reply_text(f"✅ کاربر `{uid}` با موفقیت مسدود شد.", parse_mode="Markdown", reply_markup=admin_keyboard())
    return ConversationHandler.END


async def unblock_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("✅ آیدی عددی کاربری که می‌خواهید از مسدودیت خارج کنید را وارد کنید:")
    return WAITING_UNBLOCK_ID


async def unblock_user_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        uid = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ آیدی نامعتبر است.")
        return WAITING_UNBLOCK_ID

    unblock_user(uid)
    await update.message.reply_text(
        f"✅ کاربر `{uid}` از مسدودیت خارج شد.\n(تعداد اخطارها نیز صفر شد)",
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
    )
    return ConversationHandler.END


# ---------- ساخت کد هدیه (با تعداد استفاده) ----------
async def create_gift_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("🎁 تعداد امتیاز این کد هدیه را وارد کنید (مثلاً 5):")
    return WAITING_CREATE_GIFT_POINTS


async def create_gift_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        points = int(update.message.text.strip())
        if points <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ عدد معتبر وارد کنید:")
        return WAITING_CREATE_GIFT_POINTS

    context.user_data["gift_points"] = points
    await update.message.reply_text(
        f"✅ امتیاز کد: *{points}*\n\n"
        f"حالا *تعداد دفعات قابل استفاده* را وارد کنید:\n"
        f"(۱ = یک‌بار مصرف | بیشتر = کد گروهی)",
        parse_mode="Markdown"
    )
    return WAITING_CREATE_GIFT_USES


async def create_gift_uses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        max_uses = int(update.message.text.strip())
        if max_uses <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ عدد معتبر بزرگ‌تر از صفر وارد کنید:")
        return WAITING_CREATE_GIFT_USES

    context.user_data["gift_max_uses"] = max_uses
    await update.message.reply_text(
        f"✅ تعداد استفاده: *{max_uses}*\n\n"
        f"حالا *مدت اعتبار* را به ساعت وارد کنید:\n"
        f"(۰ = بدون انقضا | مثلاً ۲۴ = یک روز | ۴۸ = دو روز)",
        parse_mode="Markdown"
    )
    return WAITING_CREATE_GIFT_EXPIRES


async def create_gift_expires(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        hours = int(update.message.text.strip())
        if hours < 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ عدد معتبر وارد کنید (۰ یا بیشتر):")
        return WAITING_CREATE_GIFT_EXPIRES

    points = context.user_data.get("gift_points", 1)
    max_uses = context.user_data.get("gift_max_uses", 1)
    code, expires_date = create_gift_code(points, max_uses, hours if hours > 0 else None)

    type_text = "یک‌بار مصرف" if max_uses == 1 else f"گروهی (حداکثر {max_uses} نفر)"
    exp_text = "بدون انقضا" if not expires_date else expires_date

    # ذخیره برای ارسال گروهی
    context.user_data["broadcast_gift_code"] = code
    context.user_data["broadcast_gift_points"] = points
    context.user_data["broadcast_gift_max_uses"] = max_uses
    context.user_data["broadcast_gift_expires"] = exp_text

    keyboard = [
        [InlineKeyboardButton("📢 ارسال به تمام کاربران", callback_data="gift_broadcast_yes")],
        [InlineKeyboardButton("✅ ادامه بدون ارسال", callback_data="gift_broadcast_no")],
    ]

    await update.message.reply_text(
        f"✅ *کد هدیه ساخته شد*\n\n"
        f"🔑 کد: `{code}`\n"
        f"⭐ امتیاز: *{points}*\n"
        f"👥 نوع: {type_text}\n"
        f"⏰ انقضا: {exp_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"آیا می‌خواهید این کد هدیه برای *تمام کاربران* ارسال شود؟",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


async def gift_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return

    if query.data == "gift_broadcast_no":
        await query.edit_message_text(
            f"✅ کد هدیه ذخیره شد.\n"
            f"🔑 کد: `{context.user_data.get('broadcast_gift_code', '-')}`\n\n"
            f"بدون ارسال گروهی ادامه داده شد.",
            parse_mode="Markdown"
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text="بازگشت به پنل مدیریت",
            reply_markup=admin_keyboard()
        )
        return

    if query.data != "gift_broadcast_yes":
        return

    code = context.user_data.get("broadcast_gift_code")
    points = context.user_data.get("broadcast_gift_points", 0)
    max_uses = context.user_data.get("broadcast_gift_max_uses", 1)
    exp_text = context.user_data.get("broadcast_gift_expires", "بدون انقضا")

    if not code:
        await query.edit_message_text("❌ کد هدیه یافت نشد. دوباره بسازید.")
        return

    await query.edit_message_text("⏳ در حال ارسال کد هدیه به تمام کاربران...")

    type_line = "یک‌بار مصرف" if max_uses == 1 else f"قابل استفاده تا {max_uses} نفر"
    msg = (
        "🎁 *هدیه ویژه از طرف مدیریت!*\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "یک کد هدیه اختصاصی برای شما آماده شده ✨\n\n"
        f"🔑 *کد هدیه:*\n`{code}`\n\n"
        f"⭐ امتیاز: *{points}*\n"
        f"👥 {type_line}\n"
        f"⏰ اعتبار: {exp_text}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "برای دریافت، از منوی ربات روی\n"
        "«🎁 کد هدیه» بزن و کد را وارد کن.\n\n"
        "موفق باشی 🌟"
    )

    user_ids = get_all_user_ids()
    success = 0
    fail = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
            success += 1
        except Exception:
            fail += 1

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"✅ *ارسال کد هدیه تمام شد*\n\n"
            f"🔑 کد: `{code}`\n"
            f"📤 موفق: *{success}*\n"
            f"❌ ناموفق: *{fail}*"
        ),
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
    )


# ---------- برودکست ----------
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("📢 پیامی که می‌خواهید برای *تمامی کاربران* ارسال شود را بنویسید:")
    return WAITING_BROADCAST


async def broadcast_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    message = update.message.text
    user_ids = get_all_user_ids()
    success = 0
    fail = 0

    await update.message.reply_text(f"⏳ در حال ارسال به {len(user_ids)} کاربر...")

    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=message)
            success += 1
        except:
            fail += 1

    await update.message.reply_text(
        f"✅ ارسال تمام شد.\n\nموفق: {success}\nناموفق: {fail}",
        reply_markup=admin_keyboard()
    )
    return ConversationHandler.END


# ---------- پیام به کاربر ----------
async def specific_msg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("✉️ آیدی عددی کاربری که می‌خواهید به او پیام بدهید را وارد کنید:")
    return WAITING_SPECIFIC_ID


async def specific_msg_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        uid = int(update.message.text.strip())
        context.user_data["target_uid"] = uid
    except:
        await update.message.reply_text("❌ آیدی نامعتبر است. دوباره وارد کنید:")
        return WAITING_SPECIFIC_ID

    await update.message.reply_text("حالا پیام خود را بنویسید:")
    return WAITING_SPECIFIC_MSG


async def specific_msg_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    uid = context.user_data.get("target_uid")
    message = update.message.text

    try:
        await context.bot.send_message(chat_id=uid, text=message)
        await update.message.reply_text(
            f"✅ پیام با موفقیت به کاربر `{uid}` ارسال شد.",
            parse_mode="Markdown",
            reply_markup=admin_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(f"❌ ارسال ناموفق بود.\nخطا: {e}", reply_markup=admin_keyboard())
    return ConversationHandler.END


# ---------- قطع سرویس ----------
async def disable_service_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await send_services_page(update, context, page=0)


async def send_services_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """نمایش لیست سرویس‌های فعال مرزبان (ساخته‌شده توسط ربات) با صفحه‌بندی"""
    per_page = 8
    offset = page * per_page

    try:
        result = await asyncio.to_thread(marzban_get_users, offset, per_page, "active")
    except Exception as e:
        logger.exception("Failed to list Marzban users")
        text = f"❌ خطا در دریافت لیست سرویس‌ها از پنل مرزبان:\n`{e}`"
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=admin_keyboard())
        return

    users = result.get("users") or []
    total = result.get("total")
    if total is None:
        total = len(users) if page == 0 and len(users) < per_page else offset + len(users) + (1 if len(users) == per_page else 0)

    if not users and page == 0:
        text = "✅ هیچ سرویس فعالی در پنل مرزبان یافت نشد."
        if update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text, reply_markup=admin_keyboard())
        return

    if not users:
        if update.callback_query:
            await update.callback_query.answer("صفحه دیگری وجود ندارد.", show_alert=True)
        return

    total_pages = max(1, (total + per_page - 1) // per_page) if total else page + 1

    text = (
        f"🔌 *لیست سرویس‌های فعال*\n"
        f"صفحه *{page + 1}* از *{total_pages}* | کل تقریبی: *{total}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"روی هر سرویس بزنید تا قطع شود."
    )

    keyboard = []
    for u in users:
        username = u.get("username") or "?"
        status = u.get("status") or "?"
        note = u.get("note") or ""
        data_limit = u.get("data_limit") or 0
        used = u.get("used_traffic") or 0
        gb = format_bytes_gb(data_limit)
        used_gb = format_bytes_gb(used)
        tg_id = parse_tg_from_note(note)
        tg_part = f" | tg:{tg_id}" if tg_id else ""
        label = f"🔌 {username} ({gb}G / {used_gb}G){tg_part}"
        if len(label) > 60:
            label = label[:57] + "..."
        keyboard.append([InlineKeyboardButton(label, callback_data=f"svc_select_{username}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ صفحه قبل", callback_data=f"svc_page_{page - 1}"))
    if len(users) >= per_page:
        nav.append(InlineKeyboardButton("صفحه بعد ➡️", callback_data=f"svc_page_{page + 1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 بستن", callback_data="svc_close")])

    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await update.callback_query.answer()
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def services_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return

    data = query.data

    if data == "svc_close":
        await query.edit_message_text("✅ لیست سرویس‌ها بسته شد.")
        await context.bot.send_message(chat_id=ADMIN_ID, text="بازگشت به پنل مدیریت", reply_markup=admin_keyboard())
        return

    if data.startswith("svc_page_"):
        try:
            page = int(data.replace("svc_page_", ""))
            await send_services_page(update, context, page=page)
        except Exception:
            await query.answer("خطا در بارگذاری صفحه.", show_alert=True)
        return

    if data.startswith("svc_select_"):
        username = data.replace("svc_select_", "", 1)
        context.user_data["disable_svc_username"] = username

        # جزئیات سرویس
        try:
            token = await asyncio.to_thread(marzban_get_token)
            info = await asyncio.to_thread(
                _marzban_request, "GET", f"/api/user/{urllib.parse.quote(username)}", None, token
            )
        except Exception as e:
            await query.edit_message_text(f"❌ خطا در دریافت اطلاعات سرویس:\n`{e}`", parse_mode="Markdown")
            return

        note = info.get("note") or "-"
        status = info.get("status") or "-"
        gb = format_bytes_gb(info.get("data_limit") or 0)
        used_gb = format_bytes_gb(info.get("used_traffic") or 0)
        tg_id = parse_tg_from_note(note)

        text = (
            f"🔌 *قطع سرویس*\n\n"
            f"👤 یوزر پنل: `{username}`\n"
            f"📊 حجم: *{gb}* گیگ | مصرف: *{used_gb}* گیگ\n"
            f"📌 وضعیت: `{status}`\n"
            f"📝 یادداشت: `{note}`\n"
        )
        if tg_id:
            text += f"🆔 تلگرام: `{tg_id}`\n"
        text += "\nآیا می‌خواهید این سرویس را *قطع* کنید؟"

        keyboard = [
            [InlineKeyboardButton("🔌 قطع سرویس", callback_data=f"svc_confirm_{username}")],
            [InlineKeyboardButton("❌ انصراف", callback_data="svc_cancel_confirm")],
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data == "svc_cancel_confirm":
        await query.edit_message_text("لغو شد. برای مشاهده مجدد لیست، دوباره «🔌 قطع سرویس» را بزنید.")
        await context.bot.send_message(chat_id=ADMIN_ID, text="بازگشت به پنل مدیریت", reply_markup=admin_keyboard())
        return

    # svc_confirm_ و svc_disable_skip توسط ConversationHandler مدیریت می‌شوند


async def services_confirm_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ورود به مرحله توضیحات قطع سرویس (از طریق دکمه قطع سرویس)"""
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return ConversationHandler.END

    data = query.data
    if not data.startswith("svc_confirm_"):
        return ConversationHandler.END

    username = data.replace("svc_confirm_", "", 1)
    context.user_data["disable_svc_username"] = username
    keyboard = [[InlineKeyboardButton("ادامه بدون توضیحات", callback_data="svc_disable_skip")]]
    await query.edit_message_text(
        f"🔌 سرویس `{username}` انتخاب شد.\n\n"
        f"توضیحات قطع سرویس را بنویسید (برای کاربر ارسال می‌شود):\n"
        f"یا روی دکمه زیر بزنید تا بدون توضیحات قطع شود.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_DISABLE_SERVICE_DESC


async def disable_service_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    description = update.message.text.strip()
    await do_disable_service(update, context, description=description)
    return ConversationHandler.END


async def disable_service_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return ConversationHandler.END
    await do_disable_service(query, context, description=None)
    return ConversationHandler.END


async def do_disable_service(update_or_query, context, description=None):
    """اجرای قطع سرویس در مرزبان و اطلاع‌رسانی"""
    username = context.user_data.get("disable_svc_username")
    if not username:
        text = "❌ سرویس انتخاب نشده است. دوباره از منو شروع کنید."
        if hasattr(update_or_query, "message") and update_or_query.message:
            await update_or_query.message.reply_text(text, reply_markup=admin_keyboard())
        else:
            await update_or_query.edit_message_text(text)
        return

    # دریافت info قبل از قطع برای tg_id
    tg_id = None
    try:
        token = await asyncio.to_thread(marzban_get_token)
        info = await asyncio.to_thread(
            _marzban_request, "GET", f"/api/user/{urllib.parse.quote(username)}", None, token
        )
        tg_id = parse_tg_from_note(info.get("note") or "")
    except Exception:
        pass

    try:
        await asyncio.to_thread(marzban_disable_user, username)
    except Exception as e:
        logger.exception("Failed to disable Marzban user")
        err = f"❌ قطع سرویس ناموفق بود.\nخطا: `{e}`"
        if hasattr(update_or_query, "message") and update_or_query.message:
            await update_or_query.message.reply_text(err, parse_mode="Markdown", reply_markup=admin_keyboard())
        else:
            await update_or_query.edit_message_text(err, parse_mode="Markdown")
            await context.bot.send_message(chat_id=ADMIN_ID, text=".", reply_markup=admin_keyboard())
        return

    # پیام به کاربر تلگرام
    user_msg = (
        "⚠️ *سرویس شما قطع شد*\n\n"
        f"سرویس پنل `{username}` توسط مدیریت غیرفعال شد."
    )
    if description:
        user_msg += f"\n\n📝 *توضیحات:*\n{description}"
    user_msg += f"\n\nدر صورت نیاز با پشتیبانی تماس بگیرید:\n👉 {SUPPORT_USERNAME}"

    if tg_id:
        try:
            await context.bot.send_message(chat_id=tg_id, text=user_msg, parse_mode="Markdown")
        except Exception:
            pass

    admin_text = (
        f"✅ *سرویس قطع شد*\n\n"
        f"👤 یوزر پنل: `{username}`\n"
    )
    if tg_id:
        admin_text += f"🆔 تلگرام: `{tg_id}`\n"
    if description:
        admin_text += f"📝 توضیحات: {description}\n"

    if hasattr(update_or_query, "message") and update_or_query.message:
        await update_or_query.message.reply_text(admin_text, parse_mode="Markdown", reply_markup=admin_keyboard())
    else:
        await update_or_query.edit_message_text(admin_text, parse_mode="Markdown")
        await context.bot.send_message(chat_id=ADMIN_ID, text="بازگشت به پنل مدیریت", reply_markup=admin_keyboard())

    context.user_data.pop("disable_svc_username", None)


# ---------- ریست گردونه شانس ----------
async def reset_wheel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "🎡 آیدی عددی کاربری که می‌خواهید گردونه شانسش صفر شود را بفرستید:"
    )
    return WAITING_RESET_WHEEL_ID


async def reset_wheel_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        uid = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ آیدی نامعتبر است. دوباره وارد کنید:")
        return WAITING_RESET_WHEEL_ID

    user = get_user(uid)
    if not user:
        await update.message.reply_text("❌ کاربری با این آیدی یافت نشد. دوباره وارد کنید:")
        return WAITING_RESET_WHEEL_ID

    reset_wheel(uid)
    name = user[2] or "کاربر"
    await update.message.reply_text(
        f"✅ گردونه شانس کاربر *{name}* (`{uid}`) صفر شد.\n"
        f"الان می‌تواند دوباره تاس بیندازد.",
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
    )
    try:
        await context.bot.send_message(
            chat_id=uid,
            text="🎡 گردونه شانس شما توسط مدیریت ریست شد.\nالان می‌توانید دوباره امتحان کنید!"
        )
    except:
        pass
    return ConversationHandler.END


# ---------- ریست اکانت تست ----------
async def reset_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "🧪 آیدی عددی کاربری که می‌خواهید اکانت تستش مجدد شارژ شود را وارد کنید:"
    )
    return WAITING_RESET_TEST_ID


async def reset_test_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        uid = int(update.message.text.strip())
    except Exception:
        await update.message.reply_text("❌ آیدی نامعتبر است. دوباره وارد کنید:")
        return WAITING_RESET_TEST_ID

    user = get_user(uid)
    if not user:
        await update.message.reply_text("❌ کاربری با این آیدی یافت نشد. دوباره وارد کنید:")
        return WAITING_RESET_TEST_ID

    reset_test(uid)
    name = user[2] or "کاربر"
    await update.message.reply_text(
        f"✅ اکانت تست کاربر *{name}* (`{uid}`) شارژ مجدد شد.\n"
        f"الان می‌تواند دوباره اکانت تست بگیرد.",
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
    )
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(
                "🧪 اکانت تست شما توسط مدیریت شارژ مجدد شد.\n"
                "الان می‌توانید دوباره از دکمه «🧪 اکانت تست» استفاده کنید!"
            )
        )
    except Exception:
        pass
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    kb = admin_keyboard() if uid == ADMIN_ID else main_keyboard(uid)
    await update.message.reply_text("لغو شد.", reply_markup=kb)
    return ConversationHandler.END


# ================== اصلی ==================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🔍 جستجوی آیدی کاربر$") & filters.User(ADMIN_ID), search_user_start),
            MessageHandler(filters.Regex("^📊 آمار کاربر$") & filters.User(ADMIN_ID), search_user_start),
            MessageHandler(filters.Regex("^🗑 حذف کاربر از ربات$") & filters.User(ADMIN_ID), delete_user_start),
            MessageHandler(filters.Regex("^✅ رفع مسدودیت کاربر$") & filters.User(ADMIN_ID), unblock_user_start),
            MessageHandler(filters.Regex("^🎁 ساخت کد هدیه$") & filters.User(ADMIN_ID), create_gift_start),
            MessageHandler(filters.Regex("^📢 پیام به کاربران ربات$") & filters.User(ADMIN_ID), broadcast_start),
            MessageHandler(filters.Regex("^✉️ پیام به کاربر دلخواه$") & filters.User(ADMIN_ID), specific_msg_start),
            MessageHandler(filters.Regex("^🎁 امتیاز به همه کاربران$") & filters.User(ADMIN_ID), admin_gift_all_start),
            MessageHandler(filters.Regex("^🎁 امتیاز به کاربر دلخواه$") & filters.User(ADMIN_ID), admin_gift_one_start),
            MessageHandler(filters.Regex("^➖ کسر امتیاز از کاربر$") & filters.User(ADMIN_ID), deduct_one_start),
            MessageHandler(filters.Regex("^➖ کسر امتیاز از تمامی کاربران$") & filters.User(ADMIN_ID), deduct_all_start),
            MessageHandler(filters.Regex("^⚠️ اخطار دهی$") & filters.User(ADMIN_ID), warning_start),
            MessageHandler(filters.Regex("^🎡 گردونه شانس مجدد$") & filters.User(ADMIN_ID), reset_wheel_start),
            MessageHandler(filters.Regex("^🧪 اکانت تست مجدد$") & filters.User(ADMIN_ID), reset_test_start),
            CallbackQueryHandler(services_confirm_entry, pattern="^svc_confirm_"),
            CallbackQueryHandler(confirm_config, pattern="^config_"),
            MessageHandler(filters.Regex("^🧪 اکانت تست$"), ask_username_for_test),
            MessageHandler(filters.Regex("^🎁 کد هدیه$"), gift_code_start),
            MessageHandler(filters.Regex("^💸 انتقال امتیاز$"), transfer_start),
        ],
        states={
            WAITING_SEARCH_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_user)],
            WAITING_DELETE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_user)],
            WAITING_UNBLOCK_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, unblock_user_process)],
            WAITING_CREATE_GIFT_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_gift_points)],
            WAITING_CREATE_GIFT_USES: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_gift_uses)],
            WAITING_CREATE_GIFT_EXPIRES: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_gift_expires)],
            WAITING_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_process)],
            WAITING_SPECIFIC_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, specific_msg_id)],
            WAITING_SPECIFIC_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, specific_msg_send)],
            WAITING_GIFT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, gift_code_process)],
            WAITING_TRANSFER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_id)],
            WAITING_TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_amount)],
            WAITING_ADMIN_GIFT_ALL_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_all_points)],
            WAITING_ADMIN_GIFT_ALL_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_all_desc),
                CallbackQueryHandler(admin_gift_all_skip, pattern="^admin_gift_all_skip$")
            ],
            WAITING_ADMIN_GIFT_ONE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_one_id)],
            WAITING_ADMIN_GIFT_ONE_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_one_points)],
            WAITING_ADMIN_GIFT_ONE_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_one_desc),
                CallbackQueryHandler(admin_gift_one_skip, pattern="^admin_gift_one_skip$")
            ],
            WAITING_DEDUCT_ONE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, deduct_one_id)],
            WAITING_DEDUCT_ONE_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, deduct_one_amount),
                CallbackQueryHandler(deduct_one_all, pattern="^deduct_one_all$")
            ],
            WAITING_DEDUCT_ALL_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, deduct_all_amount),
                CallbackQueryHandler(deduct_all_zero, pattern="^deduct_all_zero$")
            ],
            WAITING_WARNING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, warning_id)],
            WAITING_WARNING_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, warning_desc),
                CallbackQueryHandler(warning_skip, pattern="^warning_skip$")
            ],
            WAITING_RESET_WHEEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, reset_wheel_process)],
            WAITING_RESET_TEST_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, reset_test_process)],
            WAITING_DISABLE_SERVICE_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, disable_service_desc),
                CallbackQueryHandler(disable_service_skip, pattern="^svc_disable_skip$")
            ],
            WAITING_CONFIG_DURATION: [
                CallbackQueryHandler(config_duration_callback, pattern="^time_"),
                CallbackQueryHandler(service_username_cancel, pattern="^username_cancel$"),
            ],
            WAITING_SERVICE_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, service_username_text),
                CallbackQueryHandler(service_username_auto, pattern="^username_auto$"),
                CallbackQueryHandler(service_username_cancel, pattern="^username_cancel$"),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^🔙 بازگشت$"), cancel),
            CommandHandler("cancel", cancel),
        ],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
    app.add_handler(CallbackQueryHandler(users_page_callback, pattern="^users_page_|^users_close$"))
    app.add_handler(CallbackQueryHandler(wheel_callback, pattern="^spin_wheel$|^wheel_cancel$"))
    app.add_handler(CallbackQueryHandler(gift_broadcast_callback, pattern="^gift_broadcast_"))
    app.add_handler(CallbackQueryHandler(services_callback, pattern="^svc_(page_|select_|close|cancel_confirm)"))
    app.add_handler(CallbackQueryHandler(
        service_info_callback,
        pattern="^svcinfo_|^svc_get_qr$|^svc_install_guide$|^svc_back_main$"
    ))

    app.add_handler(MessageHandler(filters.Regex("^🎁 دریافت کانفینگ رایگان$"), get_config))
    app.add_handler(MessageHandler(filters.Regex("^👥 زیرمجموعه گیری$"), referral))
    app.add_handler(MessageHandler(filters.Regex("^👤 حساب کاربری$"), account))
    app.add_handler(MessageHandler(filters.Regex("^📜 تاریخچه امتیاز$"), points_history_handler))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ راهنما$"), help_guide))
    app.add_handler(MessageHandler(filters.Regex("^🏆 جدول رتبه‌بندی$"), leaderboard))
    app.add_handler(MessageHandler(filters.Regex("^📅 جایزه روزانه$"), daily_reward))
    app.add_handler(MessageHandler(filters.Regex("^🎡 گردونه شانس$"), wheel_start))
    app.add_handler(MessageHandler(filters.Regex("^📞 پشتیبانی$"), support))
    app.add_handler(MessageHandler(filters.Regex("^🛠 پنل مدیریت$") & filters.User(ADMIN_ID), admin_panel))
    app.add_handler(MessageHandler(filters.Regex("^📊 آمار کلی ربات$") & filters.User(ADMIN_ID), bot_stats))
    app.add_handler(MessageHandler(filters.Regex("^📋 نمایش تمام کاربران$") & filters.User(ADMIN_ID), show_all_users_start))
    app.add_handler(MessageHandler(filters.Regex("^🔌 قطع سرویس$") & filters.User(ADMIN_ID), disable_service_start))
    app.add_handler(MessageHandler(filters.Regex("^🔙 بازگشت$") & filters.User(ADMIN_ID), back_to_main))

    app.add_handler(conv_handler)

    # چک عضویت دوره‌ای هر ۱ ساعت
    if app.job_queue:
        app.job_queue.run_repeating(periodic_membership_check, interval=3600, first=60)
        print("JobQueue فعال شد — چک عضویت هر ۱ ساعت")
    else:
        print("⚠️ JobQueue در دسترس نیست. برای چک دوره‌ای نصب کنید: pip install \"python-telegram-bot[job-queue]\"")

    print("ربات روشن شد...")
    app.run_polling()


if __name__ == "__main__":
    main()
