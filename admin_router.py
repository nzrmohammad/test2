import logging
from telebot import types, telebot
from admin_handlers import user_management, reporting, broadcast, backup
from admin_hiddify_handlers import _start_add_user_convo, initialize_hiddify_handlers
from admin_marzban_handlers import _start_add_marzban_user_convo, initialize_marzban_handlers
from menu import menu
from utils import _safe_edit

logger = logging.getLogger(__name__)
admin_conversations = {}
bot = None

def register_admin_handlers(b: telebot.TeleBot):
    global bot
    bot = b
    
    # مقداردهی اولیه تمام ماژول‌های هندلر
    initialize_hiddify_handlers(bot, admin_conversations)
    initialize_marzban_handlers(bot, admin_conversations)
    user_management.initialize_user_management_handlers(bot, admin_conversations)
    reporting.initialize_reporting_handlers(bot)
    broadcast.initialize_broadcast_handlers(bot, admin_conversations)
    backup.initialize_backup_handlers(bot)

# ===================================================================
# بخش ۱: توابع ساده منو که در همین فایل باقی می‌مانند
# این توابع منطق خاصی ندارند و فقط منوها را نمایش می‌دهند.
# ===================================================================

def _handle_show_panel(call, params):
    """نمایش منوی اصلی پنل مدیریت."""
    _safe_edit(call.from_user.id, call.message.message_id, "👑 پنل مدیریت", reply_markup=menu.admin_panel())

def _handle_management_menu(call, params):
    """نمایش منوی مدیریت کاربران."""
    _safe_edit(call.from_user.id, call.message.message_id, "👥 مدیریت کاربران", reply_markup=menu.admin_management_menu())

def _handle_panel_management_menu(call, params):
    """نمایش منوی مدیریت یک پنل خاص (آلمان یا فرانسه)."""
    bot.clear_step_handler_by_chat_id(call.from_user.id)
    panel = params[0]
    panel_name = "آلمان 🇩🇪" if panel == "hiddify" else "فرانسه 🇫🇷"
    _safe_edit(call.from_user.id, call.message.message_id, f"مدیریت کاربران پنل *{panel_name}*", reply_markup=menu.admin_panel_management_menu(panel))

def _handle_server_selection(call, params):
    """منوی انتخاب سرور را برای گزارش‌گیری یا آمار نمایش می‌دهد."""
    base_callback = params[0]
    text_map = {"reports_menu": "لطفاً پنل را برای گزارش‌گیری انتخاب کنید:", "analytics_menu": "لطفاً پنل را برای تحلیل و آمار انتخاب کنید:"}
    _safe_edit(call.from_user.id, call.message.message_id, text_map.get(base_callback, "لطفا انتخاب کنید:"),
               reply_markup=menu.admin_server_selection_menu(f"admin:{base_callback}"))

# ===================================================================
# بخش ۲: دیکشنری توزیع‌کننده نهایی (Dispatcher Dictionary)
# این دیکشنری، قلب تپنده روتر است و هر درخواست را به تابع صحیح ارجاع می‌دهد.
# ===================================================================
ADMIN_CALLBACK_HANDLERS = {
    # منوها
    "panel": _handle_show_panel,
    "management_menu": _handle_management_menu,
    "manage_panel": _handle_panel_management_menu,
    "select_server": _handle_server_selection,
    
    # مکالمات ساخت کاربر
    "add_user": lambda c, p: (_start_add_user_convo if p[0] == 'hiddify' else _start_add_marzban_user_convo)(c.from_user.id, c.message.message_id),
    
    # مدیریت کاربر (از ماژول user_management)
    "search_user": user_management.handle_search_user_convo,
    "us": user_management.handle_show_user_summary,
    "edt": user_management.handle_edit_user_menu,
    "ask_edt": user_management.handle_ask_edit_value,
    "tgl": user_management.handle_toggle_status,
    "rbd": user_management.handle_reset_birthday,
    "rusg_m": user_management.handle_reset_usage_menu,
    "rusg_a": user_management.handle_reset_usage_action,
    "del_cfm": user_management.handle_delete_user_confirm,
    "del_a": user_management.handle_delete_user_action,

    # گزارش‌گیری (از ماژول reporting)
    "reports_menu": reporting.handle_reports_menu,
    "analytics_menu": reporting.handle_analytics_menu,
    "health_check": reporting.handle_health_check,
    "marzban_stats": reporting.handle_marzban_system_stats,
    "list": reporting.handle_paginated_list,

    # پیام همگانی (از ماژول broadcast)
    "broadcast": broadcast.start_broadcast_flow,
    "broadcast_target": broadcast.ask_for_broadcast_message,
    
    # پشتیبان‌گیری (از ماژول backup)
    "backup_menu": backup.handle_backup_menu,
    "backup": backup.handle_backup_action,
}

# ===================================================================
# بخش ۳: تابع توزیع‌کننده اصلی (Dispatcher Function)
# این تابع، موتور روتر است و درخواست‌ها را به هندلرها توزیع می‌کند.
# ===================================================================
def handle_admin_callbacks(call: types.CallbackQuery):
    """
    تابع اصلی که Callback ها را مدیریت می‌کند.
    این تابع، بر اساس `call.data`، هندلر مناسب را از دیکشنری پیدا کرده و اجرا می‌کند.
    """
    if not (call.data.startswith("admin:") or call.data.startswith("adm:")):
        return

    parts = call.data.split(':')
    action = parts[1]
    params = parts[2:]
    
    handler = ADMIN_CALLBACK_HANDLERS.get(action)
    if handler:
        try:
            handler(call, params)
        except Exception as e:
            logger.error(f"Error handling admin callback '{call.data}': {e}", exc_info=True)
            bot.answer_callback_query(call.id, "❌ خطایی در پردازش درخواست رخ داد.", show_alert=True)
    else:
        logger.warning(f"No handler found for admin action: '{action}' in callback: {call.data}")

