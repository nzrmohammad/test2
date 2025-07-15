import logging
import time
import os
import json
from telebot import types, telebot
from database import db
from api_handler import api_handler
from marzban_api_handler import marzban_handler
from menu import menu
from formatters import (
    fmt_one, fmt_users_list, fmt_hiddify_panel_info, fmt_top_consumers,
    fmt_online_users_list, fmt_bot_users_list, fmt_birthdays_list,
    fmt_marzban_system_stats, fmt_panel_users_list
)
from utils import escape_markdown, _safe_edit, validate_uuid
from datetime import datetime
from config import ADMIN_IDS, DATABASE_PATH, TELEGRAM_FILE_SIZE_LIMIT_BYTES, PAGE_SIZE
from telebot.apihelper import ApiTelegramException

from admin_hiddify_handlers import _start_add_user_convo, initialize_hiddify_handlers
from admin_marzban_handlers import _start_add_marzban_user_convo, initialize_marzban_handlers


logger = logging.getLogger(__name__)
admin_conversations = {}
bot = None

def is_admin(message: types.Message) -> bool:
    return message.from_user.id in ADMIN_IDS

def register_admin_handlers(b: telebot.TeleBot):
    global bot
    bot = b
    initialize_hiddify_handlers(bot, admin_conversations)
    initialize_marzban_handlers(bot, admin_conversations)

# --- Search Flow ---
def _ask_for_search_query(uid, msg_id, panel: str):
    prompt = "لطفاً نام یا UUID کاربر مورد نظر برای جستجو در این پنل را وارد کنید:"
    admin_conversations[uid] = {'panel': panel}
    # _safe_edit به صورت خودکار متن را escape می‌کند
    _safe_edit(uid, msg_id, prompt, 
               reply_markup=menu.cancel_action(f"admin_manage_panel_{panel}"),
               parse_mode="MarkdownV2")
    bot.register_next_step_handler_by_chat_id(uid, _handle_user_search)

def _handle_user_search(message: types.Message):
    uid, query = message.from_user.id, message.text.strip().lower()
    if uid not in admin_conversations or 'panel' not in admin_conversations[uid]:
        bot.send_message(uid, "خطا: اطلاعات پنل یافت نشد\\. لطفاً دوباره تلاش کنید\\.", parse_mode="MarkdownV2")
        return
    
    panel = admin_conversations.pop(uid)['panel']
    if not query:
        bot.send_message(uid, "جستجو لغو شد\\.", parse_mode="MarkdownV2")
        return
        
    wait_msg = bot.send_message(uid, "⏳ در حال جستجو\\.\\.\\.", parse_mode="MarkdownV2") 
    all_users = api_handler.get_all_users(panel=panel)
    found_user = next((u for u in all_users if query.lower() in u.get('name', '').lower()), None)
    
    bot.delete_message(uid, wait_msg.message_id)

    if found_user:
        identifier = found_user.get('uuid')
        info = api_handler.user_info(identifier)
        if not info:
            bot.send_message(uid, f"❌ خطایی در دریافت جزئیات کاربر `{escape_markdown(query)}` رخ داد\\.", reply_markup=menu.admin_panel_management_menu(panel), parse_mode="MarkdownV2")
            return

        daily_usage = db.get_usage_since_midnight_by_uuid(identifier)
        text = fmt_one(info, daily_usage) # fmt_one خودش متن را برای MarkdownV2 آماده می‌کند
        kb = menu.admin_user_interactive_management(info, info['is_active'], panel)
        bot.send_message(uid, text, reply_markup=kb, parse_mode="MarkdownV2")
    else:
        err_msg = f"❌ کاربری با مشخصات `{escape_markdown(query)}` در این پنل یافت نشد\\."
        bot.send_message(uid, err_msg, reply_markup=menu.admin_panel_management_menu(panel), parse_mode="MarkdownV2")

# --- Broadcast Flow ---
def _start_broadcast_flow(uid, msg_id):
    prompt = "لطفاً جامعه هدف برای ارسال پیام همگانی را انتخاب کنید:"
    _safe_edit(uid, msg_id, prompt, reply_markup=menu.broadcast_target_menu())

def _ask_for_broadcast_message(uid, msg_id, target_group):
    admin_conversations[uid] = {'broadcast_target': target_group}
    prompt = f"پیام شما برای گروه «<b>{target_group.replace('_', ' ').title()}</b>» ارسال خواهد شد.\n\nلطفاً پیام خود را بنویسید (متن، عکس، ویدیو و...):"
    _safe_edit(uid, msg_id, prompt, reply_markup=menu.cancel_action("admin_panel"), parse_mode="HTML")
    bot.register_next_step_handler_by_chat_id(uid, _send_broadcast)

def _send_broadcast(message: types.Message):
    admin_id = message.from_user.id
    if admin_id not in admin_conversations or 'broadcast_target' not in admin_conversations[admin_id]: return
    target_group = admin_conversations.pop(admin_id)['broadcast_target']
    uuids_to_fetch, target_user_ids = [], []
    if target_group == 'online': uuids_to_fetch = [u['uuid'] for u in api_handler.online_users()]
    elif target_group == 'active_1': uuids_to_fetch = [u['uuid'] for u in api_handler.get_active_users(1)]
    elif target_group == 'inactive_7': uuids_to_fetch = [u['uuid'] for u in api_handler.get_inactive_users(1, 7)]
    elif target_group == 'inactive_0': uuids_to_fetch = [u['uuid'] for u in api_handler.get_inactive_users(-1, -1)]
    if target_group == 'all': target_user_ids = db.get_all_user_ids()
    else: target_user_ids = db.get_user_ids_by_uuids(uuids_to_fetch)
    if admin_id in target_user_ids: target_user_ids.remove(admin_id)
    if not target_user_ids:
        bot.send_message(admin_id, "هیچ کاربری در گروه هدف یافت نشد\\. پیامی ارسال نشد\\.", parse_mode="MarkdownV2")
        return
    unique_targets = set(target_user_ids)
    bot.send_message(admin_id, f"⏳ شروع ارسال پیام برای {len(unique_targets)} کاربر\\.\\.\\.", parse_mode="MarkdownV2")
    success_count, fail_count = 0, 0
    for user_id in unique_targets:
        try:
            bot.copy_message(chat_id=user_id, from_chat_id=admin_id, message_id=message.message_id)
            success_count += 1
        except Exception as e:
            logger.warning(f"Failed to send broadcast to user {user_id}: {e}")
            fail_count += 1
        time.sleep(0.1)
    bot.send_message(admin_id, f"✅ ارسال پیام همگانی تمام شد\\.\n\n\\- ✔️ موفق: {success_count}\n\\- ❌ ناموفق: {fail_count}", parse_mode="MarkdownV2")

# --- Edit Flow ---
def _ask_for_new_value(uid, msg_id, edit_type: str):
    prompt_map = {
        "addgb": "لطفاً مقدار حجم برای افزودن \\(به گیگابایت\\) را وارد کنید:",
        "adddays": "لطفاً تعداد روز برای افزودن را وارد کنید:"
    }
    prompt = prompt_map.get(edit_type, "مقدار جدید را وارد کنید:")
    
    identifier = admin_conversations.get(uid, {}).get('identifier')
    back_callback = f"admin_search_result_{identifier}" if identifier else "admin_management_menu"
    
    _safe_edit(uid, msg_id, prompt, reply_markup=menu.cancel_action(back_callback))
    bot.register_next_step_handler_by_chat_id(uid, _apply_user_edit)

def _apply_user_edit(msg: types.Message):
    uid, text = msg.from_user.id, msg.text.strip()
    if uid not in admin_conversations: return
    
    convo = admin_conversations.get(uid, {})
    identifier = convo.get('identifier')
    edit_type = convo.get('edit_type')
    panel = convo.get('panel')
    msg_id = convo.get('msg_id')
    
    admin_conversations[uid].pop('edit_type', None)

    if not all([identifier, edit_type, panel, msg_id]):
        bot.send_message(uid, "خطای داخلی: اطلاعات ویرایش ناقص است\\. لطفاً دوباره تلاش کنید\\.", parse_mode="MarkdownV2")
        return

    if text.startswith('/'):
        bot.clear_step_handler_by_chat_id(uid)
        bot.send_message(uid, "عملیات ویرایش لغو شد\\.", parse_mode="MarkdownV2")
        info = api_handler.user_info(identifier)
        if info:
            # فرمت‌کننده متن را escape می‌کند
            _safe_edit(uid, msg_id, fmt_one(info, {}), reply_markup=menu.admin_user_interactive_management(identifier, info['is_active'], panel))
        return

    try:
        value = float(text)
        add_gb, add_days = 0, 0
        if edit_type == "addgb": add_gb = value
        elif edit_type == "adddays": add_days = int(value)
        
        if api_handler.modify_user(identifier, add_usage_gb=add_gb, add_days=add_days):
            new_info = api_handler.user_info(identifier)
            success_text = fmt_one(new_info, {}) + "\n\n*✅ کاربر با موفقیت ویرایش شد\\.*"
            _safe_edit(uid, msg_id, success_text, reply_markup=menu.admin_user_interactive_management(identifier, new_info['is_active'], panel))
        else:
            _safe_edit(uid, msg_id, "❌ خطا در ویرایش کاربر\\.", reply_markup=menu.admin_user_interactive_management(identifier, True, panel))
    except Exception as e:
        logger.error(f"Admin edit error: {e}")
        _safe_edit(uid, msg_id, "❌ خطای ناشناخته رخ داد\\.", reply_markup=menu.admin_user_interactive_management(identifier, True, panel))

def _handle_health_check(call: types.CallbackQuery):
    try:
        bot.answer_callback_query(call.id, "در حال دریافت اطلاعات پنل\\.\\.\\.")
        info = api_handler.get_panel_info()
        text = fmt_hiddify_panel_info(info) # فرمت‌کننده متن را escape می‌کند
        
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به تحلیل‌ها", callback_data="admin_analytics_menu_hiddify"))
        kb.add(types.InlineKeyboardButton("↩️ بازگشت به انتخاب پنل", callback_data="admin_select_server_for_analytics"))
        
        _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb)
        
    except Exception as e:
        logger.error(f"ADMIN HEALTH CHECK Error for chat {call.from_user.id}: {e}")
        _safe_edit(call.from_user.id, call.message.message_id, "❌ خطایی در دریافت اطلاعات پنل رخ داد\\.", reply_markup=menu.admin_analytics_menu(panel='hiddify'))

def _handle_bot_db_backup_request(call: types.CallbackQuery):
    chat_id = call.from_user.id
    log_adapter = logging.LoggerAdapter(logger, {'user_id': chat_id})
    log_adapter.info("Admin requested a BOT DATABASE backup.")

    bot.answer_callback_query(call.id, "در حال پردازش\\.\\.")

    if not os.path.exists(DATABASE_PATH):
        bot.send_message(chat_id, "❌ فایل دیتابیس ربات یافت نشد\\.")
        return

    try:
        file_size = os.path.getsize(DATABASE_PATH)

        if file_size > TELEGRAM_FILE_SIZE_LIMIT_BYTES:
            size_in_mb = file_size / (1024 * 1024)
            error_message = escape_markdown(
                f"❌ خطا: حجم فایل دیتابیس ({size_in_mb:.2f} MB) "
                f"بیشتر از حد مجاز تلگرام (50 MB) است\\."
            )
            bot.send_message(chat_id, error_message, parse_mode="MarkdownV2")
            return

        status_msg = escape_markdown("⏳ در حال آماده‌سازی و ارسال فایل پشتیبان دیتابیس ربات\\.\\.\\.")
        bot.send_message(chat_id, status_msg, parse_mode="MarkdownV2")
        
        with open(DATABASE_PATH, "rb") as db_file:
            caption_text = escape_markdown("✅ فایل پشتیبان دیتابیس ربات (آلمان)\\.")
            bot.send_document(chat_id, db_file, caption=caption_text, parse_mode="MarkdownV2")
            
    except ApiTelegramException as e:
        logger.error(f"Bot DB Backup failed due to Telegram API error: {e}")
        error_text = escape_markdown(f"❌ خطای API تلگرام: {e.description}")
        bot.send_message(chat_id, error_text, parse_mode="MarkdownV2")
        
    except Exception as e:
        logger.error(f"Bot DB Backup failed with a general error: {e}")
        error_text = escape_markdown(f"❌ یک خطای ناشناخته رخ داد: {e}")
        bot.send_message(chat_id, error_text, parse_mode="MarkdownV2")

def json_datetime_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def _handle_marzban_backup_request(call: types.CallbackQuery):
    chat_id = call.from_user.id
    msg_id = call.message.message_id
    log_adapter = logging.LoggerAdapter(logger, {'user_id': chat_id})
    log_adapter.info("Admin requested a Marzban users backup.")
    
    bot.answer_callback_query(call.id, "در حال دریافت اطلاعات کاربران فرانسه\\.\\.")
    status_msg = "⏳ در حال دریافت لیست کاربران از پنل فرانسه و ساخت فایل پشتیبان\\.\\.\\."
    _safe_edit(chat_id, msg_id, status_msg)

    try:
        marzban_users = marzban_handler.get_all_users()
        if not marzban_users:
            err_msg = "❌ هیچ کاربری در پنل فرانسه یافت نشد یا دسترسی به API ممکن نیست\\."
            _safe_edit(chat_id, msg_id, err_msg, reply_markup=menu.admin_backup_selection_menu())
            return
        
        backup_filename = f"marzban_backup_{datetime.now().strftime('%Y-%m-%d')}.json"
        
        with open(backup_filename, 'w', encoding='utf-8') as f:
            json.dump(marzban_users, f, ensure_ascii=False, indent=4, default=json_datetime_serializer)
            
        success_msg = "✅ فایل پشتیبان با موفقیت ساخته شد\\. در حال ارسال\\.\\.\\."
        _safe_edit(chat_id, msg_id, success_msg)

        with open(backup_filename, "rb") as backup_file:
            caption = escape_markdown(f"✅ فایل پشتیبان کاربران پنل فرانسه (مرزبان) شامل {len(marzban_users)} کاربر\\.")
            bot.send_document(chat_id, backup_file, caption=caption, parse_mode="MarkdownV2")

        os.remove(backup_filename)

    except Exception as e:
        logger.error(f"Marzban backup failed for chat {chat_id}: {e}")
        err_msg = escape_markdown(f"❌ یک خطای ناشناخته در هنگام ساخت پشتیبان رخ داد: {e}")
        _safe_edit(chat_id, msg_id, err_msg, reply_markup=menu.admin_backup_selection_menu())

def handle_admin_callbacks(call: types.CallbackQuery):
    uid, data, msg_id = call.from_user.id, call.data, call.message.message_id
    bot.answer_callback_query(call.id)

    # --- Main Panel and Sub-Panel Navigation ---
    if data == "admin_panel":
        _safe_edit(uid, msg_id, "👑 پنل مدیریت", reply_markup=menu.admin_panel())
        return
        
    if data == "admin_management_menu":
        _safe_edit(uid, msg_id, "👥 مدیریت کاربران", reply_markup=menu.admin_management_menu())
        return

    if data.startswith("admin_manage_panel_"):
        panel = data.split('_')[-1]
        panel_name = "آلمان 🇩🇪" if panel == "hiddify" else "فرانسه 🇫🇷"
        _safe_edit(uid, msg_id, f"مدیریت کاربران پنل *{panel_name}*", reply_markup=menu.admin_panel_management_menu(panel))
        return

    # --- Conversation Starters (User Creation & Search) ---
    if data.startswith("admin_add_user_"):
        panel = data.split('_')[-1]
        if panel == 'hiddify':
            _start_add_user_convo(uid, msg_id)
        elif panel == 'marzban':
            _start_add_marzban_user_convo(uid, msg_id)
        return

    if data.startswith("admin_search_user_"):
        panel = data.split('_')[-1]
        _ask_for_search_query(uid, msg_id, panel)
        return

    # --- Context-Based Edit Flow (for both panels) ---
    if data.startswith("admin_show_edit_menu_"):
        parts = data.split('_')
        panel = parts[3]
        identifier = '_'.join(parts[4:]) 
        admin_conversations[uid] = {'identifier': identifier, 'panel': panel, 'msg_id': msg_id}
        _safe_edit(uid, msg_id, "🔧 *کدام ویژگی را می‌خواهید ویرایش کنید؟*", reply_markup=menu.admin_edit_user_menu(identifier))
        return

    if data.startswith("admin_action_"):
        if uid not in admin_conversations:
            bot.answer_callback_query(call.id, "خطا: اطلاعات کاربر یافت نشد. لطفاً دوباره تلاش کنید.", show_alert=True)
            return
            
        action = data.replace("admin_action_", "")
        admin_conversations[uid]['edit_type'] = action
        _ask_for_new_value(uid, msg_id, action)
        return

    # --- User Info Display ---
    if data.startswith("admin_search_result_") or data.startswith("admin_db_id_result_"):
        identifier = ""
        if data.startswith("admin_search_result_"):
            identifier = data.replace("admin_search_result_", "")
        else:
            db_id = int(data.replace("admin_db_id_result_", ""))
            uuid_row = db.uuid_by_id(uid, db_id)
            if not uuid_row:
                bot.answer_callback_query(call.id, "❌ کاربر در دیتابیس ربات یافت نشد.", show_alert=True)
                return
            identifier = uuid_row['uuid']

        info = api_handler.user_info(identifier)
        if not info:
            bot.answer_callback_query(call.id, "❌ اطلاعات کاربر قابل دریافت نیست.", show_alert=True)
            return

        daily_usage = db.get_usage_since_midnight_by_uuid(identifier)
        panel_context = 'marzban' if 'marzban' in info.get('breakdown', {}) and 'hiddify' not in info.get('breakdown', {}) else 'hiddify'
        is_manageable = validate_uuid(identifier)
        
        text = fmt_one(info, daily_usage) # fmt_one prepares the markdown
        kb = menu.admin_user_interactive_management(identifier, info['is_active'], panel_context) if is_manageable else menu.admin_unmanaged_user_menu(panel_context)
        if not is_manageable:
            text += "\n\n*⚠️ این کاربر در دیتابیس ربات ثبت نشده و قابل ویرایش از اینجا نیست\\.*"
        
        _safe_edit(uid, msg_id, text, reply_markup=kb)
        return

    # --- Reporting and Analytics Navigation ---
    if data == "admin_select_server_for_reports":
        _safe_edit(uid, msg_id, "لطفاً پنل را برای گزارش‌گیری انتخاب کنید:", reply_markup=menu.admin_server_selection_menu(base_callback="admin_reports_menu"))
        return

    if data.startswith("admin_reports_menu_"):
        panel = data.split('_')[-1]
        panel_name = "آلمان 🇩🇪" if panel == "hiddify" else "فرانسه 🇫🇷"
        _safe_edit(uid, msg_id, f"📜 *گزارش‌گیری پنل {panel_name}*", reply_markup=menu.admin_reports_menu(panel=panel))
        return

    if data == "admin_select_server_for_analytics":
        _safe_edit(uid, msg_id, "لطفاً پنل را برای تحلیل و آمار انتخاب کنید:", reply_markup=menu.admin_server_selection_menu(base_callback="admin_analytics_menu"))
        return

    if data.startswith("admin_analytics_menu_"):
        panel = data.split('_')[-1]
        panel_name = "آلمان 🇩🇪" if panel == "hiddify" else "فرانسه 🇫🇷"
        _safe_edit(uid, msg_id, f"📊 *تحلیل و آمار پنل {panel_name}*", reply_markup=menu.admin_analytics_menu(panel=panel))
        return

    # --- Paginated Lists ---
    if any(data.startswith(prefix) for prefix in ["admin_list_panel_users_", "admin_online_", "admin_active_1_", "admin_inactive_7_", "admin_inactive_0_", "admin_birthdays_", "admin_list_bot_users_", "admin_top_consumers_"]):
        try:
            parts = data.split('_')
            panel = parts[-2] if parts[-2] in ['hiddify', 'marzban'] else None
            base_callback = '_'.join(parts[:-2]) if panel else '_'.join(parts[:-1])
            page = int(parts[-1])
            
            user_list, text, kb = [], "", None
            panel_name = "آلمان 🇩🇪" if panel == "hiddify" else "فرانسه 🇫🇷"

            if base_callback == "admin_list_panel_users":
                _safe_edit(uid, msg_id, f"⏳ در حال دریافت لیست کاربران پنل *{panel_name}*\\.\\.\\.")
                user_list = api_handler.get_all_users(panel=panel)
                text = fmt_panel_users_list(user_list, panel_name, page) # Formatter handles escaping
                
                temp_kb = types.InlineKeyboardMarkup(row_width=3)
                paginated_users = user_list[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
                user_buttons = [types.InlineKeyboardButton(u.get('name'), callback_data=f"admin_search_result_{u.get('uuid')}") for u in paginated_users]
                temp_kb.add(*user_buttons)
                
                nav_buttons = []
                if page > 0: nav_buttons.append(types.InlineKeyboardButton("⬅️ قبلی", callback_data=f"{base_callback}_{panel}_{page - 1}"))
                if (page + 1) * PAGE_SIZE < len(user_list): nav_buttons.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=f"{base_callback}_{panel}_{page + 1}"))
                if nav_buttons: temp_kb.row(*nav_buttons)
                temp_kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin_manage_panel_{panel}"))
                kb = temp_kb
            
            _safe_edit(uid, msg_id, text, reply_markup=kb)

        except Exception as e:
            logger.exception(f"ADMIN LIST Error for chat {uid}, data: {data}")
            _safe_edit(uid, msg_id, "❌ خطایی در پردازش لیست رخ داد\\.", reply_markup=menu.admin_panel())
        return

    # --- Direct Actions ---
    if any(data.startswith(prefix) for prefix in ["admin_toggle_", "admin_reset_bday_", "admin_reset_usage_", "admin_delete_", "admin_confirm_delete_", "admin_cancel_delete_"]):
        parts = data.split('_')
        action = parts[1]
        
        if action == "confirm" or action == "cancel":
            uuid = '_'.join(parts[3:])
            if action == "confirm":
                _safe_edit(uid, msg_id, "⏳ در حال حذف کامل کاربر\\.\\.\\.")
                if api_handler.delete_user(uuid):
                    db.delete_user_by_uuid(uuid)
                    _safe_edit(uid, msg_id, "✅ کاربر با موفقیت حذف شد\\.", reply_markup=menu.admin_management_menu())
                else:
                    _safe_edit(uid, msg_id, "❌ خطا در حذف کاربر از پنل\\.", reply_markup=menu.admin_management_menu())
            else: # cancel
                _safe_edit(uid, msg_id, "عملیات حذف لغو شد\\.", reply_markup=menu.admin_management_menu())
            return
            
        panel, identifier = parts[2], '_'.join(parts[3:])

        if action == "toggle":
            info = api_handler.user_info(identifier)
            if info and api_handler.modify_user(identifier, data={'is_active': not info['is_active']}):
                bot.answer_callback_query(call.id, f"کاربر {'فعال' if not info['is_active'] else 'غیرفعال'} شد\\.")
                new_info = api_handler.user_info(identifier)
                _safe_edit(uid, msg_id, fmt_one(new_info, {}), reply_markup=menu.admin_user_interactive_management(identifier, new_info['is_active'], panel))
            else:
                bot.answer_callback_query(call.id, "❌ خطا در تغییر وضعیت\\.")
        
        elif action == "reset": 
            sub_action = parts[2]
            panel, identifier = parts[3], '_'.join(parts[4:])
            if sub_action == "bday":
                user_id_to_reset = db.get_user_id_by_uuid(identifier)
                if user_id_to_reset:
                    db.reset_user_birthday(user_id_to_reset)
                    bot.answer_callback_query(call.id, "✅ تاریخ تولد کاربر ریست شد\\.")
                    _safe_edit(uid, msg_id, call.message.text + "\n\n*تاریخ تولد کاربر ریست شد\\.*", reply_markup=call.message.reply_markup)
                else:
                    bot.answer_callback_query(call.id, "❌ خطا: کاربری برای این UUID یافت نشد\\.")
            elif sub_action == "usage":
                if api_handler.reset_user_usage(identifier):
                    bot.answer_callback_query(call.id, "✅ مصرف کاربر صفر شد\\.")
                    new_info = api_handler.user_info(identifier)
                    _safe_edit(uid, msg_id, fmt_one(new_info, {}), reply_markup=menu.admin_user_interactive_management(identifier, new_info['is_active'], panel))
                else:
                    bot.answer_callback_query(call.id, "❌ خطا در ریست کردن مصرف\\.")

        elif action == "delete":
            _safe_edit(uid, msg_id, f"⚠️ *آیا از حذف کامل کاربر با شناسه زیر اطمینان دارید؟*\\n`{escape_markdown(identifier)}`", reply_markup=menu.confirm_delete(identifier))
        return

    # --- Other Static Callbacks ---
    if data == "admin_marzban_system_stats":
        # ... (logic for system stats)
        return
    if data == "admin_select_backup":
        _safe_edit(uid, msg_id, "🗄️ لطفاً نوع پشتیبان‌گیری را انتخاب کنید:", reply_markup=menu.admin_backup_selection_menu())
        return
    if data == "admin_backup_bot_db":
        _handle_bot_db_backup_request(call)
        return
    if data == "admin_backup_marzban":
        _handle_marzban_backup_request(call)
        return