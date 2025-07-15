import re
from datetime import datetime
from typing import Union, Optional
import pytz
from config import EMOJIS, PROGRESS_COLORS
import jdatetime
import json
import logging


logger = logging.getLogger(__name__)
bot = None

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")

def initialize_utils(b_instance):
    """Initializes the bot instance for utility functions."""
    global bot
    bot = b_instance

def validate_uuid(uuid_str: str) -> bool:
    """Validates if a string matches the UUID format."""
    return bool(_UUID_RE.match(uuid_str.strip())) if uuid_str else False

def _safe_edit(chat_id: int, msg_id: int, text: str, **kwargs):
    """A safe version of edit_message_text that handles common errors."""
    if not bot:
        logger.error("Util's bot instance is not initialized!")
        return
    try:
        # Set MarkdownV2 as default, but allow it to be overridden (e.g., with None or HTML)
        kwargs.setdefault('parse_mode', 'MarkdownV2')
        
        bot.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=msg_id,
            **kwargs
        )
    except Exception as e:
        # Ignore errors for messages that are not found or not modified
        if 'message not found' in str(e) or 'message is not modified' in str(e):
            pass
        else:
            log_adapter = logging.LoggerAdapter(logger, {'user_id': chat_id})
            log_adapter.error(f"Safe edit failed with an unexpected error: {e}")

def safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def create_progress_bar(percent: float, length: int = 15) -> str:
    percent = max(0, min(100, percent))
    filled_count = int(percent / 100 * length)
    
    if percent >= 90: color = PROGRESS_COLORS["critical"]
    elif percent >= 75: color = PROGRESS_COLORS["danger"]
    elif percent >= 50: color = PROGRESS_COLORS["warning"]
    else: color = PROGRESS_COLORS["safe"]
    
    filled_bar = '█' * filled_count
    empty_bar = '░' * (length - filled_count)
    
    escaped_percent = escape_markdown(f"{percent:.1f}")

    return f"{color} `[{filled_bar}{empty_bar}] {escaped_percent}%`"

def persian_date(dt: Optional[datetime]) -> str:
    """
    Converts a timezone-aware datetime object to a Persian-formatted date string.
    The input datetime is expected to have timezone info.
    """
    if not isinstance(dt, datetime):
        return "نامشخص"
    
    tehran_tz = pytz.timezone("Asia/Tehran")
    dt_tehran = dt.astimezone(tehran_tz)
    
    return dt_tehran.strftime("%Y/%m/%d - %H:%M")

def format_daily_usage(gb: float) -> str:
    """Formats daily usage, showing MB if usage is less than 1 GB."""
    if gb < 0: return "0 MB"
    if gb < 1:
        return f"{gb * 1024:.0f} MB"
    return f"{gb:.2f} GB"
    
def escape_markdown(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def shamsi_to_gregorian(shamsi_str: str) -> Optional[datetime.date]:
    """Converts a Shamsi date string (YYYY/MM/DD) to a Gregorian date object."""
    try:
        year, month, day = map(int, shamsi_str.split('/'))
        return jdatetime.date(year, month, day).togregorian()
    except (ValueError, TypeError):
        return None
    
def format_relative_time(dt: Optional[datetime]) -> str:
    """Formats a datetime object into a relative time string like '5 days ago'."""
    if not dt:
        return "Unknown"
    
    now = datetime.now(pytz.utc)
    diff = now - dt.astimezone(pytz.utc)
    
    days = diff.days
    seconds = diff.seconds

    if days > 365:
        years = days // 365
        return f"{years} year{'s' if years > 1 else ''} ago"
    if days > 30:
        months = days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    if days > 0:
        return f"{days} day{'s' if days > 1 else ''} ago"
    if seconds > 3600:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    if seconds > 60:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    return "just now"

def load_service_plans():
    """پلن‌های سرویس را از فایل plans.json می‌خواند."""
    try:
        # فایل را باز کرده و محتوای آن را با json.load می‌خوانیم
        with open('plans.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # اگر فایل پیدا نشد، یک لاگ هشدار ثبت کرده و لیست خالی برمی‌گردانیم
        logger.warning("plans.json not found. Service plans will be empty.")
        return []
    except json.JSONDecodeError:
        # اگر محتوای فایل ساختار JSON صحیحی نداشت، خطا ثبت کرده و لیست خالی برمی‌گردانیم
        logger.error("Could not decode plans.json. Please check its format is valid.")
        return []

def load_custom_links():
    try:
        with open('custom_links.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {} # اگر فایل وجود نداشت، یک دیکشنری خالی برگردان
    except json.JSONDecodeError:
        return {} # اگر فایل خراب بود، باز هم دیکشنری خالی برگردان