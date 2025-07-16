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
    
    initialize_hiddify_handlers(bot, admin_conversations)
    initialize_marzban_handlers(bot, admin_conversations)
    user_management.initialize_user_management_handlers(bot, admin_conversations)
    reporting.initialize_reporting_handlers(bot)
    broadcast.initialize_broadcast_handlers(bot, admin_conversations)
    backup.initialize_backup_handlers(bot)

# ===================================================================
# Simple Menu Functions
# ===================================================================

def _handle_show_panel(call, params):
    """Shows the main admin panel menu."""
    _safe_edit(call.from_user.id, call.message.message_id, "👑 پنل مدیریت", reply_markup=menu.admin_panel())

def _handle_management_menu(call, params):
    """Shows the user management menu."""
    _safe_edit(call.from_user.id, call.message.message_id, "👥 مدیریت کاربران", reply_markup=menu.admin_management_menu())

def _handle_panel_management_menu(call, params):
    """Shows the management menu for a specific panel (Hiddify/Marzban)."""
    bot.clear_step_handler_by_chat_id(call.from_user.id)
    panel = params[0]
    panel_name = "آلمان 🇩🇪" if panel == "hiddify" else "فرانسه 🇫🇷"
    _safe_edit(call.from_user.id, call.message.message_id, f"مدیریت کاربران پنل *{panel_name}*", reply_markup=menu.admin_panel_management_menu(panel))

def _handle_server_selection(call, params):
    """Shows the server selection menu for reports or analytics."""
    base_callback = params[0]
    text_map = {"reports_menu": "لطفاً پنل را برای گزارش‌گیری انتخاب کنید:", "analytics_menu": "لطفاً پنل را برای تحلیل و آمار انتخاب کنید:"}
    _safe_edit(call.from_user.id, call.message.message_id, text_map.get(base_callback, "لطفا انتخاب کنید:"),
               reply_markup=menu.admin_server_selection_menu(f"admin:{base_callback}"))

# ===================================================================
# Final Dispatcher Dictionary
# ===================================================================
ADMIN_CALLBACK_HANDLERS = {
    # Menus
    "panel": _handle_show_panel,
    "management_menu": _handle_management_menu,
    "manage_panel": _handle_panel_management_menu,
    "select_server": _handle_server_selection,
    
    # User Actions
    "add_user": lambda c, p: (_start_add_user_convo if p[0] == 'hiddify' else _start_add_marzban_user_convo)(c.from_user.id, c.message.message_id),
    # *** FINAL FIX: Corrected function name from handle_search_user_convo to handle_global_search_convo ***
    "search_user_global": user_management.handle_global_search_convo,
    "us": user_management.handle_show_user_summary,
    "edt": user_management.handle_edit_user_menu,
    "ask_edt": user_management.handle_ask_edit_value,
    "tgl": user_management.handle_toggle_status,
    "rbd": user_management.handle_reset_birthday,
    "rusg_m": user_management.handle_reset_usage_menu,
    "rusg_a": user_management.handle_reset_usage_action,
    "del_cfm": user_management.handle_delete_user_confirm,
    "del_a": user_management.handle_delete_user_action,
    
    # Reporting & Analytics
    "reports_menu": reporting.handle_reports_menu,
    "analytics_menu": reporting.handle_analytics_menu,
    "health_check": reporting.handle_health_check,
    "marzban_stats": reporting.handle_marzban_system_stats,
    "list": reporting.handle_paginated_list,
    
    # Other Admin Tools
    "broadcast": broadcast.start_broadcast_flow,
    "broadcast_target": broadcast.ask_for_broadcast_message,
    "backup_menu": backup.handle_backup_menu,
    "backup": backup.handle_backup_action,
}


def handle_admin_callbacks(call: types.CallbackQuery):
    """The main callback router for all admin actions."""
    if not call.data.startswith("admin:"):
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