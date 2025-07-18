import logging
from telebot import types, telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
from config import ADMIN_IDS, CUSTOM_SUB_LINK_BASE_URL, EMOJIS
from database import db
import combined_handler 
from menu import menu
from utils import validate_uuid, escape_markdown, load_custom_links, _safe_edit
from user_formatters import fmt_one, quick_stats, fmt_service_plans, fmt_panel_quick_stats
from utils import load_service_plans

logger = logging.getLogger(__name__)
bot = telebot.TeleBot("YOUR_BOT_TOKEN")

def _save_first_uuid(message: types.Message):
    uid, uuid_str = message.from_user.id, message.text.strip().lower()
    if not validate_uuid(uuid_str):
        m = bot.send_message(uid, "❌ `UUID` نامعتبر است\\. دوباره تلاش کنید\\.", parse_mode="MarkdownV2")
        if m: bot.register_next_step_handler(m, _save_first_uuid)
        return
        
    info = combined_handler.get_combined_user_info(uuid_str)
    if not info:
        m = bot.send_message(uid, "❌ `UUID` در پنل یافت نشد\\. دوباره تلاش کنید\\.", parse_mode="MarkdownV2")
        if m: bot.register_next_step_handler(m, _save_first_uuid)
        return

    status_message = db.add_uuid(uid, uuid_str, info.get("name", "کاربر ناشناس"))
    
    if "✅" in status_message:
        user_data = db.user(uid)
        has_birthday = bool(user_data and user_data.get('birthday'))
        bot.send_message(uid, escape_markdown(status_message), reply_markup=menu.main(uid in ADMIN_IDS, has_birthday), parse_mode="MarkdownV2")
    else:
        bot.send_message(uid, escape_markdown(status_message), parse_mode="MarkdownV2")
        m = bot.send_message(uid, "لطفاً یک `UUID` دیگر وارد کنید\\.", parse_mode="MarkdownV2")
        if m: bot.register_next_step_handler(m, _save_first_uuid)

def _add_uuid_step(message: types.Message):
    uid, uuid_str = message.from_user.id, message.text.strip().lower()
    user_data = db.user(uid)
    has_birthday = bool(user_data and user_data.get('birthday'))

    if uuid_str.startswith('/'):
        bot.clear_step_handler_by_chat_id(uid)
        bot.send_message(uid, "عملیات افزودن اکانت لغو شد\\.", reply_markup=menu.main(uid in ADMIN_IDS, has_birthday), parse_mode="MarkdownV2")
        return

    if not validate_uuid(uuid_str):
        m = bot.send_message(uid, "❌ `UUID` نامعتبر است\\. دوباره تلاش کنید یا عملیات را لغو کنید\\.", reply_markup=menu.cancel_action("manage"), parse_mode="MarkdownV2")
        if m: bot.register_next_step_handler(m, _add_uuid_step)
        return

    info = combined_handler.get_combined_user_info(uuid_str)
    if not info:
        m = bot.send_message(uid, "❌ `UUID` در پنل یافت نشد\\. دوباره تلاش کنید یا عملیات را لغو کنید\\.", reply_markup=menu.cancel_action("manage"), parse_mode="MarkdownV2")
        if m: bot.register_next_step_handler(m, _add_uuid_step)
        return
    
    status_message = db.add_uuid(uid, uuid_str, info.get("name", "کاربر ناشناس"))
    bot.send_message(uid, escape_markdown(status_message), reply_markup=menu.accounts(db.uuids(uid)), parse_mode="MarkdownV2")

def _get_birthday_step(message: types.Message):
    uid = message.from_user.id
    birthday_str = message.text.strip()
    
    # FINAL FIX: Switched to parsing Gregorian date format (YYYY-MM-DD).
    try:
        gregorian_date = datetime.strptime(birthday_str, '%Y-%m-%d').date()
        db.update_user_birthday(uid, gregorian_date)
        bot.send_message(uid, "✅ تاریخ تولد شما با موفقیت ثبت شد\\.",
                         reply_markup=menu.main(uid in ADMIN_IDS, has_birthday=True), parse_mode="MarkdownV2")
    except ValueError:
        m = bot.send_message(uid, "❌ فرمت تاریخ نامعتبر است\\. لطفاً به شکل `YYYY-MM-DD` وارد کنید \\(مثلاً `1990-08-27`\\)\\.", parse_mode="MarkdownV2")
        bot.clear_step_handler_by_chat_id(uid)
        if m: bot.register_next_step_handler(m, _get_birthday_step)

# --- Callback Handlers ---

def _handle_add_uuid_request(call: types.CallbackQuery):
    _safe_edit(call.from_user.id, call.message.message_id, "لطفاً UUID جدید را ارسال کنید:", reply_markup=menu.cancel_action("manage"), parse_mode=None)
    bot.register_next_step_handler_by_chat_id(call.from_user.id, _add_uuid_step)

def _show_manage_menu(call: types.CallbackQuery):
    _safe_edit(call.from_user.id, call.message.message_id, "🔐 *فهرست اکانت‌ها*", reply_markup=menu.accounts(db.uuids(call.from_user.id)))

def _show_quick_stats(call: types.CallbackQuery):
    text, menu_data = quick_stats(db.uuids(call.from_user.id), page=0)
    reply_markup = menu.quick_stats_menu(menu_data['num_accounts'], menu_data['current_page'])
    _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=reply_markup)

def _show_settings(call: types.CallbackQuery):
    settings = db.get_user_settings(call.from_user.id)
    _safe_edit(call.from_user.id, call.message.message_id, "⚙️ *تنظیمات اعلان‌ها*", reply_markup=menu.settings(settings))

def _go_back_to_main(call: types.CallbackQuery):
    user_data = db.user(call.from_user.id)
    has_birthday = bool(user_data and user_data.get('birthday'))
    _safe_edit(call.from_user.id, call.message.message_id, "🏠 *منوی اصلی*", reply_markup=menu.main(call.from_user.id in ADMIN_IDS, has_birthday))

def _handle_birthday_gift_request(call: types.CallbackQuery):
    prompt = "لطفاً تاریخ تولد خود را به فرمت میلادی `YYYY-MM-DD` وارد کنید \\(مثلاً: `1990-08-27`\\)\\.\n\nدر روز تولدتان از ما هدیه بگیرید\\!"
    _safe_edit(call.from_user.id, call.message.message_id, prompt, reply_markup=menu.cancel_action("back"))
    bot.register_next_step_handler_by_chat_id(call.from_user.id, _get_birthday_step)

def _show_plans(call: types.CallbackQuery):
    text = fmt_service_plans()
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(f"{EMOJIS['home']} بازگشت به منوی اصلی", callback_data="back"))
    _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb)

def _show_plan_categories(call: types.CallbackQuery):
    """منوی انتخاب دسته‌بندی پلن‌ها را نمایش می‌دهد."""
    prompt = "لطفاً دسته‌بندی سرویس مورد نظر خود را انتخاب کنید:"
    _safe_edit(call.from_user.id, call.message.message_id, prompt, reply_markup=menu.plan_category_menu())

# تابع جدید برای نمایش پلن‌های فیلتر شده
def _show_filtered_plans(call: types.CallbackQuery):
    """پلن‌ها را بر اساس نوع فیلتر کرده و نمایش می‌دهد."""
    plan_type = call.data.split(":")[1] # مثلا 'combined' or 'germany'
    
    all_plans = load_service_plans()
    # فیلتر کردن پلن‌ها بر اساس نوع
    filtered_plans = [p for p in all_plans if p.get("type") == plan_type]
    
    text = fmt_service_plans(filtered_plans, plan_type)
    
    # دکمه بازگشت به منوی انتخاب دسته‌بندی
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(f"{EMOJIS['back']} بازگشت", callback_data="view_plans"))
    _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb)

USER_CALLBACK_MAP = {
    "add": _handle_add_uuid_request,
    "manage": _show_manage_menu,
    "quick_stats": _show_quick_stats,
    "settings": _show_settings,
    "back": _go_back_to_main,
    "birthday_gift": _handle_birthday_gift_request,
    "view_plans": _show_plan_categories,
}

def handle_user_callbacks(call: types.CallbackQuery):
    uid, data, msg_id = call.from_user.id, call.data, call.message.message_id

    handler = USER_CALLBACK_MAP.get(data)
    if handler:
        bot.clear_step_handler_by_chat_id(uid)
        handler(call)
        return
    
    if data.startswith("acc_"):
        uuid_id = int(data.split("_")[1])
        row = db.uuid_by_id(uid, uuid_id)
        if row and (info := combined_handler.get_combined_user_info(row["uuid"])):
            daily_usage_data = db.get_usage_since_midnight(uuid_id)
            text = fmt_one(info, daily_usage_data)
            _safe_edit(uid, msg_id, text, reply_markup=menu.account_menu(uuid_id))
            
    elif data.startswith("toggle_"):
        setting_key = data.replace("toggle_", "")
        current_settings = db.get_user_settings(uid)
        db.update_user_setting(uid, setting_key, not current_settings.get(setting_key, True))
        _safe_edit(uid, msg_id, "⚙️ *تنظیمات شما به‌روز شد*", reply_markup=menu.settings(db.get_user_settings(uid)))

    elif data.startswith("getlinks_"):
        uuid_id = int(data.split("_")[1])
        row = db.uuid_by_id(call.from_user.id, uuid_id)
        if not row:
            bot.answer_callback_query(call.id, "❌ خطا: اطلاعات اکانت یافت نشد.", show_alert=True)
            return

        user_uuid = row['uuid']
        custom_links = load_custom_links()
        user_links_data = custom_links.get(user_uuid)
        
        if user_links_data and user_links_data.get('normal'):
            link_id = user_links_data['normal']
            if link_id.startswith('http'):
                full_sub_link = link_id
            else:
                full_sub_link = CUSTOM_SUB_LINK_BASE_URL.rstrip('/') + '/' + link_id.lstrip('/')
            
            text = (
                f"🔗 *لینک اشتراک شما آماده است*\n\n"
                f"برای کپی کردن، روی لینک زیر ضربه بزنید:\n\n"
                f"`{escape_markdown(full_sub_link)}`"
            )
            
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"acc_{uuid_id}"))
            _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb, parse_mode="MarkdownV2")
        else:
            bot.answer_callback_query(call.id, "❌ لینک سفارشی برای این اکانت در فایل json تعریف نشده است\\.", show_alert=True)
            
    elif data.startswith("del_"):
        uuid_id = int(data.split("_")[1])
        db.deactivate_uuid(uuid_id)
        _safe_edit(call.from_user.id, call.message.message_id, "🗑 اکانت با موفقیت حذف شد\\.", reply_markup=menu.accounts(db.uuids(call.from_user.id)))

    elif data.startswith("win_hiddify_") or data.startswith("win_marzban_"):
        parts = data.split("_")
        panel_code = parts[1]
        uuid_id = int(parts[2])

        if db.uuid_by_id(uid, uuid_id):
            panel_db_name = f"{panel_code}_usage_gb"
            panel_display_name = "آلمان 🇩🇪" if panel_code == "hiddify" else "فرانسه 🇫🇷"

            stats = db.get_panel_usage_in_intervals(uuid_id, panel_db_name)
            text = fmt_panel_quick_stats(panel_display_name, stats)

            markup = InlineKeyboardMarkup().add(
                InlineKeyboardButton(f"{EMOJIS['back']} بازگشت", callback_data=f"win_select_{uuid_id}")
            )
            _safe_edit(uid, msg_id, text, reply_markup=markup)

    elif data.startswith("win_select_"):
        uuid_id = int(data.split("_")[2])
        if db.uuid_by_id(uid, uuid_id):
            text = "لطفاً سرور مورد نظر خود را برای مشاهده آمار مصرف انتخاب کنید:"
            _safe_edit(uid, msg_id, text, reply_markup=menu.server_selection_menu(uuid_id), parse_mode=None)
            
    elif data.startswith("qstats_acc_page_"):
        page = int(data.split("_")[3])
        text, menu_data = quick_stats(db.uuids(uid), page=page)
        reply_markup = menu.quick_stats_menu(menu_data['num_accounts'], menu_data['current_page'])
        _safe_edit(uid, msg_id, text, reply_markup=reply_markup)

    if data.startswith("show_plans:"):
        _show_filtered_plans(call)
        return

def register_user_handlers(b: telebot.TeleBot):
    """Registers all message handlers for regular users."""
    global bot
    bot = b

    @bot.message_handler(commands=["start"])
    def cmd_start(msg: types.Message):
        uid = msg.from_user.id
        log_adapter = logging.LoggerAdapter(logger, {'user_id': uid})
        log_adapter.info("User started the bot.")
        db.add_or_update_user(uid, msg.from_user.username, msg.from_user.first_name, msg.from_user.last_name)
        user_data = db.user(uid)
        has_birthday = bool(user_data and user_data.get('birthday'))

        if db.uuids(uid):
            bot.send_message(uid, "🏠 *به منوی اصلی خوش آمدید*", reply_markup=menu.main(uid in ADMIN_IDS, has_birthday), parse_mode="MarkdownV2")
        else:
            m = bot.send_message(uid, "👋 *خوش آمدید\\!*\n\nلطفاً `UUID` اکانت خود را ارسال کنید\\.", parse_mode="MarkdownV2")
            if m: bot.register_next_step_handler(m, _save_first_uuid)