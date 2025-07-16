from telebot import types
from menu import menu
from api_handler2 import api_handler
from user_formatters import fmt_one
from utils import _safe_edit, escape_markdown
import logging

logger = logging.getLogger(__name__)
bot = None
admin_conversations = {}

def initialize_hiddify_handlers(b_instance, conversations_dict):
    global bot, admin_conversations
    bot = b_instance
    admin_conversations = conversations_dict

def _delete_user_message(msg: types.Message):
    try:
        bot.delete_message(msg.chat.id, msg.message_id)
    except Exception as e:
        logger.warning(f"Could not delete user message {msg.message_id}: {e}")

# --- User Creation Flow ---

def _start_add_user_convo(uid, msg_id):
    admin_conversations[uid] = {'msg_id': msg_id, 'panel': 'hiddify'}
    prompt = "افزودن کاربر به پنل آلمان \\(Hiddify\\) 🇩🇪\n\n1\\. لطفاً یک **نام** برای کاربر جدید وارد کنید:"
    _safe_edit(uid, msg_id, prompt, reply_markup=menu.cancel_action("admin_manage_panel_hiddify"))
    bot.register_next_step_handler_by_chat_id(uid, _get_name_for_add_user)

def _get_name_for_add_user(msg: types.Message):
    uid, name = msg.from_user.id, msg.text.strip()
    _delete_user_message(msg)
    if uid not in admin_conversations:
        bot.send_message(uid, "⚠️ عملیات به دلیل وقفه در ربات لغو شد. لطفاً دوباره شروع کنید.", reply_markup=menu.admin_panel_management_menu('hiddify'), parse_mode="MarkdownV2")
        bot.clear_step_handler_by_chat_id(uid)
        return
    if name.startswith('/'):
        bot.clear_step_handler_by_chat_id(uid)
        _safe_edit(uid, admin_conversations[uid]['msg_id'], "عملیات ساخت کاربر لغو شد.", reply_markup=menu.admin_panel_management_menu('hiddify'))
        return
    msg_id = admin_conversations[uid].get('msg_id')
    admin_conversations[uid]['name'] = name
    prompt = f"نام کاربر: `{escape_markdown(name)}`\n\n2\\. حالا **مدت زمان** پلن \\(به روز\\) را وارد کنید \\(مثلاً: `30`\\):"
    _safe_edit(uid, msg_id, prompt, reply_markup=menu.cancel_action("admin_manage_panel_hiddify"))
    bot.register_next_step_handler_by_chat_id(uid, _get_days_for_add_user)

def _get_days_for_add_user(msg: types.Message):
    uid, days_text = msg.from_user.id, msg.text.strip()
    _delete_user_message(msg)
    if uid not in admin_conversations: return
    if days_text.startswith('/'):
        bot.clear_step_handler_by_chat_id(uid)
        _safe_edit(uid, admin_conversations[uid]['msg_id'], "عملیات ساخت کاربر لغو شد.", reply_markup=menu.admin_panel_management_menu('hiddify'))
        return
    msg_id = admin_conversations[uid].get('msg_id')
    try:
        days = int(days_text)
        admin_conversations[uid]['package_days'] = days
        name = admin_conversations[uid]['name']
        prompt = f"نام: `{escape_markdown(name)}`, مدت: `{days}` روز\n\n3\\. در نهایت، **حجم کل مصرف** \\(به گیگابایت\\) را وارد کنید \\(عدد `0` برای نامحدود\\):"
        _safe_edit(uid, msg_id, prompt, reply_markup=menu.cancel_action("admin_manage_panel_hiddify"))
        bot.register_next_step_handler_by_chat_id(uid, _get_limit_for_add_user)
    except (ValueError, TypeError):
        bot.send_message(uid, "❌ ورودی نامعتبر. لطفاً یک عدد صحیح برای روز وارد کنید.", parse_mode="MarkdownV2")
        bot.register_next_step_handler_by_chat_id(uid, _get_days_for_add_user)

def _get_limit_for_add_user(msg: types.Message):
    uid, limit_text = msg.from_user.id, msg.text.strip()
    _delete_user_message(msg)
    if uid not in admin_conversations: return
    if limit_text.startswith('/'):
        bot.clear_step_handler_by_chat_id(uid)
        _safe_edit(uid, admin_conversations[uid]['msg_id'], "عملیات ساخت کاربر لغو شد.", reply_markup=menu.admin_panel_management_menu('hiddify'))
        return
    msg_id = admin_conversations[uid].get('msg_id')
    try:
        limit = float(limit_text)
        admin_conversations[uid]['usage_limit_GB'] = limit
        # FINAL FIX: Escaping '4.', '()', and '-'
        prompt = (
            "4\\. لطفاً **حالت مصرف** را با ارسال عدد مورد نظر انتخاب کنید:\n\n"
            "`1` \\- ماهانه \\(monthly\\)\n"
            "`2` \\- هفتگی \\(weekly\\)\n"
            "`3` \\- روزانه \\(daily\\)\n"
            "`4` \\- بدون ریست \\(حجم کل برای تمام دوره\\)"
        )
        _safe_edit(uid, msg_id, prompt, reply_markup=menu.cancel_action("admin_manage_panel_hiddify"))
        bot.register_next_step_handler_by_chat_id(uid, _get_mode_for_add_user)
    except (ValueError, TypeError):
        bot.send_message(uid, "❌ ورودی نامعتبر. لطفاً یک عدد برای حجم وارد کنید.", parse_mode="MarkdownV2")
        bot.register_next_step_handler_by_chat_id(uid, _get_limit_for_add_user)

def _get_mode_for_add_user(msg: types.Message):
    uid, choice = msg.from_user.id, msg.text.strip()
    _delete_user_message(msg)
    if uid not in admin_conversations: return
    msg_id = admin_conversations[uid].get('msg_id')
    mode_map = {'1': 'monthly', '2': 'weekly', '3': 'daily', '4': 'no_reset'}
    if choice not in mode_map:
        bot.send_message(uid, "❌ انتخاب نامعتبر است. لطفاً عددی بین ۱ تا ۴ وارد کنید.", parse_mode="MarkdownV2")
        bot.register_next_step_handler_by_chat_id(uid, _get_mode_for_add_user)
        return
    _finish_user_creation(uid, msg_id, mode_map[choice])

def _finish_user_creation(uid, msg_id, mode):
    if uid not in admin_conversations:
        _safe_edit(uid, msg_id, "⚠️ عملیات به دلیل وقفه در ربات لغو شد. لطفاً دوباره شروع کنید.", reply_markup=menu.admin_panel_management_menu('hiddify'))
        return
    
    admin_conversations[uid]['mode'] = mode
    user_data = admin_conversations.pop(uid)
    
    # FINAL FIX: Escape all dynamic values that might contain special characters
    name_escaped = escape_markdown(user_data['name'])
    limit_gb_escaped = escape_markdown(f"{user_data.get('usage_limit_GB', 0.0):.1f}")
    days_escaped = escape_markdown(str(user_data['package_days']))
    mode_escaped = escape_markdown(user_data['mode'])

    wait_msg_text = (
        f"⏳ در حال ساخت کاربر با اطلاعات زیر:\n"
        f"\\> نام: `{name_escaped}`\n"
        f"\\> حجم: `{limit_gb_escaped} GB`\n"
        f"\\> مدت: `{days_escaped}` روز\n"
        f"\\> حالت: `{mode_escaped}`"
    )
    _safe_edit(uid, msg_id, wait_msg_text)

    new_user_info = api_handler.add_user(user_data)
    if new_user_info:
        report = fmt_one(new_user_info, {})
        uuid_escaped = escape_markdown(new_user_info.get('uuid', 'N/A'))
        success_text = f"✅ کاربر با موفقیت ساخته شد\\.\n\n{report}\n\n`{uuid_escaped}`"
        _safe_edit(uid, msg_id, success_text, reply_markup=menu.admin_panel_management_menu('hiddify'))
    else:
        err_msg = "❌ خطا در ساخت کاربر. ممکن است نام تکراری باشد یا پنل در دسترس نباشد. لطفاً لاگ‌های سرور را برای خطای `422` بررسی کنید."
        _safe_edit(uid, msg_id, err_msg, reply_markup=menu.admin_panel_management_menu('hiddify'))
