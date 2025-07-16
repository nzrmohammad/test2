import pytz
from datetime import datetime, timedelta
from config import EMOJIS, PAGE_SIZE
from database import db
from api_handler2 import api_handler
import jdatetime
from utils import (
    persian_date,
    format_daily_usage, escape_markdown,
    format_relative_time, validate_uuid 
)

def fmt_users_list(users: list, list_type: str, page: int) -> str:
    title_map = {
        'active': "✅ کاربران فعال (۲۴ ساعت اخیر)",
        'inactive': "⏳ کاربران غیرفعال (۱ تا ۷ روز)",
        'never_connected': "🚫 کاربرانی که هرگز متصل نشده‌اند"
    }
    title = title_map.get(list_type, "لیست کاربران")
    
    if not users:
        return f"*{escape_markdown(title)}*\n\nهیچ کاربری در این دسته یافت نشد\\."

    header_text = f"*{escape_markdown(title)}*"
    if len(users) > PAGE_SIZE:
        total_pages = (len(users) + PAGE_SIZE - 1) // PAGE_SIZE
        pagination_text = f"(صفحه {page + 1} از {total_pages} | کل: {len(users)})"
        header_text += f"\n{escape_markdown(pagination_text)}"

    lines = [header_text]
    
    start_index = page * PAGE_SIZE
    paginated_users = users[start_index : start_index + PAGE_SIZE]

    for user in paginated_users:
        name = escape_markdown(user.get('name', 'کاربر ناشناس'))
        line = f"`•` *{name}*"
        
        if list_type == 'active':
            last_online_str = persian_date(user.get('last_online')).split(' - ')[-1]
            usage_p = user.get('usage_percentage', 0)
            line += f" `|` Last Seen: `{escape_markdown(last_online_str)}` `|` Usage: `{usage_p:.1f}%`"

        elif list_type == 'inactive':
            last_online_str = format_relative_time(user.get('last_online'))
            status = "Expired" if user.get('expire', 0) < 0 else "Active"
            line += f" `|` Last Seen: `{escape_markdown(last_online_str)}` `|` Status: `{status}`"
            
        elif list_type == 'never_connected':
            created_at_str = format_relative_time(user.get('created_at'))
            limit_gb = user.get('usage_limit_GB', 0)
            line += f" `|` Registered: `{escape_markdown(created_at_str)}` `|` Limit: `{limit_gb} GB`"
            
        lines.append(line)
        
    return "\n".join(lines)

def fmt_online_users_list(users: list, page: int) -> str:
    title = "⚡️ کاربران آنلاین (۳ دقیقه اخیر)"
    
    if not users:
        return f"*{escape_markdown(title)}*\n\nهیچ کاربری در این لحظه آنلاین نیست\\."

    header_text = f"*{escape_markdown(title)}*"
    if len(users) > PAGE_SIZE:
        total_pages = (len(users) + PAGE_SIZE - 1) // PAGE_SIZE
        pagination_text = f"(صفحه {page + 1} از {total_pages} | کل: {len(users)})"
        header_text += f"\n{escape_markdown(pagination_text)}"

    paginated_users = users[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    user_lines = []

    uuid_to_bot_user = db.get_uuid_to_bot_user_map()

    for user in paginated_users:
        panel_name_raw = user.get('name', 'کاربر ناشناس')
        bot_user_info = uuid_to_bot_user.get(user.get('uuid'))
        
        name_str = escape_markdown(panel_name_raw)
        if bot_user_info and bot_user_info.get('user_id'):
            user_id = bot_user_info['user_id']
            name_str = f"[{escape_markdown(panel_name_raw)}](tg://user?id={user_id})"

        daily_usage_output = escape_markdown(format_daily_usage(user.get('daily_usage_GB', 0)))
        expire_days = user.get("expire")
        expire_text = "Unlimited"
        if expire_days is not None:
            expire_text = f"{expire_days} Days" if expire_days >= 0 else "Expired"
        expire_output = escape_markdown(expire_text)
        
        line = f"{name_str} \\| `{daily_usage_output}` \\| `{expire_output}`"
        user_lines.append(line)

    body_text = "\n".join(user_lines)
    return f"{header_text}\n\n{body_text}"

def fmt_admin_report(all_users_from_api: list, db_manager) -> str:
    if not all_users_from_api:
        return "هیچ کاربری در پنل یافت نشد\\."

    total_usage_all, active_users = 0.0, 0
    total_daily_hiddify, total_daily_marzban = 0.0, 0.0
    online_users, expiring_soon_users, new_users_today = [], [], []
    
    now_utc = datetime.now(pytz.utc)
    online_deadline = now_utc - timedelta(minutes=3)
    
    db_users_map = {u['uuid']: u.get('created_at') for u in db_manager.all_active_uuids()}

    for user_info in all_users_from_api:
        if user_info.get("is_active"):
            active_users += 1
        total_usage_all += user_info.get("current_usage_GB", 0)
        
        daily_usage_dict = db_manager.get_usage_since_midnight_by_uuid(user_info['uuid'])
        total_daily_hiddify += daily_usage_dict.get('hiddify', 0.0)
        total_daily_marzban += daily_usage_dict.get('marzban', 0.0)
        
        if user_info.get('is_active') and user_info.get('last_online') and user_info['last_online'].astimezone(pytz.utc) >= online_deadline:
            # افزودن مصرف روزانه به اطلاعات کاربر آنلاین برای استفاده در ادامه
            user_info['daily_usage_dict'] = daily_usage_dict
            online_users.append(user_info)

        if user_info.get('expire') is not None and 0 <= user_info['expire'] <= 3:
            expiring_soon_users.append(user_info)
            
        created_at = db_users_map.get(user_info['uuid'])
        if created_at and (now_utc - created_at.astimezone(pytz.utc)).days < 1:
            new_users_today.append(user_info)

    total_daily_all = total_daily_hiddify + total_daily_marzban
    report_lines = [
        f"{EMOJIS['gear']} *{escape_markdown('خلاصه وضعیت کل پنل')}*",
        f"\\- {EMOJIS['user']} تعداد کل اکانت‌ها: *{len(all_users_from_api)}*",
        f"\\- {EMOJIS['success']} اکانت‌های فعال: *{active_users}*",
        f"\\- {EMOJIS['wifi']} کاربران آنلاین: *{len(online_users)}*",
        f"\\- {EMOJIS['chart']} *مجموع مصرف کل:* `{escape_markdown(f'{total_usage_all:.2f}')} GB`",
        f"\\- {EMOJIS['lightning']} *مصرف امروز کل:* `{escape_markdown(format_daily_usage(total_daily_all))}`",
        # بخش جدید برای نمایش تفکیک مصرف روزانه کل
        f"  `\\- 🇩🇪 آلمان:* `{escape_markdown(format_daily_usage(total_daily_hiddify))}`",
        f"  `\\- 🇫🇷 فرانسه:* `{escape_markdown(format_daily_usage(total_daily_marzban))}`"
    ]

    if online_users:
        report_lines.append("\n" + "─" * 20 + f"\n*{EMOJIS['wifi']} {escape_markdown('کاربران آنلاین و مصرف امروزشان:')}*")
        online_users.sort(key=lambda u: u.get('name', ''))
        for user in online_users:
            user_name = escape_markdown(user.get('name', 'کاربر ناشناس'))
            # نمایش مصرف روزانه به تفکیک برای هر کاربر آنلاین
            daily_dict = user.get('daily_usage_dict', {})
            h_daily_str = escape_markdown(format_daily_usage(daily_dict.get('hiddify', 0.0)))
            m_daily_str = escape_markdown(format_daily_usage(daily_dict.get('marzban', 0.0)))
            report_lines.append(f"`•` *{user_name}:* 🇩🇪`{h_daily_str}` \\| 🇫🇷`{m_daily_str}`")

    if expiring_soon_users:
        report_lines.append("\n" + "─" * 20 + f"\n*{EMOJIS['warning']} {escape_markdown('کاربرانی که به زودی منقضی می‌شوند (تا ۳ روز):')}*")
        expiring_soon_users.sort(key=lambda u: u.get('expire', 99))
        for user in expiring_soon_users:
            name = escape_markdown(user['name'])
            days = user['expire']
            report_lines.append(f"`•` *{name}:* `{days} روز باقیمانده`")

    if new_users_today:
        report_lines.append("\n" + "─" * 20 + f"\n*{EMOJIS['star']} {escape_markdown('کاربران جدید (۲۴ ساعت اخیر):')}*")
        for user in new_users_today:
            name = escape_markdown(user['name'])
            report_lines.append(f"`•` *{name}*")

    return "\n".join(report_lines)

def fmt_hiddify_panel_info(info: dict) -> str:
    if not info: 
        return escape_markdown("اطلاعاتی از پنل دریافت نشد.")
    
    title = escape_markdown(info.get('title', 'N/A'))
    description = escape_markdown(info.get('description', 'N/A'))
    version = escape_markdown(info.get('version', 'N/A'))
    
    return (f"{EMOJIS['gear']} *اطلاعات پنل Hiddify*\n\n"
            f"**عنوان:** {title}\n"
            f"**توضیحات:** {description}\n"
            f"**نسخه:** {version}\n")

def fmt_top_consumers(users: list, page: int) -> str:
    title = "پرمصرف‌ترین کاربران"
    if not users:
        return f"🏆 *{escape_markdown(title)}*\n\nهیچ کاربری برای نمایش وجود ندارد."

    header_text = f"🏆 *{escape_markdown(title)}*"
    if len(users) > PAGE_SIZE:
        total_pages = (len(users) + PAGE_SIZE - 1) // PAGE_SIZE
        pagination_text = f"(صفحه {page + 1} از {total_pages} | کل: {len(users)})"
        header_text += f"\n{escape_markdown(pagination_text)}"
        
    lines = [header_text]
    paginated_users = users[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    for i, user in enumerate(paginated_users, start=page * PAGE_SIZE + 1):
        name = escape_markdown(user.get('name', 'کاربر ناشناس'))
        usage = user.get('current_usage_GB', 0)
        limit = user.get('usage_limit_GB', 0)
        usage_str = f"`{usage:.2f} GB / {limit:.2f} GB`"
        line = f"`{i}\\.` *{name}* `\\|` {EMOJIS['chart']} {usage_str}"
        lines.append(line)

    return "\n".join(lines)

def fmt_bot_users_list(bot_users: list, page: int) -> str:
    title = "کاربران ربات"
    if not bot_users:
        return f"🤖 *{escape_markdown(title)}*\n\nهیچ کاربری در ربات ثبت‌نام نکرده است."

    header_text = f"🤖 *{escape_markdown(title)}*"
    total_users = len(bot_users)
    if total_users > PAGE_SIZE:
        total_pages = (total_users + PAGE_SIZE - 1) // PAGE_SIZE
        pagination_text = f"(صفحه {page + 1} از {total_pages} | کل: {total_users})"
        header_text += f"\n{escape_markdown(pagination_text)}"

    lines = [header_text]
    start_index = page * PAGE_SIZE
    paginated_users = bot_users[start_index : start_index + PAGE_SIZE]

    for user in paginated_users:
        user_id = user.get('user_id')
        first_name = escape_markdown(user.get('first_name') or 'ناشناس')
        username = escape_markdown(f"(@{user.get('username')})" if user.get('username') else '')
        lines.append(f"`•` {first_name} {username} `| ID:` `{user_id}`")

    return "\n".join(lines)

def fmt_birthdays_list(users: list, page: int) -> str:
    title = "لیست تولد کاربران"
    if not users:
        return f"🎂 *{escape_markdown(title)}*\n\nهیچ کاربری تاریخ تولد خود را ثبت نکرده است."
    
    title_text = f"{title} (مرتب شده بر اساس ماه)"
    header_text = f"🎂 *{escape_markdown(title_text)}*"

    if len(users) > PAGE_SIZE:
        total_pages = (len(users) + PAGE_SIZE - 1) // PAGE_SIZE
        pagination_text = f"(صفحه {page + 1} از {total_pages} | کل: {len(users)})"
        header_text += f"\n{escape_markdown(pagination_text)}"

    lines = [header_text]
    start_index = page * PAGE_SIZE
    paginated_users = users[start_index : start_index + PAGE_SIZE]

    for user in paginated_users:
        name = escape_markdown(user.get('first_name', 'کاربر ناشناس'))
        gregorian_date = user['birthday']
        shamsi_date = jdatetime.date.fromgregorian(date=gregorian_date)
        
        shamsi_str = shamsi_date.strftime('%Y/%m/%d')
        gregorian_str = gregorian_date.strftime('%Y-%m-%d')
        
        lines.append(f"`•` *{name}* `\\|` solar: `{shamsi_str}` `\\|` gregorian: `{gregorian_str}`")

        
    return "\n".join(lines)

def fmt_marzban_system_stats(info: dict) -> str:
    if not info:
        return escape_markdown("اطلاعاتی از سیستم دریافت نشد\\.")

    # Helper for GB conversion
    to_gb = lambda b: b / (1024**3)

    # --- System Info ---
    version = info.get('version', 'N/A')
    mem_total_gb = to_gb(info.get('mem_total', 0))
    mem_used_gb = to_gb(info.get('mem_used', 0))
    mem_percent = (mem_used_gb / mem_total_gb * 100) if mem_total_gb > 0 else 0
    cpu_cores = info.get('cpu_cores', 'N/A')
    cpu_usage = info.get('cpu_usage', 0.0)

    # --- User Stats ---
    total_users = info.get('total_user', 0)
    online_users = info.get('online_users', 0)
    active_users = info.get('users_active', 0)
    disabled_users = info.get('users_disabled', 0)
    expired_users = info.get('users_expired', 0)

    # --- Bandwidth Stats ---
    total_dl_gb = to_gb(info.get('incoming_bandwidth', 0))
    total_ul_gb = to_gb(info.get('outgoing_bandwidth', 0))
    speed_dl_mbps = info.get('incoming_bandwidth_speed', 0) / (1024 * 1024)
    speed_ul_mbps = info.get('outgoing_bandwidth_speed', 0) / (1024 * 1024)

    report = (
        f"📊 وضعیت سیستم پنل مرزبان (فرانسه 🇫🇷)\n"
        f"------------------------------------\n"
        f"⚙️ نسخه: {version}\n"
        f"🖥️ هسته CPU: {cpu_cores} | مصرف: {cpu_usage:.1f}%\n"
        f"💾 مصرف RAM: {mem_used_gb:.2f} / {mem_total_gb:.2f} GB \\({mem_percent:.1f}%\\)"
        f"------------------------------------\n"
        f"👥 کاربران کل: {total_users}\n"
        f"🟢 فعال: {active_users}\n"
        f"🔴 آنلاین: {online_users}\n"
        f"⚪️ غیرفعال: {disabled_users}\n"
        f"🗓 منقضی شده: {expired_users}\n"
        f"------------------------------------\n"
        f"📈 ترافیک کل:\n"
        f"  ↓ دانلود: {total_dl_gb:.2f} GB\n"
        f"  ↑ آپلود: {total_ul_gb:.2f} GB\n"
        f"🚀 سرعت لحظه‌ای:\n"
        f"  ↓ دانلود: {speed_dl_mbps:.2f} MB/s\n"
        f"  ↑ آپلود: {speed_ul_mbps:.2f} MB/s"
    )
    
    # Escape the entire report to prevent any markdown errors
    return escape_markdown(report)

def fmt_panel_users_list(users: list, panel_name: str, page: int) -> str:
    title = f"کاربران پنل {panel_name}"
    if not users:
        return f"*{escape_markdown(title)}*\n\nهیچ کاربری در این پنل یافت نشد."

    header_text = f"*{escape_markdown(title)}*"
    if len(users) > PAGE_SIZE:
        total_pages = (len(users) + PAGE_SIZE - 1) // PAGE_SIZE
        pagination_text = f"(صفحه {page + 1} از {total_pages} | کل: {len(users)})"
        header_text += f"\n{escape_markdown(pagination_text)}"

    user_lines = []
    paginated_users = users[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    for user in paginated_users:
        name = escape_markdown(user.get('name', 'کاربر ناشناس'))
        expire_days = user.get("expire")
        expire_text = "نامحدود"
        if expire_days is not None:
            expire_text = f"{expire_days} روز" if expire_days >= 0 else "منقضی"
        
        line = f"`•` *{name}* `|` {EMOJIS['calendar']} {escape_markdown(expire_text)}"
        user_lines.append(line)

    body_text = "\n".join(user_lines)
    return f"{header_text}\n\n{body_text}"

# در فایل admin_formatters.py این تابع را به طور کامل جایگزین کنید

# این تابع را در فایل admin_formatters.py به طور کامل جایگزین کنید
def fmt_admin_user_summary(info: dict) -> str:
    """Formats a user summary for the admin, ensuring all values are properly escaped for MarkdownV2."""
    if not info:
        return "❌ خطا در دریافت اطلاعات کاربر\\."

    name = escape_markdown(info.get("name", "کاربر ناشناس"))
    status_emoji = "🟢" if info.get("is_active") else "🔴"
    status_text = "فعال" if info.get("is_active") else "غیرفعال"
    name_line = f"👤 نام : {name} \\({status_emoji} {status_text}\\)"

    total_limit_gb = info.get('usage_limit_GB', 0)
    total_usage_gb = info.get('current_usage_GB', 0)
    total_remaining_gb = total_limit_gb - total_usage_gb if total_limit_gb > 0 else 0
    daily_usage_total = info.get('daily_usage_GB', 0)
    
    total_limit_str = escape_markdown(f"{total_limit_gb:.2f}")
    total_usage_str = escape_markdown(f"{total_usage_gb:.2f}")
    total_remaining_str = escape_markdown(f"{total_remaining_gb:.2f}")
    total_daily_str = escape_markdown(format_daily_usage(daily_usage_total))

    total_usage_line = f"🗂️ مجموع حجم : `{total_limit_str} GB`"
    total_consumed_line = f"🔥 مجموع مصرف شده : `{total_usage_str} GB`"
    total_remaining_line = f"📥 مجموع باقیمانده: `{total_remaining_str} GB`"
    total_daily_line = f"⚡️ مجموع مصرف امروز: `{total_daily_str}`"

    breakdown_lines = ["\n*جزئیات سرورها*"]
    h_info = info.get('breakdown', {}).get('hiddify', {})
    m_info = info.get('breakdown', {}).get('marzban', {})

    if h_info:
        h_limit_str = escape_markdown(f"{h_info.get('limit', 0):.2f}")
        h_usage_str = escape_markdown(f"{h_info.get('usage', 0):.2f}")
        h_daily_str = escape_markdown(format_daily_usage(h_info.get('daily_usage', 0)))
        h_last_online_str = format_shamsi_tehran(h_info.get('last_online'))
        
        # FIX: The missing comma after this line is now added.
        breakdown_lines.extend([
            "\nآلمان 🇩🇪",
            f"🗂️ مجموع حجم : `{h_limit_str} GB`",
            f"🔥 مجموع مصرف شده : `{h_usage_str} GB`",
            f"⚡️ مصرف امروز : `{h_daily_str}`",  # <<<<<<< این ویرگول فراموش شده بود
            f"⏰ آخرین اتصال : `{h_last_online_str}`"
        ])

    if m_info:
        m_limit_str = escape_markdown(f"{m_info.get('limit', 0):.2f}")
        m_usage_str = escape_markdown(f"{m_info.get('usage', 0):.2f}")
        m_daily_str = escape_markdown(format_daily_usage(m_info.get('daily_usage', 0)))
        m_last_online_str = format_shamsi_tehran(m_info.get('last_online'))
        
        breakdown_lines.extend([
            "\nفرانسه 🇫🇷",
            f"🗂️ مجموع حجم : `{m_limit_str} GB`",
            f"🔥 مجموع مصرف شده : `{m_usage_str} GB`",
            f"⚡️ مصرف امروز : `{m_daily_str}`",
            f"⏰ آخرین اتصال : `{m_last_online_str}`"
        ])

    expire_days = info.get("expire")
    expire_label = "نامحدود"
    if expire_days is not None:
        expire_label = f"{expire_days} روز" if expire_days >= 0 else "منقضی شده"
    expire_line = f"📅 انقضا: {escape_markdown(expire_label)}"
    
    identifier = escape_markdown(info.get("uuid") or info.get("name", "N/A"))
    uuid_line = f"🔑 شناسه یکتا: `{identifier}`"

    usage_percentage = info.get('usage_percentage', 0)
    progress_bar = '░' * 15
    filled_count = int(usage_percentage / 100 * 15)
    if filled_count > 0:
        progress_bar = '▓' * filled_count + '░' * (15 - filled_count)
    
    usage_percentage_str = escape_markdown(f"{usage_percentage:.1f}")
    status_bar_line = f"وضعیت : {status_emoji} {progress_bar} {usage_percentage_str}%"
    
    report_parts = [
        name_line, "",
        total_usage_line, total_consumed_line, total_remaining_line, total_daily_line,
        *breakdown_lines, "",
        expire_line, uuid_line, "",
        status_bar_line
    ]

    return "\n".join(report_parts)




def format_shamsi_tehran(dt_obj):

    if not dt_obj:
        return "N/A"
    
    if dt_obj.tzinfo is None:
        dt_obj = pytz.utc.localize(dt_obj)

    tehran_tz = pytz.timezone('Asia/Tehran')
    tehran_dt = dt_obj.astimezone(tehran_tz)
    
    shamsi_date = jdatetime.date.fromgregorian(date=tehran_dt)
    
    return f"{shamsi_date.strftime('%Y/%m/%d')} - {tehran_dt.strftime('%H:%M')}"
