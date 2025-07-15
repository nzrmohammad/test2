

def _safe_edit(chat_id: int, msg_id: int, text: str, **kwargs):
    """A helper function to safely edit messages."""
    try:
        bot.edit_message_text(text, chat_id, msg_id, **kwargs)
    except Exception as e:
        if 'message is not modified' not in str(e):
            logger.error(f"Admin safe edit error: {e}")



def _clear_and_start(uid, start_function, msg_id=None):
    """Clears any pending step handlers before starting a new conversation."""
    bot.clear_step_handler_by_chat_id(uid)
    if msg_id:
        start_function(uid, msg_id)
    else:
        start_function(uid)





# --- User Search Flow ---







def _show_panel(call: types.CallbackQuery):
    _safe_edit(call.from_user.id, call.message.message_id, "👑 پنل مدیریت", reply_markup=menu.admin_panel())

def _show_management_menu(call: types.CallbackQuery):
    _safe_edit(call.from_user.id, call.message.message_id, "👥 مدیریت کاربران", reply_markup=menu.admin_management_menu())

def _show_reports_menu(call: types.CallbackQuery):
    _safe_edit(call.from_user.id, call.message.message_id, "📜 *گزارش‌گیری کاربران*", reply_markup=menu.admin_reports_menu())

# def _show_analytics_menu(call: types.CallbackQuery):
#     _safe_edit(call.from_user.id, call.message.message_id, "📊 *تحلیل و آمار*", reply_markup=menu.admin_analytics_menu())

def _handle_add_user(call: types.CallbackQuery):
    _start_add_user_convo(call.from_user.id, call.message.message_id)

def _handle_search_user(call: types.CallbackQuery):
    _ask_for_search_query(call.from_user.id, call.message.message_id)

def _handle_broadcast(call: types.CallbackQuery):
    _start_broadcast_flow(call.from_user.id, call.message.message_id)



# --- دیکشنری مپ‌کننده Callback به توابع ---
# این دیکشنری، callback_data های ثابت را به تابع مربوطه‌شان متصل می‌کند.
STATIC_CALLBACK_MAP = {
    "admin_panel": _show_panel,
    "admin_management_menu": _show_management_menu,
    "admin_add_user": _handle_add_user,
    "admin_search_user": _handle_search_user,
    "admin_broadcast": _handle_broadcast,
    "admin_health_check": _handle_health_check,
    "admin_backup_bot_db": _handle_bot_db_backup_request, # Renamed
    "admin_backup_marzban": _handle_marzban_backup_request, # New

}

# --- هندلر اصلی و بازآرایی شده ---
# این تابع تمام callback های ادمین را مدیریت می‌کند.
def handle_admin_callbacks(call: types.CallbackQuery):
    uid, data, msg_id = call.from_user.id, call.data, call.message.message_id


    
