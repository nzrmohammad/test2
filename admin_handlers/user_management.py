import logging
from telebot import types
from datetime import datetime
from typing import Optional, Dict, Any

from database import db
from menu import menu
import combined_handler
from admin_formatters import fmt_admin_user_summary
from utils import _safe_edit, escape_markdown, validate_uuid

logger = logging.getLogger(__name__)
bot, admin_conversations = None, None

def initialize_user_management_handlers(b, conv_dict):
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

# REMOVED: Redundant local function _get_combined_user_info.
# All calls now use combined_handler.get_combined_user_info

def handle_show_user_summary(call, params):
    panel, identifier = params[0], ':'.join(params[1:])
    info = combined_handler.get_combined_user_info(identifier)
    if info:
        text = fmt_admin_user_summary(info)
        kb = menu.admin_user_interactive_management(identifier, info.get('is_active', False), panel)
        _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb)
    else:
        _safe_edit(call.from_user.id, call.message.message_id, "خطا در دریافت اطلاعات کاربر.", reply_markup=menu.admin_panel_management_menu(panel))

def handle_edit_user_menu(call, params):
    panel, identifier = params[0], ':'.join(params[1:])
    _safe_edit(call.from_user.id, call.message.message_id, "🔧 *کدام ویژگی را میخواهید ویرایش کنید؟*", reply_markup=menu.admin_edit_user_menu(identifier, panel))

def handle_ask_edit_value(call, params):
    edit_type, panel, identifier = params[0], params[1], ':'.join(params[2:])
    prompt_map = {"add_gb": "مقدار حجم برای افزودن (GB) را وارد کنید:", "add_days": "تعداد روز برای افزودن را وارد کنید:"}
    prompt = prompt_map.get(edit_type, "مقدار جدید را وارد کنید:")
    uid, msg_id = call.from_user.id, call.message.message_id
    admin_conversations[uid] = {'edit_type': edit_type, 'panel': panel, 'identifier': identifier, 'msg_id': msg_id}
    _safe_edit(uid, msg_id, prompt, reply_markup=menu.cancel_action(f"adm:us:{panel}:{identifier}"))
    bot.register_next_step_handler_by_chat_id(uid, apply_user_edit)

def apply_user_edit(msg: types.Message):
    """
    Handles adding GB or days to a user across one or all panels.
    This function has been completely rewritten for correctness.
    """
    uid, text = msg.from_user.id, msg.text.strip()
    if uid not in admin_conversations: return
    convo = admin_conversations.pop(uid, {})
    identifier, edit_type, panel, msg_id = convo.get('identifier'), convo.get('edit_type'), convo.get('panel'), convo.get('msg_id')
    if not all([identifier, edit_type, panel, msg_id]): return
    
    try:
        value = float(text)
        add_gb = value if edit_type == "add_gb" else 0
        add_days = int(value) if edit_type == "add_days" else 0

        # FIX: Use the new centralized function to modify the user
        success = combined_handler.modify_user_on_all_panels(
            identifier=identifier,
            add_gb=add_gb,
            add_days=add_days,
            target_panel=panel # Specify which panel to modify ('hiddify', 'marzban', or 'both')
        )
        
        if success:
            new_info = combined_handler.get_combined_user_info(identifier)
            text_to_show = fmt_admin_user_summary(new_info) + "\n\n*✅ کاربر با موفقیت ویرایش شد.*"
            # The original panel doesn't matter as much now, but we'll keep it for consistency
            original_panel_for_menu = 'hiddify' if 'hiddify' in new_info.get('breakdown', {}) else 'marzban'
            kb = menu.admin_user_interactive_management(identifier, new_info['is_active'], original_panel_for_menu)
            _safe_edit(uid, msg_id, text_to_show, reply_markup=kb)
        else:
            raise Exception("API call failed or user not found")
            
    except Exception as e:
        logger.error(f"Failed to apply user edit for {identifier}: {e}")
        # Get original info to show the menu again on failure
        info = combined_handler.get_combined_user_info(identifier)
        is_active = info.get('is_active', False) if info else False
        _safe_edit(uid, msg_id, "❌ خطا در ویرایش کاربر.", reply_markup=menu.admin_user_interactive_management(identifier, is_active, panel))

def handle_toggle_status(call, params):
    panel, identifier = params[0], ':'.join(params[1:])
    info = combined_handler.get_combined_user_info(identifier) # Use combined handler
    if not info: return
    new_status = not info.get('is_active', False)
    h_success, m_success = True, True
    if 'hiddify' in info.get('breakdown', {}): h_success = combined_handler.hiddify_handler.modify_user(info['uuid'], data={'enable': new_status})
    if 'marzban' in info.get('breakdown', {}): m_success = combined_handler.marzban_handler.modify_user(info['name'], data={'status': 'active' if new_status else 'disabled'})
    
    if h_success and m_success:
        bot.answer_callback_query(call.id, "✅ وضعیت با موفقیت تغییر کرد.")
        new_info = combined_handler.get_combined_user_info(identifier) # Use combined handler
        if new_info: _safe_edit(call.from_user.id, call.message.message_id, fmt_admin_user_summary(new_info), reply_markup=menu.admin_user_interactive_management(identifier, new_info['is_active'], panel))
    else:
        bot.answer_callback_query(call.id, "❌ عملیات ناموفق بود.", show_alert=True)

def handle_reset_birthday(call, params):
    panel, identifier = params[0], ':'.join(params[1:])
    user_id_to_reset = db.get_user_id_by_uuid(identifier)
    if user_id_to_reset:
        db.reset_user_birthday(user_id_to_reset)
        bot.answer_callback_query(call.id, "✅ تاریخ تولد کاربر ریست شد.")
        info = combined_handler.get_combined_user_info(identifier) # Use combined handler
        if info: _safe_edit(call.from_user.id, call.message.message_id, fmt_admin_user_summary(info), reply_markup=menu.admin_user_interactive_management(identifier, info['is_active'], panel))
    else:
        bot.answer_callback_query(call.id, "❌ خطا: کاربر در دیتابیس ربات یافت نشد.", show_alert=True)

def handle_reset_usage_menu(call, params):
    panel, identifier = params[0], ':'.join(params[1:])
    _safe_edit(call.from_user.id, call.message.message_id, "⚙️ *مصرف کدام پنل صفر شود؟*", reply_markup=menu.admin_reset_usage_selection_menu(identifier, panel))

def handle_reset_usage_action(call, params):
    panel_to_reset, identifier = params[0], ':'.join(params[1:])
    info = combined_handler.get_combined_user_info(identifier) # Use combined handler
    if not info:
        bot.answer_callback_query(call.id, "❌ کاربر یافت نشد.", show_alert=True)
        return
    h_success, m_success = True, True
    if panel_to_reset in ['h', 'both'] and 'hiddify' in info.get('breakdown', {}): h_success = combined_handler.hiddify_handler.reset_user_usage(info['uuid'])
    if panel_to_reset in ['m', 'both'] and 'marzban' in info.get('breakdown', {}): m_success = combined_handler.marzban_handler.reset_user_usage(info['name'])
    
    if h_success and m_success:
        bot.answer_callback_query(call.id, "✅ مصرف کاربر با موفقیت صفر شد.")
        new_info = combined_handler.get_combined_user_info(identifier)
        if new_info:
            original_panel = 'hiddify' if 'hiddify' in new_info.get('breakdown', {}) else 'marzban'
            _safe_edit(call.from_user.id, call.message.message_id, fmt_admin_user_summary(new_info), reply_markup=menu.admin_user_interactive_management(identifier, new_info['is_active'], original_panel))
    else:
        bot.answer_callback_query(call.id, "❌ عملیات ناموفق بود.", show_alert=True)

def handle_delete_user_confirm(call, params):
    panel, identifier = params[0], ':'.join(params[1:])
    text = f"⚠️ *آیا از حذف کامل کاربر با شناسه زیر اطمینان دارید؟*\n`{escape_markdown(identifier)}`"
    _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=menu.confirm_delete(identifier, panel))

def handle_delete_user_action(call, params):
    action, panel, identifier = params[0], params[1], ':'.join(params[2:])
    uid, msg_id = call.from_user.id, call.message.message_id
    if action == "cancel":
        info = combined_handler.get_combined_user_info(identifier)
        if info: _safe_edit(uid, msg_id, fmt_admin_user_summary(info), reply_markup=menu.admin_user_interactive_management(identifier, info['is_active'], panel))
        else: _safe_edit(uid, msg_id, "عملیات لغو شد.", reply_markup=menu.admin_management_menu())
        return
    if action == "confirm":
        _safe_edit(uid, msg_id, "⏳ در حال حذف کامل کاربر...")
        success = combined_handler.delete_user_from_all_panels(identifier)
        if success:
            _safe_edit(uid, msg_id, "✅ کاربر با موفقیت از تمام پنل‌ها و ربات حذف شد.", reply_markup=menu.admin_management_menu())
        else:
            _safe_edit(uid, msg_id, "❌ خطا در حذف کاربر.", reply_markup=menu.admin_management_menu())


def handle_global_search_convo(call, params):
    """مکالمه برای جستجوی جامع کاربر را شروع می‌کند."""
    uid, msg_id = call.from_user.id, call.message.message_id
    prompt = "لطفاً نام یا UUID کاربر مورد نظر برای جستجو در هر دو پنل را وارد کنید:"
    admin_conversations[uid] = {'msg_id': msg_id}
    _safe_edit(uid, msg_id, prompt, reply_markup=menu.cancel_action("admin:management_menu"))
    bot.register_next_step_handler_by_chat_id(uid, _handle_global_search_response)

def _handle_global_search_response(message: types.Message):
    """پاسخ جستجو را پردازش کرده و نتایج را نمایش می‌دهد."""
    uid, query = message.from_user.id, message.text.strip()
    convo_data = admin_conversations.pop(uid, None)
    if not convo_data: return

    original_msg_id = convo_data['msg_id']
    _safe_edit(uid, original_msg_id, "⏳ در حال جستجو...")

    results = combined_handler.search_user(query)

    if not results:
        _safe_edit(uid, original_msg_id, f"❌ کاربری با مشخصات `{escape_markdown(query)}` یافت نشد.", reply_markup=menu.cancel_action("admin:management_menu"))
        return

    if len(results) == 1:
        user = results[0]
        panel = user['panel']
        identifier = user.get('uuid') or user.get('name')
        info = combined_handler.get_combined_user_info(identifier) # Use combined handler
        if info:
            text = fmt_admin_user_summary(info)
            kb = menu.admin_user_interactive_management(identifier, info.get('is_active', False), panel)
            _safe_edit(uid, original_msg_id, text, reply_markup=kb)
    else:
        kb = types.InlineKeyboardMarkup()
        for user in results:
            panel_emoji = "🇩🇪" if user['panel'] == 'hiddify' else "🇫🇷"
            identifier = user.get('uuid') or user.get('name')
            kb.add(types.InlineKeyboardButton(
                f"{panel_emoji} {user['name']}",
                callback_data=f"adm:us:{user['panel']}:{identifier}"
            ))
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:management_menu"))
        _safe_edit(uid, original_msg_id, "چندین کاربر یافت شد. لطفاً یکی را انتخاب کنید:", reply_markup=kb)