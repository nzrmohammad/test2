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

def _get_combined_user_info(identifier: str) -> Optional[Dict[str, Any]]:
    # (این تابع خصوصی است و آندرلاین آن باقی می‌ماند)
    is_uuid = validate_uuid(identifier)
    h_info, m_info = None, None
    if is_uuid: h_info = combined_handler.user_info(identifier)
    m_info = combined_handler.get_user_info(identifier) if is_uuid else combined_handler.get_user_by_username(identifier)
    if not h_info and not m_info: return None
    if m_info and not h_info:
        m_info['breakdown'] = {'marzban': {'usage': m_info['current_usage_GB'], 'limit': m_info['usage_limit_GB'], 'last_online': m_info.get('last_online')}}
        return m_info
    if h_info and not m_info:
        h_info['breakdown'] = {'hiddify': {'usage': h_info['current_usage_GB'], 'limit': h_info['usage_limit_GB'], 'last_online': h_info.get('last_online')}}
        return h_info
    if h_info and m_info:
        h_info['breakdown'] = {'hiddify': h_info, 'marzban': m_info}
        total_limit = h_info['usage_limit_GB'] + m_info['usage_limit_GB']
        total_usage = h_info['current_usage_GB'] + m_info['current_usage_GB']
        h_info['usage_limit_GB'], h_info['current_usage_GB'] = total_limit, total_usage
        h_info['remaining_GB'] = max(0, total_limit - total_usage)
        h_info['usage_percentage'] = (total_usage / total_limit * 100) if total_limit > 0 else 0
        if m_info.get('last_online') and (not h_info.get('last_online') or m_info['last_online'] > h_info['last_online']):
            h_info['last_online'] = m_info['last_online']
        return h_info
    return None

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
    uid, text = msg.from_user.id, msg.text.strip()
    if uid not in admin_conversations: return
    convo = admin_conversations.pop(uid, {})
    identifier, edit_type, panel, msg_id = convo.get('identifier'), convo.get('edit_type'), convo.get('panel'), convo.get('msg_id')
    if not all([identifier, edit_type, panel, msg_id]): return
    try:
        value = float(text)
        success = False
        info = _get_combined_user_info(identifier)
        if not info: raise Exception("User not found")
        if panel == 'hiddify': success = combined_handler.modify_user_relative(info['uuid'], add_gb=value if edit_type == "add_gb" else 0, add_days=int(value) if edit_type == "add_days" else 0)
        elif panel == 'marzban': success = combined_handler.modify_user(info['name'], add_usage_gb=value if edit_type == "add_gb" else 0, add_days=int(value) if edit_type == "add_days" else 0)
        if success:
            new_info = _get_combined_user_info(identifier)
            text_to_show = fmt_admin_user_summary(new_info) + "\n\n*✅ کاربر با موفقیت ویرایش شد.*"
            kb = menu.admin_user_interactive_management(identifier, new_info['is_active'], panel)
            _safe_edit(uid, msg_id, text_to_show, reply_markup=kb)
        else: raise Exception("API call failed")
    except Exception as e:
        logger.error(f"Failed to apply user edit for {identifier}: {e}")
        _safe_edit(uid, msg_id, "❌ خطا در ویرایش کاربر.", reply_markup=menu.admin_user_interactive_management(identifier, True, panel))

def handle_toggle_status(call, params):
    panel, identifier = params[0], ':'.join(params[1:])
    info = _get_combined_user_info(identifier)
    if not info: return
    new_status = not info.get('is_active', False)
    h_success, m_success = True, True
    if 'hiddify' in info.get('breakdown', {}): h_success = combined_handler.modify_user(info['uuid'], data={'enable': new_status})
    if 'marzban' in info.get('breakdown', {}): m_success = combined_handler.modify_user(info['name'], data={'status': 'active' if new_status else 'disabled'})
    if h_success and m_success:
        bot.answer_callback_query(call.id, "✅ وضعیت با موفقیت تغییر کرد.")
        new_info = _get_combined_user_info(identifier)
        if new_info: _safe_edit(call.from_user.id, call.message.message_id, fmt_admin_user_summary(new_info), reply_markup=menu.admin_user_interactive_management(identifier, new_info['is_active'], panel))
    else:
        bot.answer_callback_query(call.id, "❌ عملیات ناموفق بود.", show_alert=True)

def handle_reset_birthday(call, params):
    panel, identifier = params[0], ':'.join(params[1:])
    user_id_to_reset = db.get_user_id_by_uuid(identifier)
    if user_id_to_reset:
        db.reset_user_birthday(user_id_to_reset)
        bot.answer_callback_query(call.id, "✅ تاریخ تولد کاربر ریست شد.")
        info = _get_combined_user_info(identifier)
        if info: _safe_edit(call.from_user.id, call.message.message_id, fmt_admin_user_summary(info), reply_markup=menu.admin_user_interactive_management(identifier, info['is_active'], panel))
    else:
        bot.answer_callback_query(call.id, "❌ خطا: کاربر در دیتابیس ربات یافت نشد.", show_alert=True)

def handle_reset_usage_menu(call, params):
    panel, identifier = params[0], ':'.join(params[1:])
    _safe_edit(call.from_user.id, call.message.message_id, "⚙️ *مصرف کدام پنل صفر شود؟*", reply_markup=menu.admin_reset_usage_selection_menu(identifier, panel))

def handle_reset_usage_action(call, params):
    panel_to_reset, identifier = params[0], ':'.join(params[1:])
    info = _get_combined_user_info(identifier)
    if not info:
        bot.answer_callback_query(call.id, "❌ کاربر یافت نشد.", show_alert=True)
        return
    h_success, m_success = True, True
    if panel_to_reset in ['h', 'both'] and 'hiddify' in info.get('breakdown', {}): h_success = combined_handler.reset_user_usage(info['uuid'])
    if panel_to_reset in ['m', 'both'] and 'marzban' in info.get('breakdown', {}): m_success = combined_handler.reset_user_usage(info['name'])
    if h_success and m_success:
        bot.answer_callback_query(call.id, "✅ مصرف کاربر با موفقیت صفر شد.")
        new_info = _get_combined_user_info(identifier)
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
        info = _get_combined_user_info(identifier)
        if info: _safe_edit(uid, msg_id, fmt_admin_user_summary(info), reply_markup=menu.admin_user_interactive_management(identifier, info['is_active'], panel))
        else: _safe_edit(uid, msg_id, "عملیات لغو شد.", reply_markup=menu.admin_management_menu())
        return
    if action == "confirm":
        _safe_edit(uid, msg_id, "⏳ در حال حذف کامل کاربر...")
        success = combined_handler.delete_user_from_all_panels(identifier) # <<-- تغییر کلیدی
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

    # استفاده از هندلر جستجوی جدید
    results = combined_handler.search_user(query)

    if not results:
        _safe_edit(uid, original_msg_id, f"❌ کاربری با مشخصات `{escape_markdown(query)}` یافت نشد.", reply_markup=menu.cancel_action("admin:management_menu"))
        return

    if len(results) == 1:
        # اگر فقط یک نتیجه بود، مستقیم به صفحه مدیریت کاربر برو
        user = results[0]
        panel = user['panel']
        identifier = user.get('uuid') or user.get('name')
        # برای نمایش اطلاعات کامل، از api_handler مربوطه استفاده می‌کنیم
        info = combined_handler.user_info(identifier) if panel == 'hiddify' else combined_handler.get_user_by_username(identifier)
        if info:
            text = fmt_admin_user_summary(info)
            kb = menu.admin_user_interactive_management(identifier, info.get('is_active', False), panel)
            _safe_edit(uid, original_msg_id, text, reply_markup=kb)
    else:
        # اگر نتایج متعدد بود، لیست آن‌ها را نمایش بده
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


