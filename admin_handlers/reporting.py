import logging
from datetime import datetime, timedelta
import pytz
from telebot import types
import combined_handler
from hiddify_api_handler import hiddify_handler
from marzban_api_handler import marzban_handler
from database import db
from menu import menu
from admin_formatters import (
    fmt_users_list, fmt_panel_users_list, fmt_online_users_list,
    fmt_top_consumers, fmt_bot_users_list, fmt_birthdays_list,
    fmt_hiddify_panel_info, fmt_marzban_system_stats, fmt_users_by_plan_list,
    fmt_payments_report_list 
)
from utils import _safe_edit, load_service_plans, parse_volume_string, escape_markdown

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
    list_type, panel, page = params[0], params[1] if len(params) > 2 else None, int(params[-1])
    
    if panel:
        _safe_edit(call.from_user.id, call.message.message_id, "⏳ در حال دریافت اطلاعات از پنل، لطفاً صبر کنید...", reply_markup=None, parse_mode=None)

    users, all_panel_users = [], []
    if panel == 'hiddify': all_panel_users = hiddify_handler.get_all_users()
    elif panel == 'marzban': all_panel_users = marzban_handler.get_all_users()
    
    if list_type == "panel_users": 
        users = all_panel_users
    elif list_type == "online_users":
        deadline = datetime.now(pytz.utc) - timedelta(minutes=3)
        online_users = [u for u in all_panel_users if u.get('is_active') and isinstance(u.get('last_online'), datetime) and u['last_online'].astimezone(pytz.utc) >= deadline]
        for user in online_users:
            if user.get('uuid'):
                user['daily_usage_GB'] = sum(db.get_usage_since_midnight_by_uuid(user['uuid']).values())
            else:
                user['daily_usage_GB'] = 0
        users = online_users
    elif list_type == "active_users":
        deadline = datetime.now(pytz.utc) - timedelta(days=1)
        users = [u for u in all_panel_users if u.get('last_online') and u['last_online'].astimezone(pytz.utc) >= deadline]
    elif list_type == "inactive_users":
        now_utc = datetime.now(pytz.utc)
        users = [u for u in all_panel_users if u.get('last_online') and 1 <= (now_utc - u['last_online'].astimezone(pytz.utc)).days < 7]
    elif list_type == "never_connected": 
        users = [u for u in all_panel_users if not u.get('last_online')]
    elif list_type == "top_consumers":
        sorted_users = sorted(all_panel_users, key=lambda u: u.get('current_usage_GB', 0), reverse=True)
        users = sorted_users[:100]
    elif list_type == "bot_users": 
        users = db.get_all_bot_users()
    elif list_type == "birthdays": 
        users = db.get_users_with_birthdays()
    elif list_type == "payments":
        users = db.get_payment_history()

    list_configs = {
        "panel_users": {"format": lambda u, pg, p: fmt_panel_users_list(u, "آلمان 🇩🇪" if p == "hiddify" else "فرانسه 🇫🇷", pg), "back": "manage_panel"},
        "online_users": {"format": fmt_online_users_list, "back": "reports_menu"},
        "active_users": {"format": lambda u, pg, p: fmt_users_list(u, 'active', pg), "back": "reports_menu"},
        "inactive_users": {"format": lambda u, pg, p: fmt_users_list(u, 'inactive', pg), "back": "reports_menu"},
        "never_connected": {"format": lambda u, pg, p: fmt_users_list(u, 'never_connected', pg), "back": "reports_menu"},
        "top_consumers": {"format": fmt_top_consumers, "back": "analytics_menu"},
        "bot_users": {"format": fmt_bot_users_list, "back": "shared_tools_menu"},
        "birthdays": {"format": fmt_birthdays_list, "back": "shared_tools_menu"},
        "payments": {"format": fmt_payments_report_list, "back": "shared_tools_menu"},
    }
    
    config = list_configs.get(list_type)
    if not config: return
    try: text = config["format"](users, page, panel)
    except TypeError: text = config["format"](users, page)
    
    base_cb = f"admin:list:{list_type}" + (f":{panel}" if panel else "")
    back_cb = f"admin:{config['back']}" + (f":{panel}" if panel and config['back'] not in ['shared_tools_menu', 'panel'] else "")
    kb = menu.create_pagination_menu(base_cb, page, len(users), back_cb)
    _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb)

def handle_report_by_plan_selection(call, params):
    """منوی انتخاب پلن برای گزارش‌گیری را نمایش می‌دهد."""
    uid, msg_id = call.from_user.id, call.message.message_id
    prompt = "لطفاً پلنی که می‌خواهید کاربران آن را مشاهده کنید، انتخاب نمایید:"
    _safe_edit(uid, msg_id, prompt, reply_markup=menu.admin_select_plan_for_report_menu())


def handle_list_users_by_plan(call, params):
    """کاربران یک پلن خاص را لیست می‌کند."""
    plan_index, page = int(params[0]), int(params[1])
    uid, msg_id = call.from_user.id, call.message.message_id

    _safe_edit(uid, msg_id, "⏳ در حال دریافت اطلاعات و مقایسه با پلن، لطفاً صبر کنید...")

    all_plans = load_service_plans()
    if plan_index >= len(all_plans):
        _safe_edit(uid, msg_id, "❌ پلن انتخاب شده نامعتبر است.")
        return
        
    selected_plan = all_plans[plan_index]
    plan_duration = parse_volume_string(selected_plan.get('duration', '0'))
    plan_vol_de = parse_volume_string(selected_plan.get('volume_de', '0'))
    plan_vol_fr = parse_volume_string(selected_plan.get('volume_fr', '0'))

    all_users = combined_handler.get_all_users_combined()
    
    filtered_users = []
    for user in all_users:
        h_info = user.get('breakdown', {}).get('hiddify', {})
        m_info = user.get('breakdown', {}).get('marzban', {})
        
        user_vol_de = int(h_info.get('usage_limit_GB', -1))
        user_vol_fr = int(m_info.get('usage_limit_GB', -1))
        
        # تطبیق حجم و روز کاربر با پلن
        # (توجه: این مقایسه برای کاربرانی که در هر دو پنل هستند دقیق‌تر است)
        if (plan_vol_de == user_vol_de and plan_vol_fr == user_vol_fr):
             filtered_users.append(user)

    # استفاده از فرمت‌کننده موجود برای نمایش لیست
    # (می‌توان یک فرمت‌کننده جدید و اختصاصی هم برای این بخش ساخت)
    plan_name_escaped = escape_markdown(selected_plan.get('name', ''))
    text = fmt_panel_users_list(filtered_users, f"پلن {plan_name_escaped}", page)

    base_cb = f"admin:list_by_plan:{plan_index}"
    back_cb = "admin:report_by_plan_select"
    kb = menu.create_pagination_menu(base_cb, page, len(filtered_users), back_cb)
    _safe_edit(uid, msg_id, text, reply_markup=kb)


def handle_list_users_by_plan(call, params):
    plan_index, page = int(params[0]), int(params[1])
    uid, msg_id = call.from_user.id, call.message.message_id

    _safe_edit(uid, msg_id, "⏳ در حال دریافت اطلاعات و مقایسه با پلن، لطفاً صبر کنید...")

    all_plans = load_service_plans()
    if plan_index >= len(all_plans):
        _safe_edit(uid, msg_id, "❌ پلن انتخاب شده نامعتبر است.")
        return
        
    selected_plan = all_plans[plan_index]
    plan_vol_de = float(parse_volume_string(selected_plan.get('volume_de', '0')))
    plan_vol_fr = float(parse_volume_string(selected_plan.get('volume_fr', '0')))

    all_users = combined_handler.get_all_users_combined()
    
    filtered_users = []
    for user in all_users:
        h_info = user.get('breakdown', {}).get('hiddify', {})
        m_info = user.get('breakdown', {}).get('marzban', {})
        
        user_vol_de = h_info.get('usage_limit_GB', -1.0)
        user_vol_fr = m_info.get('usage_limit_GB', -1.0)

        if user_vol_de == plan_vol_de and user_vol_fr == plan_vol_fr:
             filtered_users.append(user)

    plan_name_raw = selected_plan.get('name', '')
    text = fmt_users_by_plan_list(filtered_users, plan_name_raw, page)

    base_cb = f"admin:list_by_plan:{plan_index}"
    back_cb = "admin:report_by_plan_select"
    kb = menu.create_pagination_menu(base_cb, page, len(filtered_users), back_cb)
    _safe_edit(uid, msg_id, text, reply_markup=kb)

    # **تغییر:** استفاده از فرمت‌کننده جدید
    plan_name_raw = selected_plan.get('name', '')
    text = fmt_users_by_plan_list(filtered_users, plan_name_raw, page)

    base_cb = f"admin:list_by_plan:{plan_index}"
    back_cb = "admin:report_by_plan_select"
    kb = menu.create_pagination_menu(base_cb, page, len(filtered_users), back_cb)
    _safe_edit(uid, msg_id, text, reply_markup=kb)

# این تابع جدید را به انتهای فایل اضافه کنید
def handle_list_users_no_plan(call, params):
    page = int(params[0])
    uid, msg_id = call.from_user.id, call.message.message_id

    _safe_edit(uid, msg_id, "⏳ در حال دریافت اطلاعات و مقایسه با پلن‌ها، لطفاً صبر کنید...")

    all_plans = load_service_plans()
    all_users = combined_handler.get_all_users_combined()
    
    plan_specs = set()
    for plan in all_plans:
        vol_de = parse_volume_string(plan.get('volume_de', '0'))
        vol_fr = parse_volume_string(plan.get('volume_fr', '0'))
        plan_specs.add((float(vol_de), float(vol_fr)))

    users_without_plan = []
    for user in all_users:
        h_info = user.get('breakdown', {}).get('hiddify', {})
        m_info = user.get('breakdown', {}).get('marzban', {})
        
        user_vol_de = h_info.get('usage_limit_GB', -1.0)
        user_vol_fr = m_info.get('usage_limit_GB', -1.0)

        if (user_vol_de, user_vol_fr) not in plan_specs:
            users_without_plan.append(user)

    text = fmt_users_by_plan_list(users_without_plan, "بدون پلن مشخص", page)

    base_cb = "admin:list_no_plan"
    back_cb = "admin:report_by_plan_select"
    kb = menu.create_pagination_menu(base_cb, page, len(users_without_plan), back_cb)
    _safe_edit(uid, msg_id, text, reply_markup=kb)