import logging
import threading
import time
from datetime import datetime
import schedule
import pytz
from telebot import apihelper, TeleBot
from config import (DAILY_REPORT_TIME, TEHRAN_TZ, ADMIN_IDS,BIRTHDAY_GIFT_GB, BIRTHDAY_GIFT_DAYS, NOTIFY_ADMIN_ON_USAGE,
                     WARNING_USAGE_THRESHOLD,WARNING_DAYS_BEFORE_EXPIRY,
                     USAGE_WARNING_CHECK_HOURS, ONLINE_REPORT_UPDATE_HOURS, EMOJIS)
from database import db
import combined_handler
from utils import escape_markdown
from menu import menu
from admin_formatters import fmt_admin_report, fmt_online_users_list
from user_formatters import fmt_user_report

logger = logging.getLogger(__name__)

class SchedulerManager:
    def __init__(self, bot: TeleBot) -> None:
        self.bot = bot  # ذخیره نمونه bot
        self.running = False
        self.tz = pytz.timezone(TEHRAN_TZ) if isinstance(TEHRAN_TZ, str) else TEHRAN_TZ
        self.tz_str = str(self.tz)

    def _hourly_snapshots(self) -> None:
        """Takes a usage snapshot for all active UUIDs every hour."""
        logger.info("Scheduler: Running hourly usage snapshot job.")
        
        all_users_info = combined_handler.get_all_users_combined() # (این تابع را در combined_handler پیاده‌سازی کنید)
        if not all_users_info:
            return
            
        user_info_map = {user['uuid']: user for user in all_users_info}

        all_uuids_from_db = db.all_active_uuids()
        if not all_uuids_from_db:
            return

        for u_row in all_uuids_from_db:
            try:
                uuid_str = u_row['uuid']
                if uuid_str in user_info_map:
                    info = user_info_map[uuid_str]
                    
                    # --- شروع تغییر اصلی ---
                    # اطلاعات مصرف تفکیکی را از ساختار breakdown می‌خوانیم
                    breakdown = info.get('breakdown', {})
                    h_usage = breakdown.get('hiddify', {}).get('usage', 0.0)
                    m_usage = breakdown.get('marzban', {}).get('usage', 0.0)
                    
                    # ذخیره اطلاعات تفکیکی در دیتابیس
                    db.add_usage_snapshot(u_row['id'], h_usage, m_usage)
                    # --- پایان تغییر اصلی ---

            except Exception as e:
                logger.error(f"Scheduler: Failed to process snapshot for uuid_id {u_row['id']}: {e}")

    def _check_for_warnings(self) -> None:
        """Checks for low data and expiring accounts and warns users."""
        logger.info("Scheduler: Running warnings check job.")
        
        all_uuids = db.all_active_uuids()
        if not all_uuids:
            return

        all_users_info_map = {u['uuid']: u for u in api_handler.get_all_users()}
        
        for u_row in all_uuids:
            uuid_str = u_row['uuid']
            uuid_id = u_row['id']
            user_id = u_row['user_id']
            
            info = all_users_info_map.get(uuid_str)
            if not info:
                continue

            user_settings = db.get_user_settings(user_id)
            
            # ۱. بررسی هشدار انقضا
            if user_settings.get('expiry_warnings'):
                expire_days = info.get('expire')
                if expire_days is not None and 0 <= expire_days <= WARNING_DAYS_BEFORE_EXPIRY:
                    if not db.has_recent_warning(uuid_id, 'expiry'):
                        user_name = escape_markdown(info.get('name', 'کاربر ناشناس'))
                        msg = (f"{EMOJIS['warning']} *هشدار انقضای اکانت*\n\n"
                               f"اکانت *{user_name}* شما تا *{expire_days}* روز دیگر منقضی می‌شود\\.")
                        try:
                            self.bot.send_message(user_id, msg, parse_mode="MarkdownV2")
                            db.log_warning(uuid_id, 'expiry')
                        except Exception as e:
                            logger.error(f"Failed to send expiry warning to user {user_id}: {e}")


            # ۲. بررسی هشدار حجم به تفکیک سرور
            breakdown = info.get('breakdown', {})
            server_map = {
                'hiddify': {'name': 'آلمان 🇩🇪', 'setting': 'data_warning_hiddify'},
                'marzban': {'name': 'فرانسه 🇫🇷', 'setting': 'data_warning_marzban'}
            }

            for code, details in server_map.items():
                if user_settings.get(details['setting']) and code in breakdown:
                    server_info = breakdown[code]
                    limit = server_info.get('limit', 0.0)
                    usage = server_info.get('usage', 0.0)
                    
                    if limit > 0:
                        remaining_gb = max(0, limit - usage)
                        remaining_percent = (remaining_gb / limit) * 100
                        
                        warning_type = f'low_data_{code}'
                        # اگر کمتر از ۲۰ درصد باقی مانده بود
                        if 0 < remaining_percent <= 20:
                            if not db.has_recent_warning(uuid_id, warning_type):
                                user_name = escape_markdown(info.get('name', 'کاربر ناشناس'))
                                server_name = details['name']
                                msg = (f"{EMOJIS['warning']} *هشدار اتمام حجم*\n\n"
                                       f"کاربر گرامی، حجم اکانت *{user_name}* شما در سرور *{server_name}* رو به اتمام است\\.\n"
                                       f"\\- حجم باقیمانده: *{remaining_gb:.2f} GB*")
                                try:
                                    self.bot.send_message(user_id, msg, parse_mode="MarkdownV2")
                                    db.log_warning(uuid_id, warning_type)
                                except Exception as e:
                                    logger.error(f"Failed to send data warning to user {user_id}: {e}")

    def _nightly_report(self) -> None:
        now = datetime.now(self.tz)
        now_str = now.strftime("%Y/%m/%d - %H:%M")
        logger.info(f"Scheduler: Running nightly reports at {now_str}")

        all_users_info_from_api = api_handler.get_all_users()
        if not all_users_info_from_api:
            logger.warning("Scheduler: Could not fetch user info from API for nightly report.")
            return
            
        user_info_map = {user['uuid']: user for user in all_users_info_from_api}
        all_bot_users = db.get_all_user_ids()
        separator = '\n' + '\\-' * 25 + '\n'

        for user_id in all_bot_users:
            user_settings = db.get_user_settings(user_id)
            if not user_settings.get('daily_reports', True):
                continue
            report_text, header = "", ""
            user_uuids_from_db = db.uuids(user_id)
            user_infos_for_report = []
            if user_uuids_from_db:
                for u_row in user_uuids_from_db:
                    if u_row['uuid'] in user_info_map:
                        user_data = user_info_map[u_row['uuid']]
                        user_data['db_id'] = u_row['id'] 
                        user_infos_for_report.append(user_data)

            try:
                if user_id in ADMIN_IDS:
                    header = f"👑 *گزارش جامع ادمین* \\- {escape_markdown(now_str)}{separator}"
                    report_text = fmt_admin_report(all_users_info_from_api, db)
                elif user_infos_for_report:
                    header = f"🌙 *گزارش روزانه شما* \\- {escape_markdown(now_str)}{separator}"
                    report_text = fmt_user_report(user_infos_for_report)

                if report_text:
                    self.bot.send_message(user_id, header + report_text, parse_mode="MarkdownV2")
                    time.sleep(0.5)
                
                if user_infos_for_report:
                    for info in user_infos_for_report:
                        db.delete_user_snapshots(info['db_id'])
                    logger.info(f"Scheduler: Cleaned up daily snapshots for user {user_id}.")
                    
            except Exception as e:
                logger.error(f"Scheduler: Failed to send nightly report or cleanup for user {user_id}: {e}")
                continue

    def _update_online_reports(self) -> None:
        """Scheduled job to update the online users report message every 3 hours."""
        logger.info("Scheduler: Running 3-hourly online user report update.")
        
        messages_to_update = db.get_scheduled_messages('online_users_report')
        
        for msg_info in messages_to_update:
            try:
                chat_id = msg_info['chat_id']
                message_id = msg_info['message_id']
                
                online_list = api_handler.online_users()
                for user in online_list:
                    user['daily_usage_GB'] = db.get_usage_since_midnight_by_uuid(user['uuid'])
                
                text = fmt_online_users_list(online_list, 0)
                kb = menu.create_pagination_menu("admin_online", 0, len(online_list))
                
                self.bot.edit_message_text(text, chat_id, message_id, reply_markup=kb, parse_mode="MarkdownV2")
                time.sleep(0.5)
            except apihelper.ApiTelegramException as e:
                if 'message to edit not found' in str(e) or 'message is not modified' in str(e):
                    db.delete_scheduled_message(msg_info['id'])
                else:
                    logger.error(f"Scheduler: Failed to update online report for chat {chat_id}: {e}")
            except Exception as e:
                logger.error(f"Scheduler: Generic error updating online report for chat {chat_id}: {e}")

    def _birthday_gifts_job(self) -> None:
        """Checks for users' birthdays and sends them a gift."""
        logger.info("Scheduler: Running daily birthday gift job.")
        today_birthday_users = db.get_todays_birthdays()
        
        if not today_birthday_users:
            logger.info("Scheduler: No birthdays today.")
            return

        for user_id in today_birthday_users:
            user_uuids = db.uuids(user_id)
            if not user_uuids:
                continue
            
            gift_applied = False
            for row in user_uuids:
                uuid = row['uuid']
                # ✅ [FIXED] فراخوانی مستقیم api_handler به جای self.api_handler
                if api_handler.modify_user(uuid, add_usage_gb=BIRTHDAY_GIFT_GB, add_days=BIRTHDAY_GIFT_DAYS):
                    gift_applied = True
            
            if gift_applied:
                try:
                    gift_message = (
                        f"🎉 *تولدت مبارک\\!* 🎉\n\n"
                        f"امیدواریم سالی پر از شادی و موفقیت پیش رو داشته باشی\\.\n"
                        f"ما به همین مناسبت، هدیه‌ای برای شما فعال کردیم:\n\n"
                        f"🎁 `{BIRTHDAY_GIFT_GB} GB` حجم و `{BIRTHDAY_GIFT_DAYS}` روز به تمام اکانت‌های شما **به صورت خودکار اضافه شد\\!**\n\n"
                        f"می‌توانی با مراجعه به بخش مدیریت اکانت، جزئیات جدید را مشاهده کنی\\."
                    )
                    self.bot.send_message(user_id, gift_message, parse_mode="MarkdownV2")
                    logger.info(f"Scheduler: Sent birthday gift to user {user_id}.")
                except Exception as e:
                    logger.error(f"Scheduler: Failed to send birthday message to user {user_id}: {e}")

    def _run_monthly_vacuum(self) -> None:
        """A scheduled job to run the VACUUM command on the database."""
        today = datetime.now(self.tz)
        if today.day == 1:
            logger.info("Scheduler: It's the first of the month, running database VACUUM job.")
            try:
                db.vacuum_db()
                logger.info("Scheduler: Database VACUUM completed successfully.")
            except Exception as e:
                logger.error(f"Scheduler: Database VACUUM failed: {e}")

    def start(self) -> None:
        if self.running: return
        
        report_time_str = DAILY_REPORT_TIME.strftime("%H:%M")
        schedule.every().hour.at(":01").do(self._hourly_snapshots)
        schedule.every(4).hours.do(self._check_for_warnings)
        schedule.every().day.at("11:59", self.tz_str).do(self._nightly_report)
        schedule.every().day.at(report_time_str, self.tz_str).do(self._nightly_report)
        schedule.every(ONLINE_REPORT_UPDATE_HOURS).hours.do(self._update_online_reports)
        schedule.every().day.at("00:05", self.tz_str).do(self._birthday_gifts_job)
        schedule.every().day.at("04:00").do(self._run_monthly_vacuum)
        
        self.running = True
        threading.Thread(target=self._runner, daemon=True).start()
        logger.info(f"Scheduler started. Nightly report at {report_time_str} ({self.tz_str}). Online user reports will update every 3 hours && Birthday gift job scheduled for 00:05 ({self.tz_str}")

    def shutdown(self) -> None:
        logger.info("Scheduler: Shutting down...")
        schedule.clear()
        self.running = False

    def _runner(self) -> None:
        while self.running:
            try:
                schedule.run_pending()
            except Exception as exc:
                logger.error(f"Scheduler loop error: {exc}")
            time.sleep(60)