import logging
import time
import os
import json
from telebot import types, telebot
from database import db
from api_handler import api_handler
from marzban_api_handler import marzban_handler
from menu import menu
from admin_formatters import (
    fmt_users_list, fmt_hiddify_panel_info, fmt_top_consumers,
    fmt_online_users_list, fmt_bot_users_list, fmt_birthdays_list,
    fmt_marzban_system_stats, fmt_panel_users_list, fmt_admin_user_summary 
)
from user_formatters import fmt_one
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
    # --- START OF FIX: Store message_id for later editing ---
    admin_conversations[uid] = {'panel': panel, 'msg_id': msg_id}
    # --- END OF FIX ---
    _safe_edit(uid, msg_id, prompt,reply_markup=menu.cancel_action(f"admin_manage_panel_{panel}"),parse_mode="MarkdownV2")
    bot.register_next_step_handler_by_chat_id(uid, _handle_user_search)

def _handle_user_search(message: types.Message):
    uid, query = message.from_user.id, message.text.strip()
    log_adapter = logging.LoggerAdapter(logger, {'user_id': uid})

    convo_data = admin_conversations.pop(uid, None)
    if not convo_data or 'panel' not in convo_data or 'msg_id' not in convo_data:
        bot.send_message(uid, "خطا: اطلاعات جستجو یافت نشد. لطفاً دوباره تلاش کنید.", parse_mode="MarkdownV2")
        log_adapter.warning("Could not find conversation data for user search.")
        return

    panel = convo_data['panel']
    original_msg_id = convo_data['msg_id']

    try:
        bot.delete_message(uid, message.message_id)
    except Exception:
        pass # Ignore if message is already deleted

    if not query:
        _safe_edit(uid, original_msg_id, "جستجو لغو شد.", reply_markup=menu.admin_panel_management_menu(panel), parse_mode="MarkdownV2")
        return

    _safe_edit(uid, original_msg_id, "⏳ در حال جستجو...", reply_markup=None, parse_mode="MarkdownV2")
    log_adapter.info(f"Admin searching for '{query}' in panel '{panel}'.")

    all_users = api_handler.get_all_users(panel=panel)
    found_user = next((u for u in all_users if query.lower() in u.get('name', '').lower() or query.lower() in u.get('uuid', '').lower()), None)

    if found_user:
        # Use the primary identifier (UUID or username) for all operations
        identifier = found_user.get('uuid') or found_user.get('name')
        
        info = api_handler.user_info(identifier) # Fetch full details using the smart user_info
        if not info:
            err_msg = f"❌ خطایی در دریافت جزئیات کاربر `{escape_markdown(query)}` رخ داد\\."
            _safe_edit(uid, original_msg_id, err_msg, reply_markup=menu.admin_panel_management_menu(panel))
            return

        # Fetch daily usage if the user is in the database, otherwise, it's empty
        db_id = db.get_uuid_id_by_uuid(identifier)
        daily_usage = db.get_usage_since_midnight(db_id) if db_id else {}
        
        text = fmt_admin_user_summary(info)
        
        # Pass the main identifier (string) to the menu function
        kb = menu.admin_user_interactive_management(identifier, info.get('is_active', False), panel)
        _safe_edit(uid, original_msg_id, text, reply_markup=kb)
    else:
        err_msg = f"❌ کاربری با مشخصات `{escape_markdown(query)}` در این پنل یافت نشد\\."
        _safe_edit(uid, original_msg_id, err_msg, reply_markup=menu.cancel_action(f"admin_manage_panel_{panel}"))

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

    all_users_from_api = api_handler.get_all_users()
    all_users_map = {u['uuid']: u for u in all_users_from_api}

    if target_group == 'online':
        uuids_to_fetch = [u['uuid'] for u in api_handler.online_users()]
    elif target_group == 'active_1':
        uuids_to_fetch = [u['uuid'] for u in api_handler.get_active_users(1)]
    elif target_group == 'inactive_7':
        uuids_to_fetch = [u['uuid'] for u in api_handler.get_inactive_users(1, 7)]
    elif target_group == 'inactive_0':
        uuids_to_fetch = [u['uuid'] for u in api_handler.get_inactive_users(-1, -1)]
    
    if target_group == 'all':
        target_user_ids = db.get_all_user_ids()
    else:
        target_user_ids = db.get_user_ids_by_uuids(uuids_to_fetch)
    
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
    back_callback = f"ad_sr_{identifier}" if identifier else "admin_management_menu"
    
    _safe_edit(uid, msg_id, prompt, reply_markup=menu.cancel_action(back_callback))
    bot.register_next_step_handler_by_chat_id(uid, _apply_user_edit)

# In admin_router.py

def _apply_user_edit(msg: types.Message):
    uid, text = msg.from_user.id, msg.text.strip()
    log_adapter = logging.LoggerAdapter(logger, {'user_id': uid})

    if uid not in admin_conversations:
        return

    convo = admin_conversations.pop(uid, {})
    identifier = convo.get('identifier') # This is now a string (UUID or username)
    edit_type = convo.get('edit_type')
    panel = convo.get('panel')
    msg_id = convo.get('msg_id')

    if not all([identifier, edit_type, panel, msg_id]):
        bot.send_message(uid, "خطای داخلی: اطلاعات ویرایش ناقص است. لطفاً دوباره تلاش کنید.", parse_mode=None)
        log_adapter.error("Incomplete conversation data for user edit.")
        return

    try:
        value = float(text)
        add_gb, add_days = 0, 0
        if edit_type == "addgb": add_gb = value
        elif edit_type == "adddays": add_days = int(value)

        success = False
        if panel == 'hiddify':
            log_adapter.info(f"Admin modifying user {identifier} on Hiddify panel.")
            success = api_handler.modify_user(identifier, add_usage_gb=add_gb, add_days=add_days)
        elif panel == 'marzban':
            log_adapter.info(f"Admin modifying user {identifier} on Marzban panel.")
            success = marzban_handler.modify_user(identifier, add_usage_gb=add_gb, add_days=add_days)

        if success:
            new_info = api_handler.user_info(identifier)
            text_to_show = fmt_admin_user_summary(new_info) + "\n\n*✅ کاربر با موفقیت ویرایش شد\\.*"
            _safe_edit(uid, msg_id, text_to_show, reply_markup=menu.admin_user_interactive_management(identifier, new_info['is_active'], panel))
        else:
            _safe_edit(uid, msg_id, "❌ خطا در ویرایش کاربر\\.", reply_markup=menu.admin_user_interactive_management(identifier, True, panel))

    except (ValueError, TypeError):
         _safe_edit(uid, msg_id, "❌ ورودی نامعتبر\\. لطفاً یک عدد صحیح وارد کنید\\.", reply_markup=menu.admin_user_interactive_management(identifier, True, panel))
    except Exception as e:
        log_adapter.error(f"Admin edit error for user {identifier}: {e}")
        _safe_edit(uid, msg_id, "❌ خطای ناشناخته رخ داد\\.", reply_markup=menu.admin_user_interactive_management(identifier, True, panel))

def _handle_health_check(call: types.CallbackQuery):
    try:
        bot.answer_callback_query(call.id, "در حال دریافت اطلاعات پنل\\.\\.\\.")
        info = api_handler.get_panel_info()
        text = fmt_hiddify_panel_info(info)
        
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به تحلیل‌ها", callback_data="admin_analytics_menu_hiddify"))
        kb.add(types.InlineKeyboardButton("↩️ بازگشت به انتخاب پنل", callback_data="admin_select_server_for_analytics"))
        
        _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb)
        
    except Exception as e:
        logger.error(f"ADMIN HEALTH CHECK Error for chat {call.from_user.id}: {e}")
        _safe_edit(call.from_user.id, call.message.message_id, "❌ خطایی در دریافت اطلاعات پنل رخ داد\\.", reply_markup=menu.admin_analytics_menu(panel='hiddify'))

def _handle_marzban_system_stats(call: types.CallbackQuery):
    try:
        bot.answer_callback_query(call.id, "در حال دریافت آمار سیستم مرزبان\\.\\.\\.")
        stats = marzban_handler.get_system_stats()
        text = fmt_marzban_system_stats(stats)
        
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به تحلیل‌ها", callback_data="admin_analytics_menu_marzban"))
        
        _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb)

    except Exception as e:
        logger.error(f"MARZBAN SYSTEM STATS Error for chat {call.from_user.id}: {e}")
        _safe_edit(call.from_user.id, call.message.message_id, "❌ خطایی در دریافت آمار سیستم رخ داد\\.", reply_markup=menu.admin_analytics_menu(panel='marzban'))

def _handle_bot_db_backup_request(call: types.CallbackQuery):
    chat_id = call.from_user.id
    log_adapter = logging.LoggerAdapter(logger, {'user_id': chat_id})
    log_adapter.info("Admin requested a BOT DATABASE backup.")

    bot.answer_callback_query(call.id, "در حال پردازش...")

    if not os.path.exists(DATABASE_PATH):
        bot.send_message(chat_id, "❌ فایل دیتابیس ربات یافت نشد\\.")
        return

    try:
        file_size = os.path.getsize(DATABASE_PATH)
        if file_size > TELEGRAM_FILE_SIZE_LIMIT_BYTES:
            size_in_mb = file_size / (1024 * 1024)
            bot.send_message(chat_id, escape_markdown(f"❌ خطا: حجم فایل دیتابیس ({size_in_mb:.2f} MB) بیشتر از حد مجاز تلگرام (50 MB) است\\."), parse_mode="MarkdownV2")
            return

        bot.send_message(chat_id, escape_markdown("⏳ در حال آماده‌سازی و ارسال فایل پشتیبان دیتابیس ربات\\.\\.\\."), parse_mode="MarkdownV2")
        
        with open(DATABASE_PATH, "rb") as db_file:
            bot.send_document(chat_id, db_file, caption=escape_markdown("✅ فایل پشتیبان دیتابیس ربات."), parse_mode="MarkdownV2")
            
    except Exception as e:
        logger.error(f"Bot DB Backup failed: {e}")
        bot.send_message(chat_id, escape_markdown(f"❌ یک خطای ناشناخته رخ داد: {e}"), parse_mode="MarkdownV2")

def json_datetime_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def _handle_marzban_backup_request(call: types.CallbackQuery):
    chat_id = call.from_user.id
    msg_id = call.message.message_id
    log_adapter = logging.LoggerAdapter(logger, {'user_id': chat_id})
    log_adapter.info("Admin requested a Marzban users backup.")
    
    bot.answer_callback_query(call.id, "در حال دریافت اطلاعات کاربران فرانسه...")
    _safe_edit(chat_id, msg_id, "⏳ در حال دریافت لیست کاربران از پنل فرانسه و ساخت فایل پشتیبان\\.\\.\\.")

    try:
        marzban_users = marzban_handler.get_all_users()
        if not marzban_users:
            _safe_edit(chat_id, msg_id, "❌ هیچ کاربری در پنل فرانسه یافت نشد یا دسترسی به API ممکن نیست\\.", reply_markup=menu.admin_backup_selection_menu())
            return
        
        backup_filename = f"marzban_backup_{datetime.now().strftime('%Y-%m-%d')}.json"
        
        with open(backup_filename, 'w', encoding='utf-8') as f:
            json.dump(marzban_users, f, ensure_ascii=False, indent=4, default=json_datetime_serializer)
            
        _safe_edit(chat_id, msg_id, "✅ فایل پشتیبان با موفقیت ساخته شد\\. در حال ارسال\\.\\.\\.")

        with open(backup_filename, "rb") as backup_file:
            caption = escape_markdown(f"✅ فایل پشتیبان کاربران پنل فرانسه (مرزبان) شامل {len(marzban_users)} کاربر\\.")
            bot.send_document(chat_id, backup_file, caption=caption, parse_mode="MarkdownV2")

        os.remove(backup_filename)

    except Exception as e:
        logger.error(f"Marzban backup failed for chat {chat_id}: {e}")
        _safe_edit(chat_id, msg_id, escape_markdown(f"❌ یک خطای ناشناخته در هنگام ساخت پشتیبان رخ داد: {e}"), reply_markup=menu.admin_backup_selection_menu())

def handle_admin_callbacks(call: types.CallbackQuery):
    uid, data, msg_id = call.from_user.id, call.data, call.message.message_id
    
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

    # --- Conversation Starters ---
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
    
    if data == 'admin_broadcast':
        _start_broadcast_flow(uid, msg_id)
        return
        
    if data.startswith("broadcast_target_"):
        target = data.replace("broadcast_target_", "")
        _ask_for_broadcast_message(uid, msg_id, target)
        return

    # --- Context-Based Edit Flow ---
    if data.startswith("ad_edt_"):
        try:
            parts = data.split('_')
            panel = parts[2]
            # Correctly join the rest of the parts to form the string identifier
            identifier = '_'.join(parts[3:])
            
            _safe_edit(uid, msg_id, "🔧 *کدام ویژگی را می‌خواهید ویرایش کنید؟*", reply_markup=menu.admin_edit_user_menu(identifier, panel))
        except (IndexError, ValueError) as e:
            logger.error(f"Could not parse callback for user edit: {data} - Error: {e}")
            bot.answer_callback_query(call.id, "خطای داخلی در پردازش دکمه ویرایش.", show_alert=True)
        return


    if data.startswith("ad_"):
        parts = data.split('_')
        action = parts[1]

        # --- Display User Info / Back from Edit ---
        if action == "sr":
            panel = parts[2]
            identifier = '_'.join(parts[3:])
            info = api_handler.user_info(identifier)
            if info:
                text = fmt_admin_user_summary(info)
                kb = menu.admin_user_interactive_management(identifier, info.get('is_active', False), panel)
                _safe_edit(uid, msg_id, text, reply_markup=kb)
            else:
                _safe_edit(uid, msg_id, "خطا در دریافت اطلاعات کاربر\\.", reply_markup=menu.admin_panel_management_menu(panel))
            return

        # --- Go to Edit Menu ---
        elif action == "edt":
            panel = parts[2]
            identifier = '_'.join(parts[3:])
            _safe_edit(uid, msg_id, "🔧 *کدام ویژگی را می‌خواهید ویرایش کنید؟*", reply_markup=menu.admin_edit_user_menu(identifier, panel))
            return

        # --- Ask for Value (e.g., GB or Days) ---
        elif action == "act":
            edit_type = parts[2]
            panel = parts[3]
            identifier = '_'.join(parts[4:])
            admin_conversations[uid] = {
                'edit_type': edit_type, 'panel': panel,
                'identifier': identifier, 'msg_id': msg_id
            }
            _ask_for_new_value(uid, msg_id, edit_type)
            return

        # --- Toggle Status ---
        elif action == "tgl":
            panel_context = parts[2]
            identifier = '_'.join(parts[3:])
            info = api_handler.user_info(identifier)
            if info:
                bot_user_info = db.get_bot_user_by_uuid(info.get('uuid', ''))
                is_self_edit = bot_user_info and str(bot_user_info.get('user_id')) == str(uid)
                new_status = not info.get('is_active', False)
                h_success = api_handler.modify_user(identifier, data={'is_active': new_status})
                m_success = marzban_handler.modify_user(info.get('name'), data={'status': 'active' if new_status else 'disabled'})
                if h_success or m_success:
                    status_text = "فعال" if new_status else "غیرفعال"
                    bot.answer_callback_query(call.id, f"✅ وضعیت با موفقیت به '{status_text}' تغییر کرد.")
                    if not is_self_edit:
                        new_info = api_handler.user_info(identifier)
                        if new_info:
                            _safe_edit(uid, msg_id, fmt_admin_user_summary(new_info), reply_markup=menu.admin_user_interactive_management(identifier, new_info['is_active'], panel_context))
                else:
                    bot.answer_callback_query(call.id, "❌ عملیات ناموفق بود.")
            return

        # --- Reset Birthday ---
        elif action == "bday":
            panel_context = parts[2]
            identifier = '_'.join(parts[3:])
            user_id_to_reset = db.get_user_id_by_uuid(identifier)
            if user_id_to_reset:
                db.reset_user_birthday(user_id_to_reset)
                bot.answer_callback_query(call.id, "✅ تاریخ تولد کاربر ریست شد.")
                info = api_handler.user_info(identifier)
                if info:
                     _safe_edit(uid, msg_id, fmt_admin_user_summary(info), reply_markup=menu.admin_user_interactive_management(identifier, info.get('is_active', False), panel_context))
            else:
                bot.answer_callback_query(call.id, "❌ خطا: این کاربر در دیتابیس ربات نیست یا UUID ندارد.")
            return

        # --- Go to Reset Usage Menu ---
        elif action == "rst":
            panel_context = parts[2]
            identifier = '_'.join(parts[3:])
            _safe_edit(uid, msg_id, "⚙️ *مصرف کدام پنل صفر شود؟*", reply_markup=menu.admin_reset_usage_selection_menu(identifier, panel_context))
            return

        # --- Confirm Reset Usage ---
        elif action == "crst":
            panel_to_reset = parts[2]
            identifier = '_'.join(parts[3:])
            panel_arg = panel_to_reset if panel_to_reset in ['hiddify', 'marzban'] else None
            if api_handler.reset_user_usage(identifier, panel=panel_arg):
                bot.answer_callback_query(call.id, "✅ مصرف کاربر با موفقیت صفر شد.")
                new_info = api_handler.user_info(identifier)
                if new_info:
                    panel_context = 'hiddify'
                    if 'marzban' in new_info.get('breakdown', {}) and 'hiddify' not in new_info.get('breakdown', {}):
                        panel_context = 'marzban'
                    _safe_edit(uid, msg_id, fmt_admin_user_summary(new_info), reply_markup=menu.admin_user_interactive_management(identifier, new_info['is_active'], panel_context))
            else:
                bot.answer_callback_query(call.id, "❌ عملیات ناموفق بود یا کاربر در پنل انتخاب شده وجود نداشت.")
            return

        # --- Go to Delete Confirmation ---
        elif action == "del":
            panel_context = parts[2]
            identifier = '_'.join(parts[3:])
            _safe_edit(uid, msg_id, f"⚠️ *آیا از حذف کامل کاربر با شناسه زیر اطمینان دارید؟*\n`{escape_markdown(identifier)}`", reply_markup=menu.confirm_delete(identifier))
            return

        # --- Confirm or Cancel Deletion ---
        elif action == "cdel" or action == "nodel":
            identifier = '_'.join(parts[2:])
            if action == "cdel":
                _safe_edit(uid, msg_id, "⏳ در حال حذف کامل کاربر...")
                if api_handler.delete_user(identifier):
                    db_id = db.get_uuid_id_by_uuid(identifier)
                    if db_id:
                        db.deactivate_uuid(db_id)
                        db.delete_user_snapshots(db_id)
                    _safe_edit(uid, msg_id, "✅ کاربر با موفقیت حذف شد\\.", reply_markup=menu.admin_management_menu())
                else:
                    _safe_edit(uid, msg_id, "❌ خطا در حذف کاربر از پنل\\.", reply_markup=menu.admin_management_menu())
            elif action == "nodel":
                info = api_handler.user_info(identifier)
                if info:
                    panel_context = 'hiddify'
                    if 'marzban' in info.get('breakdown', {}) and 'hiddify' not in info.get('breakdown', {}):
                        panel_context = 'marzban'
                    _safe_edit(uid, msg_id, fmt_admin_user_summary(info), reply_markup=menu.admin_user_interactive_management(identifier, info['is_active'], panel_context))
                else:
                    _safe_edit(uid, msg_id, "عملیات لغو شد\\.", reply_markup=menu.admin_management_menu())
            return

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

    # --- Paginated Lists (Reports, Panel Users, etc.) ---
    paginated_prefixes = ["admin_list_panel_users_", "admin_online_", "admin_active_1_", "admin_inactive_7_", "admin_inactive_0_", "admin_birthdays_", "admin_list_bot_users_", "admin_top_consumers_"]
    if any(data.startswith(prefix) for prefix in paginated_prefixes):
        try:
            parts = data.split('_')
            page = int(parts[-1])
            
            # Extract panel and base_callback
            if parts[-2] in ['hiddify', 'marzban']:
                panel = parts[-2]
                base_callback = '_'.join(parts[:-2])
                back_callback = f"admin_reports_menu_{panel}"
            else:
                panel = None
                base_callback = '_'.join(parts[:-1])
                back_callback = "admin_management_menu"

            panel_name = "آلمان 🇩🇪" if panel == "hiddify" else "فرانسه 🇫🇷"
            user_list = []
            text = "لیست خالی است." # Default text
            kb = menu.create_pagination_menu(f"{base_callback}_{panel}" if panel else base_callback, page, 0, back_callback)
            
            # -- Logic for each list type --
            if base_callback == "admin_list_panel_users":
                _safe_edit(uid, msg_id, f"⏳ در حال دریافت لیست کاربران پنل *{panel_name}*\\.\\.\\.")
                user_list = api_handler.get_all_users(panel=panel)
                text = fmt_panel_users_list(user_list, panel_name, page)
                kb = menu.create_pagination_menu(f"{base_callback}_{panel}", page, len(user_list), f"admin_manage_panel_{panel}")
            elif base_callback == "admin_online":
                user_list = api_handler.online_users(panel=panel)
                text = fmt_online_users_list(user_list, page)
                kb = menu.create_pagination_menu(f"{base_callback}_{panel}", page, len(user_list), f"admin_reports_menu_{panel}")
            elif base_callback == "admin_active_1":
                user_list = api_handler.get_active_users(1, panel=panel)
                text = fmt_users_list(user_list, 'active', page)
                kb = menu.create_pagination_menu(f"{base_callback}_{panel}", page, len(user_list), f"admin_reports_menu_{panel}")
            elif base_callback == "admin_inactive_7":
                user_list = api_handler.get_inactive_users(1, 7, panel=panel)
                text = fmt_users_list(user_list, 'inactive', page)
                kb = menu.create_pagination_menu(f"{base_callback}_{panel}", page, len(user_list), f"admin_reports_menu_{panel}")
            elif base_callback == "admin_inactive_0":
                user_list = api_handler.get_inactive_users(-1, -1, panel=panel)
                text = fmt_users_list(user_list, 'never_connected', page)
                kb = menu.create_pagination_menu(f"{base_callback}_{panel}", page, len(user_list), f"admin_reports_menu_{panel}")
            elif base_callback == "admin_top_consumers":
                user_list = api_handler.get_top_consumers(panel=panel)
                text = fmt_top_consumers(user_list, page)
                kb = menu.create_pagination_menu(f"{base_callback}_{panel}", page, len(user_list), f"admin_analytics_menu_{panel}")
            elif base_callback == "admin_list_bot_users":
                user_list = db.get_all_bot_users()
                text = fmt_bot_users_list(user_list, page)
                kb = menu.create_pagination_menu(base_callback, page, len(user_list), "admin_management_menu")
            elif base_callback == "admin_birthdays":
                user_list = db.get_users_with_birthdays()
                text = fmt_birthdays_list(user_list, page)
                kb = menu.create_pagination_menu(base_callback, page, len(user_list), "admin_panel")

            _safe_edit(uid, msg_id, text, reply_markup=kb)

        except Exception as e:
            logger.exception(f"ADMIN LIST Error for chat {uid}, data: {data}")
            _safe_edit(uid, msg_id, "❌ خطایی در پردازش لیست رخ داد\\.", reply_markup=menu.admin_panel())
        return

    # --- Other Static Callbacks ---
    if data == "admin_marzban_system_stats":
        _handle_marzban_system_stats(call)
        return
    if data == "admin_health_check":
        _handle_health_check(call)
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