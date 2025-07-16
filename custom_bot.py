import logging
import sys
import signal
import time
from datetime import datetime
from telebot import TeleBot
from utils import initialize_utils
from config import LOG_LEVEL, LOG_FORMAT, ADMIN_IDS, BOT_TOKEN
from database import db
from api_handler2 import api_handler

from scheduler import SchedulerManager

from user_handlers import register_user_handlers
from admin_router import register_admin_handlers
from callback_router import register_callback_router

# ==================== بخش تنظیمات لاگ ====================

class UserIdFilter(logging.Filter):
    """A filter to add a default user_id to records that don't have one."""
    def filter(self, record):
        if not hasattr(record, 'user_id'):
            record.user_id = 'SYSTEM'  # Add a default value
        return True

LOG_FORMAT = "%(asctime)s — %(name)s — %(levelname)s — [User:%(user_id)s] — %(message)s"
DEFAULT_LOG_FORMAT = "%(asctime)s — %(name)s — %(levelname)s — %(message)s"

# گرفتن لاگر اصلی
root_logger = logging.getLogger()
root_logger.setLevel(LOG_LEVEL)

# پاک کردن هندلرهای قبلی
if root_logger.hasHandlers():
    root_logger.handlers.clear()

# ۱. ساخت هندلر برای فایل bot.log
info_handler = logging.FileHandler("bot.log", encoding="utf-8")
info_handler.setLevel(logging.INFO)
info_formatter = logging.Formatter(DEFAULT_LOG_FORMAT)
info_handler.setFormatter(info_formatter)

# ۲. ساخت هندلر برای فایل error.log
error_handler = logging.FileHandler("error.log", encoding="utf-8")
error_handler.setLevel(logging.ERROR)
error_formatter = logging.Formatter(LOG_FORMAT)
error_handler.setFormatter(error_formatter)
# 2. APPLY THE FILTER TO THE ERROR HANDLER
error_handler.addFilter(UserIdFilter())

# ۳. ساخت هندلر برای نمایش در کنسول
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(info_formatter)

# افزودن هندلرها به لاگر اصلی
root_logger.addHandler(info_handler)
root_logger.addHandler(error_handler)
root_logger.addHandler(stream_handler)


# لاگر اصلی این ماژول
logger = logging.getLogger(__name__)
# Create the single bot instance
bot = TeleBot(BOT_TOKEN, parse_mode=None)
initialize_utils(bot)
scheduler = SchedulerManager(bot)

def _notify_admins_start() -> None:
    """پس از ریاستارت ربات، یک پیام وضعیت برای ادمین‌ها بفرستد."""
    text = "🚀 ربات با موفقیت فعال شد"
    for aid in ADMIN_IDS:
        try:
            bot.send_message(aid, text, parse_mode=None)
        except Exception:
            continue

class HiddifyBot:
    """مدیر چرخهٔ حیات ربات"""

    def __init__(self) -> None:
        self.bot = bot
        self.running = False
        self.started_at: datetime | None = None
        signal.signal(signal.SIGINT, self._on_signal)
        signal.signal(signal.SIGTERM, self._on_signal)

    def _on_signal(self, signum, _frame):
        logger.info("Received signal %s → shutting down …", signum)
        self.shutdown()
        sys.exit(0)

    def start(self) -> None:
        if self.running:
            logger.warning("Bot already running")
            return
        try:
            logger.info("Registering handlers...")
            register_user_handlers(self.bot)
            register_admin_handlers(self.bot)
            register_callback_router(self.bot)
            logger.info("✅ Handlers registered")

            logger.info("Testing API connectivity …")
            if api_handler.test_connection():
                logger.info("✅ API reachable")
            else:
                logger.warning("⚠️ API unreachable")

            db.user(0)  # Test DB connection
            logger.info("✅ SQLite ready (users table reachable)")

            scheduler.start()
            logger.info("✅ Scheduler thread started")

            _notify_admins_start()

            self.running = True
            self.started_at = datetime.now()

            logger.info("🚀 Polling …")
            while self.running:
                try:
                    self.bot.infinity_polling(timeout=20, skip_pending=True)
                except Exception as e:
                    logger.error(f"FATAL ERROR: Bot polling failed: {e}", exc_info=True)
                    logger.info("Restarting polling in 15 seconds...")
                    time.sleep(15)

        except Exception as exc:
            logger.exception("Start-up failed: %s", exc)
            self.shutdown()
            raise

    def shutdown(self) -> None:
        if not self.running: return
        logger.info("Graceful shutdown …")
        self.running = False
        try:
            scheduler.shutdown()
            logger.info("Scheduler stopped")
            self.bot.stop_polling()
            logger.info("Telegram polling stopped")
            if self.started_at:
                logger.info("Uptime: %s", datetime.now() - self.started_at)
        finally:
            self.running = False
            logger.info("Shutdown complete")

if __name__ == "__main__":
    bot_instance = HiddifyBot()
    try:
        bot_instance.start()
    except Exception as e:
        logger.critical(f"Bot failed to start: {e}", exc_info=True)