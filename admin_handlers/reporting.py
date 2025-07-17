# admin_handlers/reporting.py

import logging
from datetime import datetime, timedelta
import pytz
from telebot import types

# FIX: واردات مطلق
from hiddify_api_handler import hiddify_handler
from marzban_api_handler import marzban_handler
from database import db
from menu import menu
from admin_formatters import (
    fmt_users_list, fmt_panel_users_list, fmt_online_users_list,
    fmt_top_consumers, fmt_bot_users_list, fmt_birthdays_list,
    fmt_hiddify_panel_info, fmt_marzban_system_stats
)
from utils import _safe_edit

logger = logging.getLogger(__name__)
bot = None

def initialize_reporting_handlers(b):
    global bot
    bot = b

# FIX: آندرلاین از نام توابع عمومی حذف شد
def handle_reports_menu(call, params):
    panel = params[0]
    panel_name = "آلمان 🇩🇪" if panel == "hiddify" else "فرانسه 🇫🇷"
    _safe_edit(call.from_user.id, call.message.message_id, f"📜 *گزارش‌گیری پنل {panel_name}*", reply_markup=menu.admin_reports_menu(panel))

def handle_analytics_menu(call, params):
    panel = params[0]
    panel_name = "آلمان 🇩🇪" if panel == "hiddify" else "فرانسه 🇫🇷"
    _safe_edit(call.from_user.id, call.message.message_id, f"📊 *تحلیل و آمار پنل {panel_name}*", reply_markup=menu.admin_analytics_menu(panel))

def handle_health_check(call, params):
    bot.answer_callback_query(call.id, "در حال دریافت اطلاعات پنل...")
    info = hiddify_handler.get_panel_info()
    text = fmt_hiddify_panel_info(info) if info else "❌ اطلاعاتی دریافت نشد."
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:analytics_menu:hiddify"))
    _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb)

def handle_marzban_system_stats(call, params):
    bot.answer_callback_query(call.id, "در حال دریافت آمار سیستم مرزبان...")
    stats = marzban_handler.get_system_stats()
    text = fmt_marzban_system_stats(stats) if stats else "❌ اطلاعاتی دریافت نشد."
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:analytics_menu:marzban"))
    _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb)

def handle_paginated_list(call, params):
    # --- UX IMPROVEMENT: Show a loading message before slow API calls ---
    list_type, panel, page = params[0], params[1] if len(params) > 2 else None, int(params[-1])
    
    # Show loading message only for panel-related lists that require an API call
    if panel:
        _safe_edit(call.from_user.id, call.message.message_id, "⏳ در حال دریافت اطلاعات از پنل، لطفاً صبر کنید...", reply_markup=None, parse_mode=None)

    users, all_panel_users = [], []
    if panel == 'hiddify': all_panel_users = hiddify_handler.get_all_users()
    elif panel == 'marzban': all_panel_users = marzban_handler.get_all_users()
    
    if list_type == "panel_users": users = all_panel_users
    elif list_type == "online_users":
        deadline = datetime.now(pytz.utc) - timedelta(minutes=3)
        users = [u for u in all_panel_users if u.get('is_active') and u.get('last_online') and u['last_online'].astimezone(pytz.utc) >= deadline]
    elif list_type == "active_users":
        deadline = datetime.now(pytz.utc) - timedelta(days=1)
        users = [u for u in all_panel_users if u.get('last_online') and u['last_online'].astimezone(pytz.utc) >= deadline]
    elif list_type == "inactive_users":
        now_utc = datetime.now(pytz.utc)
        users = [u for u in all_panel_users if u.get('last_online') and 1 <= (now_utc - u['last_online'].astimezone(pytz.utc)).days < 7]
    elif list_type == "never_connected": users = [u for u in all_panel_users if not u.get('last_online')]
    elif list_type == "top_consumers": users = sorted(all_panel_users, key=lambda u: u.get('current_usage_GB', 0), reverse=True)
    elif list_type == "bot_users": users = db.get_all_bot_users()
    elif list_type == "birthdays": users = db.get_users_with_birthdays()
    
    list_configs = {
        "panel_users": {"format": lambda u, pg, p: fmt_panel_users_list(u, "آلمان 🇩🇪" if p == "hiddify" else "فرانسه 🇫🇷", pg), "back": "manage_panel"},
        "online_users": {"format": fmt_online_users_list, "back": "reports_menu"},
        "active_users": {"format": lambda u, pg, p: fmt_users_list(u, 'active', pg), "back": "reports_menu"},
        "inactive_users": {"format": lambda u, pg, p: fmt_users_list(u, 'inactive', pg), "back": "reports_menu"},
        "never_connected": {"format": lambda u, pg, p: fmt_users_list(u, 'never_connected', pg), "back": "reports_menu"},
        "top_consumers": {"format": fmt_top_consumers, "back": "analytics_menu"},
        "bot_users": {"format": fmt_bot_users_list, "back": "management_menu"},
        "birthdays": {"format": fmt_birthdays_list, "back": "panel"},
    }
    
    config = list_configs.get(list_type)
    if not config: return
    try: text = config["format"](users, page, panel)
    except TypeError: text = config["format"](users, page)
    
    base_cb = f"admin:list:{list_type}" + (f":{panel}" if panel else "")
    back_cb = f"admin:{config['back']}" + (f":{panel}" if panel and config['back'] not in ['management_menu', 'panel'] else "")
    kb = menu.create_pagination_menu(base_cb, page, len(users), back_cb)
    _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb)

