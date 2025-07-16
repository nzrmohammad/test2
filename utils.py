import re
from datetime import datetime, date
from typing import Union, Optional
import pytz
import jdatetime
import json
import logging

from config import EMOJIS, PROGRESS_COLORS

logger = logging.getLogger(__name__)
bot = None

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")

def format_datetime_for_user(dt_obj: Optional[datetime]) -> str:
    """
    THE FINAL, CORRECT, AND ONLY FUNCTION FOR DATETIME FORMATTING.
    Converts a datetime object to a Shamsi date and Tehran time string.
    """
    if not isinstance(dt_obj, datetime):
        return "هرگز"

    # Step 1: Assume the incoming datetime is UTC. If it's naive, localize it.
    if dt_obj.tzinfo is None:
        dt_obj = pytz.utc.localize(dt_obj)
    
    # Step 2: Convert the UTC time to 'Asia/Tehran' timezone.
    tehran_tz = pytz.timezone('Asia/Tehran')
    tehran_dt = dt_obj.astimezone(tehran_tz)
    
    # Step 3: Convert the Gregorian date part to Shamsi.
    shamsi_date = jdatetime.date.fromgregorian(date=tehran_dt)
    
    # Step 4: Format the output string using the CORRECT Tehran-converted parts.
    return f"{shamsi_date.strftime('%Y/%m/%d')} - {tehran_dt.strftime('%H:%M')}"

def initialize_utils(b_instance):
    global bot
    bot = b_instance

def validate_uuid(uuid_str: str) -> bool:
    return bool(_UUID_RE.match(uuid_str.strip())) if uuid_str else False

def _safe_edit(chat_id: int, msg_id: int, text: str, **kwargs):
    if not bot: return
    try:
        kwargs.setdefault('parse_mode', 'MarkdownV2')
        bot.edit_message_text(text=text, chat_id=chat_id, message_id=msg_id, **kwargs)
    except Exception as e:
        if 'message not found' not in str(e) and 'message is not modified' not in str(e):
            pass
        else:
            logger.error(f"Safe edit failed: {e}")

def escape_markdown(text: Union[str, int, float]) -> str:
    text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def shamsi_to_gregorian(shamsi_str: str) -> Optional[date]:
    try:
        year, month, day = map(int, shamsi_str.split('/'))
        return jdatetime.date(year, month, day).togregorian()
    except (ValueError, TypeError):
        return None

def format_relative_time(dt: Optional[datetime]) -> str:
    if not dt: return "Unknown"
    now = datetime.now(pytz.utc)
    if dt.tzinfo is None: dt = pytz.utc.localize(dt)
    diff = now - dt.astimezone(pytz.utc)
    days, seconds = diff.days, diff.seconds

    if days > 365: return f"{days // 365} year(s) ago"
    if days > 30: return f"{days // 30} month(s) ago"
    if days > 0: return f"{days} day(s) ago"
    if seconds > 3600: return f"{seconds // 3600} hour(s) ago"
    if seconds > 60: return f"{seconds // 60} minute(s) ago"
    return "just now"

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
    return f"{color} `{filled_bar}{empty_bar} {escaped_percent}%`"

def format_daily_usage(gb: float) -> str:
    if gb < 0: return "0 MB"
    if gb < 1: return f"{gb * 1024:.0f} MB"
    return f"{gb:.2f} GB"

def load_service_plans():
    try:
        with open('plans.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception: return []

def load_custom_links():
    try:
        with open('custom_sub_links.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception: return {}