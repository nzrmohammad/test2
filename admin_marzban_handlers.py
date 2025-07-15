from telebot import types, telebot
from menu import menu
from marzban_api_handler import marzban_handler
from utils import escape_markdown, _safe_edit

bot = None
admin_conversations = {}

def initialize_marzban_handlers(b_instance, conversations_dict):
    """Initializes necessary variables from the main router."""
    global bot, admin_conversations
    bot = b_instance
    admin_conversations = conversations_dict

# --- START: ADD NEW CONVERSATION FLOW for Marzban ---
def _start_add_marzban_user_convo(uid, msg_id):
    admin_conversations[uid] = {'msg_id': msg_id, 'panel': 'marzban'}
    prompt = "افزودن کاربر به پنل فرانسه \\(مرزبان\\) 🇫🇷\n\n1\\. لطفاً یک **نام کاربری** وارد کنید \\(حروف انگلیسی، اعداد و آندرلاین\\):"
    _safe_edit(uid, msg_id, prompt,reply_markup=menu.cancel_action(f"admin_manage_panel_marzban"),parse_mode="MarkdownV2")
    bot.register_next_step_handler_by_chat_id(uid, _get_name_for_add_marzban_user)

def _get_name_for_add_marzban_user(msg: types.Message):
    uid, name = msg.from_user.id, msg.text.strip()
    if name.startswith('/'):
        bot.clear_step_handler_by_chat_id(uid)
        bot.send_message(uid, "عملیات ساخت کاربر لغو شد\\.", reply_markup=menu.admin_panel_management_menu('marzban'))
        return
        
    msg_id = admin_conversations[uid].get('msg_id')
    admin_conversations[uid]['username'] = name
    prompt = f"نام کاربری: `{name}`\n\n2\\. حالا **حجم کل مصرف** \\(به گیگابایت\\) را وارد کنید \\(عدد `0` برای نامحدود\\):"
    _safe_edit(uid, msg_id, prompt,reply_markup=menu.cancel_action(f"admin_manage_panel_marzban"),parse_mode="MarkdownV2")
    bot.register_next_step_handler_by_chat_id(uid, _get_limit_for_add_marzban_user)

def _get_limit_for_add_marzban_user(msg: types.Message):
    uid, limit_text = msg.from_user.id, msg.text.strip()
    if limit_text.startswith('/'):
        bot.clear_step_handler_by_chat_id(uid)
        bot.send_message(uid, "عملیات ساخت کاربر لغو شد\\.", reply_markup=menu.admin_panel_management_menu('marzban'))
        return

    msg_id = admin_conversations[uid].get('msg_id')
    try:
        limit = float(limit_text)
        admin_conversations[uid]['usage_limit_GB'] = limit
        name = admin_conversations[uid]['username']
        prompt = f"نام کاربری: `{name}`, حجم: `{limit} GB`\n\n3\\. در نهایت، **مدت زمان** پلن \\(به روز\\) را وارد کنید \\(عدد `0` برای نامحدود\\):"
        _safe_edit(uid, msg_id, prompt,reply_markup=menu.cancel_action(f"admin_manage_panel_marzban"),parse_mode="MarkdownV2")
        bot.register_next_step_handler_by_chat_id(uid, _get_days_for_add_marzban_user)
    except (ValueError, TypeError):
        err_msg = escape_markdown("❌ ورودی نامعتبر. لطفاً یک عدد برای حجم وارد کنید\\.")
        bot.send_message(uid, err_msg, parse_mode="MarkdownV2")
        bot.register_next_step_handler_by_chat_id(uid, _get_limit_for_add_marzban_user)

def _get_days_for_add_marzban_user(msg: types.Message):
    uid, days_text = msg.from_user.id, msg.text.strip()
    if days_text.startswith('/'):
        bot.clear_step_handler_by_chat_id(uid)
        bot.send_message(uid, "عملیات ساخت کاربر لغو شد\\.", reply_markup=menu.admin_panel_management_menu('marzban'))
        return

    msg_id = admin_conversations[uid].get('msg_id')
    try:
        days = int(days_text)
        admin_conversations[uid]['package_days'] = days
        _finish_marzban_user_creation(uid, msg_id)
    except (ValueError, TypeError):
        err_msg = escape_markdown("❌ ورودی نامعتبر. لطفاً یک عدد صحیح برای روز وارد کنید\\.")
        bot.send_message(uid, err_msg, parse_mode="MarkdownV2")
        bot.register_next_step_handler_by_chat_id(uid, _get_days_for_add_marzban_user)

def _finish_marzban_user_creation(uid, msg_id):
    user_data = admin_conversations.pop(uid)
    wait_msg = f"⏳ در حال ساخت کاربر در پنل مرزبان...\n> نام کاربری: `{user_data['username']}`"
    _safe_edit(uid, msg_id, escape_markdown(wait_msg), parse_mode="MarkdownV2")

    new_user_info = marzban_handler.add_user(user_data)
    if new_user_info and new_user_info.get('username'):
        success_text = f"✅ کاربر `{new_user_info['username']}` با موفقیت در پنل فرانسه ساخته شد\\."
        _safe_edit(uid, msg_id, escape_markdown(success_text), reply_markup=menu.admin_panel_management_menu('marzban'))
    else:
        err_msg = escape_markdown("❌ خطا در ساخت کاربر. ممکن است نام تکراری باشد یا پنل در دسترس نباشد\\.")
        _safe_edit(uid, msg_id, err_msg, reply_markup=menu.admin_panel_management_menu('marzban'))