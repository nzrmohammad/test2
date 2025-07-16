import pytz
from config import EMOJIS, PAGE_SIZE
from database import db
from api_handler2 import api_handler
import jdatetime
from datetime import datetime
from utils import (
    create_progress_bar, persian_date,
    format_daily_usage, escape_markdown,
    load_service_plans
)

def fmt_one(info: dict, daily_usage_dict: dict) -> str:
    """
    اطلاعات اکانت را با تاریخ شمسی و ساعت تهران قالب‌بندی می‌کند.
    """
    if not info:
        return "❌ خطا در دریافت اطلاعات"
    
    # --- ۱. آماده‌سازی متغیرها ---
    name = escape_markdown(info.get("name", "کاربر ناشناس"))
    status_emoji = "🟢" if info.get("is_active") else "🔴"
    status_text = "فعال" if info.get("is_active") else "غیرفعال"
    
    # آمار کلی
    total_limit_gb = f"{info.get('usage_limit_GB', 0):.2f} GB"
    total_usage_gb = f"{info.get('current_usage_GB', 0):.2f} GB"
    total_remaining_gb = f"{info.get('remaining_GB', 0):.2f} GB"
    total_daily_gb_val = sum(daily_usage_dict.values())
    total_daily_gb_str = format_daily_usage(total_daily_gb_val)

    # آمار سرور آلمان (Hiddify)
    h_limit_str = f"{info.get('breakdown', {}).get('hiddify', {}).get('limit', 0.0):.2f} GB"
    h_usage_str = f"{info.get('breakdown', {}).get('hiddify', {}).get('usage', 0.0):.2f} GB"
    h_daily_str = format_daily_usage(daily_usage_dict.get('hiddify', 0.0))
    # ---> تغییر اصلی: استفاده از تابع جدید برای فرمت تاریخ و زمان
    h_last_online = format_shamsi_tehran_datetime(info.get('breakdown', {}).get('hiddify', {}).get('last_online'))
    
    # آمار سرور فرانسه (Marzban)
    m_limit_str = f"{info.get('breakdown', {}).get('marzban', {}).get('limit', 0.0):.2f} GB"
    m_usage_str = f"{info.get('breakdown', {}).get('marzban', {}).get('usage', 0.0):.2f} GB"
    m_daily_str = format_daily_usage(daily_usage_dict.get('marzban', 0.0))
    # ---> تغییر اصلی: استفاده از تابع جدید برای فرمت تاریخ و زمان
    m_last_online = format_shamsi_tehran_datetime(info.get('breakdown', {}).get('marzban', {}).get('last_online'))

    # آمار پایانی
    expire_days = info.get("expire")
    expire_label = "نامحدود"
    if expire_days is not None:
        expire_label = f"{expire_days} روز"
    
    escaped_expire_label = escape_markdown(expire_label)
    uuid = escape_markdown(info.get('uuid', ''))
    
    usage_percentage = info.get("usage_percentage", 0)
    bar = create_progress_bar(usage_percentage) 

    # --- ۲. ساخت گزارش نهایی ---
    report = f"""{EMOJIS['user']} *نام :* {name} \\({status_emoji} {status_text}\\)

{EMOJIS['database']} *مجموع حجم :* `{total_limit_gb}`
{EMOJIS['fire']} *مجموع مصرف شده :* `{total_usage_gb}`
{EMOJIS['download']} *مجموع باقیمانده:* `{total_remaining_gb}`
{EMOJIS['lightning']} *مجموع مصرف امروز:* `{total_daily_gb_str}`

*جزئیات سرورها*

*آلمان* 🇩🇪
{EMOJIS['database']} مجموع حجم : `{h_limit_str}`
{EMOJIS['fire']} مجموع مصرف شده : `{h_usage_str}`
{EMOJIS['lightning']} مصرف امروز : `{h_daily_str}`
{EMOJIS['time']} آخرین اتصال : `{h_last_online}`

*فرانسه* 🇫🇷
{EMOJIS['database']} مجموع حجم : `{m_limit_str}`
{EMOJIS['fire']} مجموع مصرف شده : `{m_usage_str}`
{EMOJIS['lightning']} مصرف امروز : `{m_daily_str}`
{EMOJIS['time']} آخرین اتصال : `{m_last_online}`

{EMOJIS['calendar']} *انقضا:* `{escaped_expire_label}`
{EMOJIS['key']} *شناسه یکتا:* `{uuid}`

*وضعیت :* {bar}"""
               
    return report


def quick_stats(uuid_rows: list, page: int = 0) -> tuple[str, dict]:
    # This function is kept for "Quick Stats" button logic, but its format can be updated if needed.
    # The current implementation is already safe.
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

    limit_h_str = escape_markdown(f"{info.get('breakdown', {}).get('hiddify', {}).get('limit', 0.0):.2f}")
    limit_m_str = escape_markdown(f"{info.get('breakdown', {}).get('marzban', {}).get('limit', 0.0):.2f}")
    limit_total_str = escape_markdown(f"{info.get('usage_limit_GB', 0.0):.2f}")
    usage_h_str = escape_markdown(f"{info.get('breakdown', {}).get('hiddify', {}).get('usage', 0.0):.2f}")
    usage_m_str = escape_markdown(f"{info.get('breakdown', {}).get('marzban', {}).get('usage', 0.0):.2f}")
    usage_total_str = escape_markdown(f"{info.get('current_usage_GB', 0.0):.2f}")
    remaining_h = max(0, info.get('breakdown', {}).get('hiddify', {}).get('limit', 0.0) - info.get('breakdown', {}).get('hiddify', {}).get('usage', 0.0))
    remaining_m = max(0, info.get('breakdown', {}).get('marzban', {}).get('limit', 0.0) - info.get('breakdown', {}).get('marzban', {}).get('usage', 0.0))
    remaining_h_str = escape_markdown(f"{remaining_h:.2f}")
    remaining_m_str = escape_markdown(f"{remaining_m:.2f}")
    remaining_total_str = escape_markdown(f"{info.get('remaining_GB', 0.0):.2f}")
    daily_h_str = escape_markdown(format_daily_usage(daily_usage_dict.get('hiddify', 0.0)))
    daily_m_str = escape_markdown(format_daily_usage(daily_usage_dict.get('marzban', 0.0)))
    daily_total_str = escape_markdown(format_daily_usage(sum(daily_usage_dict.values())))

    report = f"""*آمار اکانت {current_page + 1} از {num_uuids} \\({name_escaped}\\)*

*{EMOJIS['database']} حجم کل*
`آلمان` 🇩🇪 : `{limit_h_str} GB`
`فرانسه` 🇫🇷: `{limit_m_str} GB`
*مجموع :* `{limit_total_str} GB`

*{EMOJIS['fire']} مجموع مصرف*
`آلمان` 🇩🇪 : `{usage_h_str} GB`
`فرانسه` 🇫🇷: `{usage_m_str} GB`
*مجموع :* `{usage_total_str} GB`

*{EMOJIS['download']} مجموع باقیمانده*
`آلمان` 🇩🇪 : `{remaining_h_str} GB`
`فرانسه` 🇫🇷: `{remaining_m_str} GB`
*مجموع :* `{remaining_total_str} GB`

*{EMOJIS['lightning']} مصرف امروز*
`آلمان` 🇩🇪 : `{daily_h_str}`
`فرانسه` 🇫🇷: `{daily_m_str}`
*مجموع :* `{daily_total_str}`"""
    
    return report, menu_data

def fmt_user_report(user_infos: list) -> str:
    if not user_infos:
        return "شما اکانت فعالی برای گزارش‌گیری ندارید."
    
    total_daily_hiddify, total_daily_marzban = 0.0, 0.0
    accounts_details = []
    
    for info in user_infos:
        daily_usage_dict = db.get_usage_since_midnight(info['db_id'])
        h_daily = daily_usage_dict.get('hiddify', 0.0)
        m_daily = daily_usage_dict.get('marzban', 0.0)
        
        total_daily_hiddify += h_daily
        total_daily_marzban += m_daily
        
        name = escape_markdown(info.get("name", "کاربر ناشناس"))
        usage_str = f"`{escape_markdown(f'{info.get("current_usage_GB", 0):.2f}')} GB / {escape_markdown(f'{info.get("usage_limit_GB", 0):.2f}')} GB`"
        
        expire_days = info.get("expire")
        expire_str = "`نامحدود`"
        if expire_days is not None:
            expire_str = f"`{expire_days} روز`" if expire_days >= 0 else "`منقضی شده`"
        
        # بخش جدید برای نمایش تفکیک مصرف روزانه
        daily_breakdown = []
        if 'hiddify' in info.get('breakdown', {}):
            daily_breakdown.append(f"`  `🇩🇪 *مصرف امروز آلمان:* `{escape_markdown(format_daily_usage(h_daily))}`")
        if 'marzban' in info.get('breakdown', {}):
            daily_breakdown.append(f"`  `🇫🇷 *مصرف امروز فرانسه:* `{escape_markdown(format_daily_usage(m_daily))}`")
            
        accounts_details.append(
            f"{EMOJIS['user']} *اکانت: {name}*\n"
            f"`  `{EMOJIS['chart']} *مصرف کل:* {usage_str}\n"
            + "\n".join(daily_breakdown) +
            f"\n`  `{EMOJIS['calendar']} *انقضا:* {expire_str}"
        )

    if not accounts_details:
        return "اطلاعات هیچ یک از اکانت‌های شما دریافت نشد."
    
    report_body = "\n\n".join(accounts_details)
    total_daily_all = total_daily_hiddify + total_daily_marzban
    
    # بخش جدید برای نمایش مجموع مصرف روزانه به تفکیک
    footer = [
        f"\n{EMOJIS['lightning']} *مجموع کل مصرف امروز شما:* `{escape_markdown(format_daily_usage(total_daily_all))}`",
        f"`  `🇩🇪 مجموع آلمان: `{escape_markdown(format_daily_usage(total_daily_hiddify))}`",
        f"`  `🇫🇷 مجموع فرانسه: `{escape_markdown(format_daily_usage(total_daily_marzban))}`"
    ]
    
    return f"{report_body}\n\n" + "\n".join(footer)

def fmt_service_plans() -> str:
    """
    Formats the service plans with the requested layout including country names.
    """
    SERVICE_PLANS = load_service_plans()
    if not SERVICE_PLANS:
        return "در حال حاضر پلن فعالی برای نمایش وجود ندارد\\."
    
    lines = [f"*{EMOJIS['rocket']} پلن‌های فروش سرویس*"]
    
    for plan in SERVICE_PLANS:
        lines.append("`────────────────────`")
        lines.append(f"*{escape_markdown(plan['name'])}*")
        lines.append(f"حجم کل: *{escape_markdown(plan['total_volume'])}*")
        lines.append(f"آلمان : *{escape_markdown(plan['volume_de'])}*")
        lines.append(f"فرانسه : *{escape_markdown(plan['volume_fr'])}*")
        lines.append(f"مدت زمان: *{escape_markdown(plan['duration'])}*")
                
    lines.append("`────────────────────`")
    lines.append(escape_markdown("نکته : حجم 🇫🇷 قابل تبدیل به 🇩🇪 هست ولی 🇩🇪 قابل تبدیل به 🇫🇷 نیست"))
    lines.append(escape_markdown("برای اطلاع از قیمت‌ها و دریافت مشاوره، لطفاً به ادمین پیام دهید."))
    
    return "\n".join(lines)

def fmt_panel_quick_stats(panel_name: str, stats: dict) -> str:    
    title = f"*{escape_markdown(f'📊 آمار مصرف سرور {panel_name}')}*"
    
    lines = [title, ""]
    if not stats:
        lines.append("اطلاعاتی برای نمایش وجود ندارد\\.")
        return "\n".join(lines)
        
    for hours, usage_gb in stats.items():
        usage_str = format_daily_usage(usage_gb)
        lines.append(f"`• {hours}` ساعت گذشته: `{escape_markdown(usage_str)}`")
        
    return "\n".join(lines)




def format_shamsi_tehran_datetime(dt_obj: datetime | None) -> str:
    """
    یک شیء datetime با منطقه زمانی UTC دریافت کرده و آن را به تاریخ شمسی 
    و ساعت به وقت تهران تبدیل می‌کند. اگر ورودی معتبر نباشد، 'هرگز' برمی‌گرداند.
    """
    if not dt_obj:
        return "هرگز"
    
    # اطمینان از اینکه شیء ورودی دارای منطقه زمانی است (پیش‌فرض UTC)
    if dt_obj.tzinfo is None:
        dt_obj = pytz.utc.localize(dt_obj)

    # تبدیل به منطقه زمانی تهران
    tehran_tz = pytz.timezone('Asia/Tehran')
    tehran_dt = dt_obj.astimezone(tehran_tz)
    
    # تبدیل تاریخ میلادی به شمسی
    shamsi_date = jdatetime.date.fromgregorian(date=tehran_dt)
    
    # قالب‌بندی خروجی به صورت 'YYYY/MM/DD - HH:MM'
    return f"{shamsi_date.strftime('%Y/%m/%d')} - {tehran_dt.strftime('%H:%M')}"