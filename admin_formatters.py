import pytz
from datetime import datetime, timedelta
from config import EMOJIS, PAGE_SIZE
from database import db
from utils import (
    format_daily_usage, escape_markdown,
    format_relative_time, validate_uuid , format_raw_datetime, create_progress_bar, format_shamsi_tehran
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
            last_online_str = format_shamsi_tehran(user.get('last_online')).split(' ')[-1]
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
        
        # Ensure uuid exists before querying the database
        if user_info.get('uuid'):
            daily_usage_dict = db_manager.get_usage_since_midnight_by_uuid(user_info['uuid'])
            total_daily_hiddify += daily_usage_dict.get('hiddify', 0.0)
            total_daily_marzban += daily_usage_dict.get('marzban', 0.0)
        else:
            daily_usage_dict = {}

        if user_info.get('is_active') and user_info.get('last_online') and isinstance(user_info.get('last_online'), datetime) and user_info['last_online'].astimezone(pytz.utc) >= online_deadline:
            user_info['daily_usage_dict'] = daily_usage_dict
            online_users.append(user_info)

        if user_info.get('expire') is not None and 0 <= user_info['expire'] <= 3:
            expiring_soon_users.append(user_info)
            
        created_at = db_users_map.get(user_info.get('uuid'))
        if created_at and isinstance(created_at, datetime) and (now_utc - created_at.astimezone(pytz.utc)).days < 1:
            new_users_today.append(user_info)

    total_daily_all = total_daily_hiddify + total_daily_marzban
    report_lines = [
        f"{EMOJIS['gear']} *{escape_markdown('خلاصه وضعیت کل پنل')}*",
        f"\\- {EMOJIS['user']} تعداد کل اکانت‌ها: *{len(all_users_from_api)}*",
        f"\\- {EMOJIS['success']} اکانت‌های فعال: *{active_users}*",
        f"\\- {EMOJIS['wifi']} کاربران آنلاین: *{len(online_users)}*",
        f"\\- {EMOJIS['chart']} *مجموع مصرف کل:* `{escape_markdown(f'{total_usage_all:.2f}')} GB`",
        f"\\- {EMOJIS['lightning']} *مصرف امروز کل:* `{escape_markdown(format_daily_usage(total_daily_all))}`",
        f"  `\\- 🇩🇪 آلمان:* `{escape_markdown(format_daily_usage(total_daily_hiddify))}`",
        f"  `\\- 🇫🇷 فرانسه:* `{escape_markdown(format_daily_usage(total_daily_marzban))}`"
    ]

    if online_users:
        report_lines.append("\n" + "─" * 20 + f"\n*{EMOJIS['wifi']} {escape_markdown('کاربران آنلاین و مصرف امروزشان:')}*")
        online_users.sort(key=lambda u: u.get('name', ''))
        for user in online_users:
            user_name = escape_markdown(user.get('name', 'کاربر ناشناس'))
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
        # FINAL FIX: Replaced problematic f-string with standard concatenation.
        pagination_text = "(صفحه " + str(page + 1) + " از " + str(total_pages) + " | کل: " + str(total_users) + ")"
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
        return f"🎂 *{escape_markdown(title)}*\n\nهیچ کاربری تاریخ تولد خود را ثبت نکرده است\\."
    
    title_text = f"{title} (مرتب شده بر اساس ماه)"
    header_text = f"🎂 *{escape_markdown(title_text)}*"

    if len(users) > PAGE_SIZE:
        total_pages = (len(users) + PAGE_SIZE - 1) // PAGE_SIZE
        pagination_text = f"\\(صفحه {page + 1} از {total_pages} \\| کل: {len(users)}\\)"
        header_text += f"\n{pagination_text}"

    lines = [header_text]
    start_index = page * PAGE_SIZE
    paginated_users = users[start_index : start_index + PAGE_SIZE]

    for user in paginated_users:
        name = escape_markdown(user.get('first_name', 'کاربر ناشناس'))
        gregorian_date = user['birthday']
        gregorian_str = escape_markdown(gregorian_date.strftime('%Y-%m-%d'))
        lines.append(f"`•` *{name}* `\\|` gregorian: `{gregorian_str}`")
        
    return "\n".join(lines)

def fmt_marzban_system_stats(info: dict) -> str:
    if not info:
        return escape_markdown("اطلاعاتی از سیستم دریافت نشد\\.")

    to_gb = lambda b: b / (1024**3)

    version = escape_markdown(info.get('version', 'N/A'))
    mem_total_gb = to_gb(info.get('mem_total', 0))
    mem_used_gb = to_gb(info.get('mem_used', 0))
    mem_percent = (mem_used_gb / mem_total_gb * 100) if mem_total_gb > 0 else 0
    cpu_cores = info.get('cpu_cores', 'N/A')
    cpu_usage = info.get('cpu_usage', 0.0)

    total_users = info.get('total_user', 0)
    online_users = info.get('online_users', 0)
    active_users = info.get('users_active', 0)
    disabled_users = info.get('users_disabled', 0)
    expired_users = info.get('users_expired', 0)

    total_dl_gb = to_gb(info.get('incoming_bandwidth', 0))
    total_ul_gb = to_gb(info.get('outgoing_bandwidth', 0))
    speed_dl_mbps = info.get('incoming_bandwidth_speed', 0) / (1024 * 1024)
    speed_ul_mbps = info.get('outgoing_bandwidth_speed', 0) / (1024 * 1024)

    report = (
        f"*📊 وضعیت سیستم پنل مرزبان \\(فرانسه 🇫🇷\\)*\n"
        f"`----------------------------`\n"
        f"⚙️ نسخه: `{version}`\n"
        f"🖥️ هسته CPU: `{cpu_cores}` \\| مصرف: `{cpu_usage:.1f}%`\n"
        f"💾 مصرف RAM: `{mem_used_gb:.2f} / {mem_total_gb:.2f} GB` \\(`{mem_percent:.1f}%`\\)\n"
        f"`----------------------------`\n"
        f"👥 کاربران کل: `{total_users}`\n"
        f"🟢 فعال: `{active_users}`\n"
        f"🔴 آنلاین: `{online_users}`\n"
        f"⚪️ غیرفعال: `{disabled_users}`\n"
        f"🗓 منقضی شده: `{expired_users}`\n"
        f"`----------------------------`\n"
        f"*📈 ترافیک کل:*\n"
        f"  ↓ دانلود: `{total_dl_gb:.2f} GB`\n"
        f"  ↑ آپلود: `{total_ul_gb:.2f} GB`\n"
        f"*🚀 سرعت لحظه‌ای:*\n"
        f"  ↓ دانلود: `{speed_dl_mbps:.2f} MB/s`\n"
        f"  ↑ آپلود: `{speed_ul_mbps:.2f} MB/s`"
    )
    
    return report

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

def fmt_admin_user_summary(info: dict) -> str:
    if not info:
        return "❌ خطا در دریافت اطلاعات کاربر\\."

    name = escape_markdown(info.get("name", "کاربر ناشناس"))
    status_emoji = "🟢" if info.get("is_active") else "🔴"
    status_text = "فعال" if info.get("is_active") else "غیرفعال"
    name_line = f"👤 نام : {name} \\({status_emoji} {status_text}\\)"

    total_limit_gb = info.get('usage_limit_GB', 0)
    total_usage_gb = info.get('current_usage_GB', 0)
    
    # --- FIX: Only show total stats if user is on both panels ---
    h_info = info.get('breakdown', {}).get('hiddify')
    m_info = info.get('breakdown', {}).get('marzban')
    is_on_both_panels = h_info and m_info

    # Initialize lines with the name
    report_parts = [name_line, ""]

    if is_on_both_panels:
        total_remaining_gb = total_limit_gb - total_usage_gb
        daily_usage_total = info.get('daily_usage_GB', 0)
        
        report_parts.extend([
            f"🗂️ مجموع حجم : `{escape_markdown(f'{total_limit_gb:.2f}')} GB`",
            f"🔥 مجموع مصرف شده : `{escape_markdown(f'{total_usage_gb:.2f}')} GB`",
            f"📥 مجموع باقیمانده: `{escape_markdown(f'{total_remaining_gb:.2f}')} GB`",
            f"⚡️ مجموع مصرف امروز: `{escape_markdown(format_daily_usage(daily_usage_total))}`"
        ])

    # --- Conditional Breakdown ---
    if is_on_both_panels:
        report_parts.append("\n*جزئیات سرورها*")

    if h_info:
        h_daily_usage = h_info.get('daily_usage', 0.0) if h_info.get('daily_usage') else 0.0
        h_last_online_str = escape_markdown(format_shamsi_tehran(h_info.get('last_online')))
        
        report_parts.extend([
            "\nآلمان 🇩🇪",
            f"🗂️ حجم : `{escape_markdown(f'{h_info.get('usage_limit_GB', 0):.2f}')} GB`",
            f"🔥 مصرف شده : `{escape_markdown(f'{h_info.get('current_usage_GB', 0):.2f}')} GB`",
            f"⚡️ مصرف امروز : `{escape_markdown(format_daily_usage(h_daily_usage))}`",
            f"⏰ آخرین اتصال : `{h_last_online_str}`"
        ])

    if m_info:
        m_daily_usage = m_info.get('daily_usage', 0.0) if m_info.get('daily_usage') else 0.0
        m_last_online_str = escape_markdown(format_shamsi_tehran(m_info.get('last_online')))

        report_parts.extend([
            "\nفرانسه 🇫🇷",
            f"🗂️ حجم : `{escape_markdown(f'{m_info.get('usage_limit_GB', 0):.2f}')} GB`",
            f"🔥 مصرف شده : `{escape_markdown(f'{m_info.get('current_usage_GB', 0):.2f}')} GB`",
            f"⚡️ مصرف امروز : `{escape_markdown(format_daily_usage(m_daily_usage))}`",
            f"⏰ آخرین اتصال : `{m_last_online_str}`"
        ])
    
    report_parts.append("") # Spacer

    # --- Footer section (Expiry, Identifier, Status Bar) ---
    expire_days = info.get("expire")
    expire_label = "نامحدود"
    if expire_days is not None:
        expire_label = f"{expire_days} روز" if expire_days >= 0 else "منقضی شده"
    report_parts.append(f"📅 انقضا: {escape_markdown(expire_label)}")
    
    if h_info:
        report_parts.append(f"🔑 شناسه یکتا: `{escape_markdown(info.get('uuid'))}`")
    elif m_info:
        report_parts.append(f"👤 یوزرنیم: `{escape_markdown(info.get('name'))}`")

    # FIX: The progress bar function now handles its own formatting.
    # This robustly prevents the 'parse entities' error.
    usage_percentage = info.get('usage_percentage', 0)
    status_bar_line = create_progress_bar(usage_percentage) # Get the fully formatted bar
    report_parts.append(f"\nوضعیت : {status_bar_line}")

    return "\n".join(report_parts)