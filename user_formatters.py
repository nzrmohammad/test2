from config import EMOJIS, PAGE_SIZE
from database import db
from api_handler import api_handler
import jdatetime
from utils import (
    create_progress_bar, persian_date,
    format_daily_usage, escape_markdown,
    load_service_plans
)

def fmt_one(info: dict, daily_usage_dict: dict) -> str:
    if not info:
        return "❌ خطا در دریافت اطلاعات"
    
    name = escape_markdown(info.get("name", "کاربر ناشناس"))
    bar = create_progress_bar(info.get("usage_percentage", 0))
    status_emoji = "🟢" if info.get("is_active") else "🔴"
    status_text = "فعال" if info.get("is_active") else "غیرفعال"
    
    total_usage = f"{info.get('current_usage_GB', 0):.2f}"
    limit = f"{info.get('usage_limit_GB', 0):.2f}"
    remaining = f"{info.get('remaining_GB', 0):.2f}"
    uuid = info.get('uuid', '')
    
    overall_last_online = persian_date(info.get('last_online'))
    
    total_daily_gb = daily_usage_dict.get('hiddify', 0.0) + daily_usage_dict.get('marzban', 0.0)
    total_daily_str = format_daily_usage(total_daily_gb)
    
    expire_days = info.get("expire")
    expire_label = "نامحدود"
    if expire_days is not None:
        expire_label = f"{expire_days} روز" if expire_days >= 0 else "منقضی شده"
        
    report = (
        f"{EMOJIS['user']} *{name}* ({status_emoji} {status_text})\n"
        f"`{bar}`\n\n"
        f"{EMOJIS['chart']} *مجموع مصرف کل:* `{total_usage} / {limit} GB`\n"
        f"{EMOJIS['download']} *مجموع باقیمانده:* `{remaining} GB`\n"
        f"{EMOJIS['lightning']} *مجموع مصرف امروز:* `{escape_markdown(total_daily_str)}`"
    )

    if 'breakdown' in info:
        report += "\n\n" + "─" * 15 + "\n*جزئیات سرورها:*"
        
        if 'hiddify' in info['breakdown']:
            h_breakdown = info['breakdown']['hiddify']
            h_usage = h_breakdown.get('usage', 0.0)
            h_limit = h_breakdown.get('limit', 0.0)
            h_daily_str = format_daily_usage(daily_usage_dict.get('hiddify', 0.0))
            report += (
                f"\n`•` *آلمان 🇩🇪:* `{h_usage:.2f} / {h_limit:.2f} GB`"
                f"\n  *مصرف امروز:* `{escape_markdown(h_daily_str)}`"
            )
            if h_breakdown.get('last_online'):
                h_online = persian_date(h_breakdown.get('last_online'))
                report += f"\n  *آخرین اتصال:* `{escape_markdown(h_online)}`"

        if 'marzban' in info['breakdown']:
            m_breakdown = info['breakdown']['marzban']
            m_usage = m_breakdown.get('usage', 0.0)
            m_limit = m_breakdown.get('limit', 0.0)
            m_daily_str = format_daily_usage(daily_usage_dict.get('marzban', 0.0))
            report += (
                f"\n`•` *فرانسه 🇫🇷:* `{m_usage:.2f} / {m_limit:.2f} GB`"
                f"\n  *مصرف امروز:* `{escape_markdown(m_daily_str)}`"
            )
            if m_breakdown.get('last_online'):
                m_online = persian_date(m_breakdown.get('last_online'))
                report += f"\n  *آخرین اتصال:* `{escape_markdown(m_online)}`"

    report += f"\n\n{EMOJIS['calendar']} *انقضا:* `{escape_markdown(expire_label)}`\n"
    if info.get('last_online'):
        report += f"{EMOJIS['time']} *آخرین اتصال کلی:* `{escape_markdown(overall_last_online)}`\n"
    report += f"{EMOJIS['key']} *UUID:* `{escape_markdown(uuid)}`"
               
    return report

def quick_stats(uuid_rows: list, page: int = 0) -> tuple[str, dict]:
    num_uuids = len(uuid_rows)
    menu_data = {
        "num_accounts": num_uuids,
        "current_page": 0
    }
    if num_uuids == 0:
        return "هیچ اکانتی ثبت نشده است\\.", menu_data

    current_page = max(0, min(page, num_uuids - 1))
    menu_data["current_page"] = current_page
    
    target_row = uuid_rows[current_page]
    uuid_str = target_row['uuid']
    uuid_id = target_row['id']
    
    info = api_handler.user_info(uuid_str)
    
    if not info:
        return f"❌ خطا در دریافت اطلاعات برای اکانت در صفحه {current_page + 1}", menu_data

    daily_usage_dict = db.get_usage_since_midnight(uuid_id)
    name_escaped = escape_markdown(info.get("name", "کاربر ناشناس"))

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
        f"*آمار اکانت {current_page + 1} از {num_uuids} ({name_escaped})*\n\n"
        
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
    
    return report, menu_data

def fmt_user_report(user_infos: list) -> str:
    if not user_infos:
        return "شما اکانت فعالی برای گزارش‌گیری ندارید."
    
    total_daily = 0.0
    accounts_details = []
    
    for info in user_infos:
        daily_usage_dict = db.get_usage_since_midnight(info['db_id'])
        daily_usage_sum = sum(daily_usage_dict.values())
        total_daily += daily_usage_sum
        
        name = escape_markdown(info.get("name", "کاربر ناشناس"))
        usage_str = f"`{info.get('current_usage_GB', 0):.2f} / {info.get('usage_limit_GB', 0):.2f} GB`"
        
        expire_days = info.get("expire")
        expire_str = "`نامحدود`"
        if expire_days is not None:
            expire_str = f"`{expire_days} روز`" if expire_days >= 0 else "`منقضی شده`"
        
        daily_usage_str = f"`{escape_markdown(format_daily_usage(daily_usage_sum))}`"
            
        accounts_details.append(
            f"{EMOJIS['user']} *اکانت: {name}*\n"
            f"`  `{EMOJIS['chart']} *مصرف کل:* {usage_str}\n"
            f"`  `{EMOJIS['lightning']} *مصرف امروز:* {daily_usage_str}\n"
            f"`  `{EMOJIS['calendar']} *انقضا:* {expire_str}"
        )

    if not accounts_details:
        return "اطلاعات هیچ یک از اکانت‌های شما دریافت نشد."
    
    report_body = "\n\n".join(accounts_details)
    total_daily_str = escape_markdown(format_daily_usage(total_daily))
    return f"{report_body}\n\n{EMOJIS['lightning']} *مجموع مصرف امروز شما:* `{total_daily_str}`"

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