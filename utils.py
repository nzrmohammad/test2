import re
from datetime import datetime
from typing import Union, Optional
import pytz
import json
import logging
import jdatetime

from config import EMOJIS, PROGRESS_COLORS

logger = logging.getLogger(__name__)
bot = None

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")

def format_raw_datetime(dt_obj: Optional[datetime]) -> str:
    if isinstance(dt_obj, datetime):
        return dt_obj.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(dt_obj, str) and dt_obj:
        return dt_obj
    return "هرگز"

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
            logger.error(f"Safe edit failed: {e}")
        else:
            pass

def escape_markdown(text: Union[str, int, float]) -> str:
    text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

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
    
    filled_bar = '█' * filled_count
    empty_bar = '░' * (length - filled_count)
    
    escaped_percent_str = escape_markdown(f"{percent:.1f}%")
    
    return f"`{filled_bar}{empty_bar} {escaped_percent_str}`"

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

def format_shamsi_tehran(dt_obj: Optional[datetime]) -> str:
    if not isinstance(dt_obj, datetime):
        return "هرگز"

    tehran_tz = pytz.timezone("Asia/Tehran")
    if dt_obj.tzinfo is None:
        dt_obj = pytz.utc.localize(dt_obj)
    tehran_dt = dt_obj.astimezone(tehran_tz)
    j_date = jdatetime.datetime.fromgregorian(datetime=tehran_dt)
    
    return j_date.strftime('%Y/%m/%d %H:%M:%S')

def parse_volume_string(volume_str: str) -> int:
    if not isinstance(volume_str, str):
        return 0
    numbers = re.findall(r'\d+', volume_str)
    if numbers:
        return int(numbers[0])
    return 0

def gregorian_to_shamsi_str(gregorian_date: Optional[datetime.date]) -> str:
    """Converts a gregorian date object to a Shamsi date string (YYYY/MM/DD)."""
    if not isinstance(gregorian_date, (datetime, jdatetime.date)):
         # If it's a date object, convert to datetime first
        if isinstance(gregorian_date, jdatetime.date):
            gregorian_date = gregorian_date.togregorian()
        try:
            gregorian_date = datetime.combine(gregorian_date, datetime.min.time())
        except (TypeError, AttributeError):
            return "نامشخص"

    if not gregorian_date:
        return "نامشخص"
        
    j_date = jdatetime.datetime.fromgregorian(datetime=gregorian_date)
    return j_date.strftime('%Y/%m/%d')