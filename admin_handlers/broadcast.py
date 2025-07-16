import logging
import time
from telebot import types
import pytz
from datetime import datetime, timedelta

from database import db
from hiddify_api_handler import api_handler
from marzban_api_handler import marzban_handler
from menu import menu
from utils import _safe_edit

logger = logging.getLogger(__name__)
bot, admin_conversations = None, None

def initialize_broadcast_handlers(b, conv_dict):
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

def start_broadcast_flow(call, params):
    prompt = "لطفاً جامعه هدف برای ارسال پیام همگانی را انتخاب کنید:"
    _safe_edit(call.from_user.id, call.message.message_id, prompt, reply_markup=menu.broadcast_target_menu())

def ask_for_broadcast_message(call, params):
    target_group = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    admin_conversations[uid] = {'broadcast_target': target_group}
    prompt = f"پیام شما برای گروه «{target_group.replace('_', ' ').title()}» ارسال خواهد شد.\n\nلطفاً پیام خود را بنویسید:"
    _safe_edit(uid, msg_id, prompt, reply_markup=menu.cancel_action("admin:panel"), parse_mode="HTML")
    bot.register_next_step_handler_by_chat_id(uid, _send_broadcast)

def _send_broadcast(message: types.Message):
    admin_id = message.from_user.id
    if admin_id not in admin_conversations: return
    target_group = admin_conversations.pop(admin_id)['broadcast_target']
    
    uuids_to_fetch, target_user_ids = [], []
    
    if target_group != 'all':
        # FIX: منطق جدید با API Handler های خالص
        h_users = api_handler.get_all_users()
        m_users = marzban_handler.get_all_users()
        all_users = h_users + [u for u in m_users if u.get('uuid')] # ترکیب با اطمینان از وجود UUID
        
        filtered_users = []
        now_utc = datetime.now(pytz.utc)
        if target_group == 'online':
            deadline = now_utc - timedelta(minutes=3)
            filtered_users = [u for u in all_users if u.get('is_active') and u.get('last_online') and u['last_online'].astimezone(pytz.utc) >= deadline]
        elif target_group == 'active_1':
            deadline = now_utc - timedelta(days=1)
            filtered_users = [u for u in all_users if u.get('last_online') and u['last_online'].astimezone(pytz.utc) >= deadline]
        elif target_group == 'inactive_7':
            filtered_users = [u for u in all_users if u.get('last_online') and 1 <= (now_utc - u['last_online'].astimezone(pytz.utc)).days < 7]
        elif target_group == 'inactive_0':
            filtered_users = [u for u in all_users if not u.get('last_online')]
        
        uuids_to_fetch = [u['uuid'] for u in filtered_users]

    if target_group == 'all':
        target_user_ids = db.get_all_user_ids()
    else:
        target_user_ids = db.get_user_ids_by_uuids(uuids_to_fetch)

    if not target_user_ids:
        bot.send_message(admin_id, "هیچ کاربری در گروه هدف یافت نشد.")
        return

    unique_targets = set(target_user_ids) - {admin_id}
    bot.send_message(admin_id, f"⏳ شروع ارسال پیام برای {len(unique_targets)} کاربر...")
    success_count, fail_count = 0, 0
    for user_id in unique_targets:
        try:
            bot.copy_message(chat_id=user_id, from_chat_id=admin_id, message_id=message.message_id)
            success_count += 1
        except Exception as e:
            logger.warning(f"Failed to send broadcast to user {user_id}: {e}")
            fail_count += 1
        time.sleep(0.1)
    bot.send_message(admin_id, f"✅ ارسال پیام همگانی تمام شد.\n- ✔️ موفق: {success_count}\n- ❌ ناموفق: {fail_count}")

