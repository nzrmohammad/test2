import pytz
from datetime import datetime, timedelta
from config import EMOJIS, PAGE_SIZE
from database import db
from api_handler import api_handler
import jdatetime
from utils import (
    create_progress_bar, persian_date,
    format_daily_usage, escape_markdown,
    format_relative_time, load_service_plans
)

def fmt_one(info: dict, daily_usage_dict: dict) -> str:
    if not info: return "❌ خطا در دریافت اطلاعات"
    
    name = escape_markdown(info.get("name", "کاربر ناشناس"))
    bar = create_progress_bar(info.get("usage_percentage", 0))
    status_emoji = "🟢" if info.get("is_active") else "🔴"
    status_text = "فعال" if info.get("is_active") else "غیرفعال"
    
    total_usage = escape_markdown(f"{info.get('current_usage_GB', 0):.2f}")
    limit = escape_markdown(f"{info.get('usage_limit_GB', 0):.2f}")
    remaining = escape_markdown(f"{info.get('remaining_GB', 0):.2f}")
    uuid = escape_markdown(info.get('uuid', ''))
    
    overall_last_online = persian_date(info.get('last_online'))
    
    # --- شروع تغییر ---
    # مجموع مصرف روزانه را از دیکشنری ورودی محاسبه می‌کنیم
    total_daily_gb = daily_usage_dict.get('hiddify', 0.0) + daily_usage_dict.get('marzban', 0.0)
    total_daily_str = format_daily_usage(total_daily_gb)
    # --- پایان تغییر ---
    
    expire_days = info.get("expire")
    expire_label = "نامحدود"
    if expire_days is not None:
        expire_label = f"{expire_days} روز" if expire_days >= 0 else "منقضی شده"
        
    report = (f"{EMOJIS['user']} *{name}* \\({status_emoji} {status_text}\\)\n`{bar}`\n\n"
              f"{EMOJIS['chart']} *مجموع مصرف کل:* `{total_usage} / {limit} GB`\n"
              f"{EMOJIS['download']} *مجموع باقیمانده:* `{remaining} GB`\n"
              f"{EMOJIS['lightning']} *مجموع مصرف امروز:* `{escape_markdown(total_daily_str)}`")

    if 'breakdown' in info:
        report += "\n\n" + "─" * 15 + "\n*جزئیات سرورها:*"
        
        # سرور آلمان (Hiddify)
        h_breakdown = info['breakdown']['hiddify']
        h_usage = h_breakdown['usage']
        h_limit = h_breakdown['limit']
        h_daily_str = format_daily_usage(daily_usage_dict.get('hiddify', 0.0))
        report += (f"\n`•` *آلمان 🇩🇪:* `{h_usage:.2f} / {h_limit:.2f} GB`"
                   f"\n  *مصرف امروز:* {escape_markdown(h_daily_str)}")
        if h_breakdown.get('last_online'):
            h_online = persian_date(h_breakdown.get('last_online'))
            report += f"\n  *آخرین اتصال:* {escape_markdown(h_online)}"

        # سرور فرانسه (Marzban)
        if 'marzban' in info['breakdown']:
            m_breakdown = info['breakdown']['marzban']
            m_usage = m_breakdown['usage']
            m_limit = m_breakdown['limit']
            m_daily_str = format_daily_usage(daily_usage_dict.get('marzban', 0.0))
            report += (f"\n`•` *فرانسه 🇫🇷:* `{m_usage:.2f} / {m_limit:.2f} GB`"
                       f"\n  *مصرف امروز:* {escape_markdown(m_daily_str)}")
            if m_breakdown.get('last_online'):
                m_online = persian_date(m_breakdown.get('last_online'))
                report += f"\n  *آخرین اتصال:* {escape_markdown(m_online)}"

    report += (f"\n\n{EMOJIS['calendar']} *انقضا:* {escape_markdown(expire_label)}\n")
    if info.get('last_online'):
        report += f"{EMOJIS['time']} *آخرین اتصال کلی:* {escape_markdown(overall_last_online)}\n"
    report += f"{EMOJIS['key']} *UUID:* `{uuid}`"
               
    return report

def fmt_users_list(users: list, list_type: str, page: int) -> str:
    title_map = {
        'active': "✅ کاربران فعال (۲۴ ساعت اخیر)",
        'inactive': "⏳ کاربران غیرفعال (۱ تا ۷ روز)",
        'never_connected': "🚫 کاربرانی که هرگز متصل نشده‌اند"
    }
    title = title_map.get(list_type, "لیست کاربران")
    
    if not users:
        return f"*{escape_markdown(title)}*\n\nهیچ کاربری در این دسته یافت نشد\\."

    lines = [f"*{escape_markdown(title)}*"]
    if len(users) > PAGE_SIZE:
        total_pages = (len(users) + PAGE_SIZE - 1) // PAGE_SIZE
        lines.append(f"\\(صفحه {page + 1} از {total_pages} \\| کل: {len(users)}\\)")

    start_index = page * PAGE_SIZE
    paginated_users = users[start_index : start_index + PAGE_SIZE]

    for user in paginated_users:
        name = escape_markdown(user.get('name', 'کاربر ناشناس'))
        line = f"`•` *{name}*"
        
        if list_type == 'active':
            last_online_str = persian_date(user.get('last_online')).split(' - ')[-1] # فقط ساعت
            usage_p = user.get('usage_percentage', 0)
            line += f" `|` Last Seen: `{last_online_str}` `|` Usage: `{usage_p:.1f}%`"

        elif list_type == 'inactive':
            last_online_str = format_relative_time(user.get('last_online'))
            status = "Expired" if user.get('expire', 0) < 0 else "Active"
            line += f" `|` Last Seen: `{last_online_str}` `|` Status: `{status}`"
            
        elif list_type == 'never_connected':
            created_at_str = format_relative_time(user.get('created_at'))
            limit_gb = user.get('usage_limit_GB', 0)
            line += f" `|` Registered: `{created_at_str}` `|` Limit: `{limit_gb} GB`"
            
        lines.append(line)
        
    return "\n".join(lines)

def fmt_online_users_list(users: list, page: int) -> str:
    # --- مشکل اینجا بود و برطرف شد ---
    title = "⚡️ کاربران آنلاین (۳ دقیقه اخیر)"
    # ---------------------------------
    
    if not users:
        return f"*{escape_markdown(title)}*\n\nهیچ کاربری در این لحظه آنلاین نیست."

    uuid_to_bot_user = db.get_uuid_to_bot_user_map()
    header_lines = [f"*{escape_markdown(title)}*"]
    if len(users) > PAGE_SIZE:
        total_pages = (len(users) + PAGE_SIZE - 1) // PAGE_SIZE
        page_info_text = f"(صفحه {page + 1} از {total_pages} | کل: {len(users)})"
        header_lines.append(escape_markdown(page_info_text))

    paginated_users = users[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    user_lines = []

    for user in paginated_users:
        panel_name_raw = user.get('name', 'کاربر ناشناس')
        bot_user_info = uuid_to_bot_user.get(user.get('uuid'))
        
        name_str = escape_markdown(panel_name_raw)

        if bot_user_info and bot_user_info.get('user_id'):
            user_id = bot_user_info['user_id']
            name_str = f"[{panel_name_raw}](tg://user?id={user_id})"

        daily_usage_output = escape_markdown(format_daily_usage(user.get('daily_usage_GB', 0)))
        expire_days = user.get("expire")
        expire_text = "Unlimited"
        if expire_days is not None:
            expire_text = f"{expire_days} Days" if expire_days >= 0 else "Expired"
        expire_output = escape_markdown(expire_text)
        
        line = f"{name_str} \\| {daily_usage_output} \\| {expire_output}"
        user_lines.append(line)

    header_text = "\n".join(header_lines)
    body_text = "\n".join(user_lines)
    return f"{header_text}\n\n{body_text}"

def quick_stats(uuid_rows: list, page: int = 0) -> tuple[str, dict]:
    num_uuids = len(uuid_rows)
    menu_data = {
        "num_accounts": num_uuids,
        "current_page": 0
    }
    if num_uuids == 0:
        return "هیچ اکانتی ثبت نشده است.", menu_data

    current_page = max(0, min(page, num_uuids - 1))
    menu_data["current_page"] = current_page
    
    target_row = uuid_rows[current_page]
    uuid_str = target_row['uuid']
    uuid_id = target_row['id']
    
    info = api_handler.user_info(uuid_str)
    
    if not info:
        return f"❌ خطا در دریافت اطلاعات برای اکانت در صفحه {current_page + 1}", menu_data

    daily_usage_dict = db.get_usage_since_midnight(uuid_id)
    name = escape_markdown(info.get("name", "کاربر ناشناس"))
    
    # --- START OF FINAL FIX ---
    # Pre-format all numbers to strings first, then escape them.
    # This is the most reliable way to handle the '.' character.

    # Volume Stats
    limit_h_str = escape_markdown(f"{info.get('breakdown', {}).get('hiddify', {}).get('limit', 0.0):.2f}")
    limit_m_str = escape_markdown(f"{info.get('breakdown', {}).get('marzban', {}).get('limit', 0.0):.2f}")
    limit_total_str = escape_markdown(f"{info.get('usage_limit_GB', 0.0):.2f}")

    # Usage Stats
    usage_h_str = escape_markdown(f"{info.get('breakdown', {}).get('hiddify', {}).get('usage', 0.0):.2f}")
    usage_m_str = escape_markdown(f"{info.get('breakdown', {}).get('marzban', {}).get('usage', 0.0):.2f}")
    usage_total_str = escape_markdown(f"{info.get('current_usage_GB', 0.0):.2f}")

    # Remaining Stats
    remaining_h = max(0, info.get('breakdown', {}).get('hiddify', {}).get('limit', 0.0) - info.get('breakdown', {}).get('hiddify', {}).get('usage', 0.0))
    remaining_m = max(0, info.get('breakdown', {}).get('marzban', {}).get('limit', 0.0) - info.get('breakdown', {}).get('marzban', {}).get('usage', 0.0))
    remaining_h_str = escape_markdown(f"{remaining_h:.2f}")
    remaining_m_str = escape_markdown(f"{remaining_m:.2f}")
    remaining_total_str = escape_markdown(f"{info.get('remaining_GB', 0.0):.2f}")
    
    # Daily Usage Stats
    daily_h_str = escape_markdown(format_daily_usage(daily_usage_dict.get('hiddify', 0.0)))
    daily_m_str = escape_markdown(format_daily_usage(daily_usage_dict.get('marzban', 0.0)))
    daily_total_str = escape_markdown(format_daily_usage(sum(daily_usage_dict.values())))

    report = (
        f"*آمار اکانت {current_page + 1} از {num_uuids} \\({name}\\)*\n\n"
        
        f"*{EMOJIS['database']} حجم کل*\n"
        f"آلمان 🇩🇪 : `{limit_h_str} GB`\n"
        f"فرانسه 🇫🇷: `{limit_m_str} GB`\n"
        f"*مجموع :* `{limit_total_str} GB`\n\n"

        f"*{EMOJIS['chart']} مجموع مصرف*\n"
        f"آلمان 🇩🇪 : `{usage_h_str} GB`\n"
        f"فرانسه 🇫🇷: `{usage_m_str} GB`\n"
        f"*مجموع :* `{usage_total_str} GB`\n\n"

        f"*{EMOJIS['download']} مجموع باقیمانده*\n"
        f"آلمان 🇩🇪 : `{remaining_h_str} GB`\n"
        f"فرانسه 🇫🇷: `{remaining_m_str} GB`\n"
        f"*مجموع :* `{remaining_total_str} GB`\n\n"
        
        f"*{EMOJIS['lightning']} مصرف امروز*\n"
        f"آلمان 🇩🇪 : `{daily_h_str}`\n"
        f"فرانسه 🇫🇷: `{daily_m_str}`\n"
        f"*مجموع :* `{daily_total_str}`"
    )
    # --- END OF FINAL FIX ---
    
    return report, menu_data

def fmt_admin_report(all_users_from_api: list, db_manager) -> str:
    if not all_users_from_api:
        return "هیچ کاربری در پنل یافت نشد\\."

    total_usage_all, active_users = 0.0, 0
    # --- شروع تغییر ---
    total_daily_hiddify, total_daily_marzban = 0.0, 0.0
    # --- پایان تغییر ---
    online_users, expiring_soon_users, new_users_today = [], [], []
    
    now_utc = datetime.now(pytz.utc)
    online_deadline = now_utc - timedelta(minutes=3)
    
    db_users_map = {u['uuid']: u.get('created_at') for u in db_manager.all_active_uuids()}

    for user_info in all_users_from_api:
        if user_info.get("is_active"):
            active_users += 1
        total_usage_all += user_info.get("current_usage_GB", 0)
        
        # --- شروع تغییر ---
        daily_usage_dict = db_manager.get_usage_since_midnight_by_uuid(user_info['uuid'])
        total_daily_hiddify += daily_usage_dict.get('hiddify', 0.0)
        total_daily_marzban += daily_usage_dict.get('marzban', 0.0)
        # --- پایان تغییر ---
        
        if user_info.get('is_active') and user_info.get('last_online') and user_info['last_online'].astimezone(pytz.utc) >= online_deadline:
            online_users.append(user_info)

        if user_info.get('expire') is not None and 0 <= user_info['expire'] <= 3:
            expiring_soon_users.append(user_info)
            
        created_at = db_users_map.get(user_info['uuid'])
        if created_at and (now_utc - created_at.astimezone(pytz.utc)).days < 1:
            new_users_today.append(user_info)

    total_daily_all = total_daily_hiddify + total_daily_marzban
    report_lines = [
        f"{EMOJIS['gear']} *خلاصه وضعیت کل پنل*",
        f"\\- {EMOJIS['user']} تعداد کل اکانت‌ها: *{len(all_users_from_api)}*",
        f"\\- {EMOJIS['success']} اکانت‌های فعال: *{active_users}*",
        f"\\- {EMOJIS['wifi']} کاربران آنلاین: *{len(online_users)}*",
        f"\\- {EMOJIS['chart']} *مجموع مصرف کل:* `{escape_markdown(f'{total_usage_all:.2f}')} GB`",
        f"\\- {EMOJIS['lightning']} *مصرف امروز کل:* `{escape_markdown(format_daily_usage(total_daily_all))}`"
    ]

    if online_users:
        report_lines.append("\n" + "─" * 20 + f"\n*{EMOJIS['wifi']} کاربران آنلاین و مصرف امروزشان:*")
        online_users.sort(key=lambda u: u.get('name', ''))
        for user in online_users:
            # --- شروع تغییر ---
            daily_dict = db_manager.get_usage_since_midnight_by_uuid(user['uuid'])
            daily_total = sum(daily_dict.values())
            # --- پایان تغییر ---
            user_name = escape_markdown(user.get('name', 'کاربر ناشناس'))
            usage_str = escape_markdown(format_daily_usage(daily_total))
            report_lines.append(f"`•` *{user_name}:* `{usage_str}`")

    if expiring_soon_users:
        report_lines.append("\n" + "─" * 20 + f"\n*{EMOJIS['warning']} کاربرانی که به زودی منقضی می‌شوند (تا ۳ روز):*")
        expiring_soon_users.sort(key=lambda u: u.get('expire', 99))
        for user in expiring_soon_users:
            name = escape_markdown(user['name'])
            days = user['expire']
            report_lines.append(f"`•` *{name}:* `{days} روز باقیمانده`")

    if new_users_today:
        report_lines.append("\n" + "─" * 20 + f"\n*{EMOJIS['star']} کاربران جدید (۲۴ ساعت اخیر):*")
        for user in new_users_today:
            name = escape_markdown(user['name'])
            report_lines.append(f"`•` *{name}*")

    return "\n".join(report_lines)

def fmt_user_report(user_infos: list) -> str:
    """Formats a daily report for a user, including individual daily usage."""
    if not user_infos: return "شما اکانت فعالی برای گزارش‌گیری ندارید\\."
    
    total_daily = 0.0
    accounts_details = []
    
    for info in user_infos:
        # دیگر نیازی به user_info(row['uuid']) نیست
        
        # برای get_usage_since_midnight به id از جدول user_uuids نیاز داریم
        # که در scheduler به دیکشنری info اضافه کردیم
        daily_usage = db.get_usage_since_midnight(info['db_id'])
        total_daily += daily_usage
        name = escape_markdown(info.get("name", "کاربر ناشناس"))
        
        usage_str = f"`{escape_markdown(f'{info.get("current_usage_GB", 0):.2f}')} / {escape_markdown(f'{info.get("usage_limit_GB", 0):.2f}')} GB`"
        
        expire_days = info.get("expire")
        expire_str = "نامحدود"
        if expire_days is not None:
            expire_str = f"`{expire_days} روز`" if expire_days >= 0 else "`منقضی شده`"
        
        daily_usage_str = escape_markdown(format_daily_usage(daily_usage))
            
        accounts_details.append(
            f"{EMOJIS['user']} *اکانت: {name}*\n"
            f"`  `{EMOJIS['chart']} *مصرف کل:* {usage_str}\n"
            f"`  `{EMOJIS['lightning']} *مصرف امروز:* `{daily_usage_str}`\n"
            f"`  `{EMOJIS['calendar']} *انقضا:* {expire_str}"
        )

    if not accounts_details: return "اطلاعات هیچ یک از اکانت‌های شما دریافت نشد\\."
    
    report_body = "\n\n".join(accounts_details)
    return f"{report_body}\n\n{EMOJIS['lightning']} *مجموع مصرف امروز شما:* `{escape_markdown(format_daily_usage(total_daily))}`"

def fmt_hiddify_panel_info(info: dict) -> str:
    """Formats the panel health check info with emojis."""
    if not info: return "اطلاعاتی از پنل دریافت نشد\\."
    
    title = escape_markdown(info.get('title', 'N/A'))
    description = escape_markdown(info.get('description', 'N/A'))
    version = escape_markdown(info.get('version', 'N/A'))
    
    return (f"{EMOJIS['gear']} *اطلاعات پنل Hiddify*\n\n"
            f"**عنوان:** {title}\n"
            f"**توضیحات:** {description}\n"
            f"**نسخه:** {version}\n")

def fmt_top_consumers(users: list, page: int) -> str:
    """Formats a paginated list of top consumers in text format."""
    title = "پرمصرف‌ترین کاربران"
    if not users:
        return f"🏆 *{escape_markdown(title)}*\n\nهیچ کاربری برای نمایش وجود ندارد\\."

    header_lines = [f"🏆 *{escape_markdown(title)}*"]
    if len(users) > PAGE_SIZE:
        total_pages = (len(users) + PAGE_SIZE - 1) // PAGE_SIZE
        header_lines.append(f"\\(صفحه {page + 1} از {total_pages} \\| کل: {len(users)}\\)")

    paginated_users = users[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    user_lines = []

    for i, user in enumerate(paginated_users, start=page * PAGE_SIZE + 1):
        name = escape_markdown(user.get('name', 'کاربر ناشناس'))
        usage = user.get('current_usage_GB', 0)
        limit = user.get('usage_limit_GB', 0)
        usage_str = f"`{usage:.2f} GB / {limit:.2f} GB`"
        line = f"`{i}.` *{name}* `|` {EMOJIS['chart']} {usage_str}"
        user_lines.append(line)

    header_text = "\n".join(header_lines)
    body_text = "\n".join(user_lines)

    return f"{header_text}\n\n{body_text}"

def fmt_bot_users_list(bot_users: list, page: int) -> str:
    title = "کاربران ربات"
    if not bot_users:
        return f"🤖 *{escape_markdown(title)}*\n\nهیچ کاربری در ربات ثبت‌نام نکرده است\\."

    lines = [f"🤖 *{escape_markdown(title)}*"]
    total_users = len(bot_users)

    if total_users > PAGE_SIZE:
        total_pages = (total_users + PAGE_SIZE - 1) // PAGE_SIZE
        lines.append(f"\\(صفحه {page + 1} از {total_pages} \\| کل: {total_users}\\)")

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
    
    lines = [f"🎂 *{escape_markdown(title)}* \\(مرتب شده بر اساس ماه\\)"]

    if len(users) > PAGE_SIZE:
        total_pages = (len(users) + PAGE_SIZE - 1) // PAGE_SIZE
        lines.append(f"\\(صفحه {page + 1} از {total_pages} \\| کل: {len(users)}\\)")

    start_index = page * PAGE_SIZE
    paginated_users = users[start_index : start_index + PAGE_SIZE]

    for user in paginated_users:
        name = escape_markdown(user.get('first_name', 'کاربر ناشناس'))
        
        gregorian_date = user['birthday']
        
        shamsi_date = jdatetime.date.fromgregorian(date=gregorian_date)
        shamsi_str = shamsi_date.strftime('%Y/%m/%d')
        
        gregorian_str = gregorian_date.strftime('%Y-%m-%d')
        
        lines.append(f"`•` *{name}* `|` solar: `{shamsi_str}` `|` lunar: `{gregorian_str}`")
        
    return "\n".join(lines)

def fmt_service_plans() -> str:
    SERVICE_PLANS = load_service_plans()

    if not SERVICE_PLANS:
        return "در حال حاضر پلن فعالی برای نمایش وجود ندارد\\."

    lines = [f"*{EMOJIS['rocket']} پلن‌های فروش سرویس*"]
    
    for plan in SERVICE_PLANS:
        lines.append("\n" + "─" * 20)
        lines.append(f"*{escape_markdown(plan['name'])}*")
        lines.append(f"*حجم کل:{escape_markdown(plan['total_volume'])}*")
        lines.append(f"حجم آلمان:{escape_markdown(plan['volume_de'])}")
        lines.append(f"حجم فرانسه:{escape_markdown(plan['volume_fr'])}")
        lines.append(f"مدت زمان:{escape_markdown(plan['duration'])}")
                
    lines.append("\n" + "─" * 20)
    lines.append("نکته : حجم 🇫🇷 قابل تبدیل به 🇩🇪 هست ولی 🇩🇪 قابل تبدیل به 🇫🇷 نیست")
    lines.append("برای اطلاع از قیمت‌ها و دریافت مشاوره، لطفاً به ادمین پیام دهید\\.")
    return "\n".join(lines)

def fmt_panel_quick_stats(panel_name: str, stats: dict) -> str:    
    title = f"*{escape_markdown(f'📊 آمار مصرف سرور {panel_name}')}*"
    
    lines = [title, ""]
    if not stats:
        lines.append("اطلاعاتی برای نمایش وجود ندارد\\.")
        return "\n".join(lines)
        
    for hours, usage_gb in stats.items():
        usage_str = format_daily_usage(usage_gb)
        lines.append(f"•` {hours}` ساعت گذشته: `{escape_markdown(usage_str)}`")
        
    return "\n".join(lines)

def fmt_marzban_system_stats(info: dict) -> str:
    """Formats the Marzban panel system status information as plain text."""
    if not info:
        return "اطلاعاتی از سیستم دریافت نشد\\."
    
    # --- START OF FIX: Formatting the full system stats ---
    version = info.get('version', 'N/A')
    
    # Memory
    mem_total_gb = info.get('mem_total', 0) / (1024**3)
    mem_used_gb = info.get('mem_used', 0) / (1024**3)
    mem_percent = (mem_used_gb / mem_total_gb * 100) if mem_total_gb > 0 else 0
    
    # CPU
    cpu_cores = info.get('cpu_cores', 'N/A')
    cpu_usage = info.get('cpu_usage', 0.0)
    
    # Users
    total_users = info.get('total_user', 0)
    online_users = info.get('online_users', 0)
    
    # Bandwidth (convert B/s to MB/s)
    up_speed_mbps = info.get('outgoing_bandwidth_speed', 0) / (1024 * 1024)
    down_speed_mbps = info.get('incoming_bandwidth_speed', 0) / (1024 * 1024)

    report = (
        f"وضعیت سیستم پنل مرزبان (فرانسه 🇫🇷)\n"
        f"------------------------------------\n"
        f"نسخه: {version}\n"
        f"------------------------------------\n"
        f"مصرف CPU: {cpu_usage:.1f}% از {cpu_cores} هسته\n"
        f"مصرف RAM: {mem_used_gb:.2f} GB / {mem_total_gb:.2f} GB ({mem_percent:.1f}%)\n"
        f"------------------------------------\n"
        f"تعداد کل کاربران: {total_users}\n"
        f"کاربران آنلاین: {online_users}\n"
        f"------------------------------------\n"
        f"سرعت لحظه‌ای شبکه:\n"
        f"↑ آپلود: {up_speed_mbps:.2f} MB/s\n"
        f"↓ دانلود: {down_speed_mbps:.2f} MB/s"
    )
    return escape_markdown(report)
    # --- END OF FIX ---