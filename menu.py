# menu.py - نسخه کامل و نهایی با ساختار جدید

from telebot import types
from config import EMOJIS, PAGE_SIZE

class Menu:
    # ===============================================
    # متدهای مربوط به کاربر (بدون تغییر در callback)
    # ===============================================

    def main(self, is_admin: bool, has_birthday: bool = False) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton(f"{EMOJIS['key']} مدیریت اکانت", callback_data="manage"),
            types.InlineKeyboardButton(f"{EMOJIS['lightning']} آمار فوری", callback_data="quick_stats")
        )

        btn_services = types.InlineKeyboardButton(f"{EMOJIS['money']} مشاهده سرویس ها", callback_data="view_plans")
        btn_settings = types.InlineKeyboardButton(f"{EMOJIS['bell']} تنظیمات", callback_data="settings")
        btn_birthday = types.InlineKeyboardButton("🎁 هدیه تولد", callback_data="birthday_gift")

        if not has_birthday:
            kb.add(btn_settings, btn_services)
            kb.add(btn_birthday)
        else:
            kb.add(btn_settings, btn_services)

        if is_admin:
            # این بخش صحیح است و از فرمت جدید استفاده می‌کند
            kb.add(types.InlineKeyboardButton(f"{EMOJIS['crown']} پنل مدیریت", callback_data="admin:panel"))
        return kb

    def accounts(self, rows) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=1)
        for r in rows:
            name = r.get('name', 'کاربر ناشناس')
            kb.add(types.InlineKeyboardButton(f"📊 {name}", callback_data=f"acc_{r['id']}"))
        kb.add(types.InlineKeyboardButton("➕ افزودن اکانت جدید", callback_data="add"))
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
        return kb

    @staticmethod
    def quick_stats_server_selection_menu(uuid_id: int) -> types.InlineKeyboardMarkup:
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_hiddify = types.InlineKeyboardButton("آلمان 🇩🇪", callback_data=f"qstats_panel_hiddify_{uuid_id}")
        btn_marzban = types.InlineKeyboardButton("فرانسه 🇫🇷", callback_data=f"qstats_panel_marzban_{uuid_id}")
        btn_back = types.InlineKeyboardButton(f"{EMOJIS['back']} بازگشت", callback_data=f"acc_{uuid_id}")
        markup.add(btn_hiddify, btn_marzban, btn_back)
        return markup

    def server_selection_menu(self, uuid_id: int) -> types.InlineKeyboardMarkup:
        """منوی انتخاب سرور (آلمان/فرانسه) برای نمایش مصرف بازه‌ای."""
        kb = types.InlineKeyboardMarkup(row_width=2)
        btn_h = types.InlineKeyboardButton("آلمان 🇩🇪", callback_data=f"win_hiddify_{uuid_id}")
        btn_m = types.InlineKeyboardButton("فرانسه 🇫🇷", callback_data=f"win_marzban_{uuid_id}")
        btn_back = types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"acc_{uuid_id}")
        kb.add(btn_h, btn_m)
        kb.add(btn_back)
        return kb

    def account_menu(self, uuid_id: int) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("⏱ مصرف بازه‌ای", callback_data=f"win_select_{uuid_id}"),
            types.InlineKeyboardButton(f"{EMOJIS['globe']} دریافت لینک‌ها", callback_data=f"getlinks_{uuid_id}")
        )
        kb.add(
            types.InlineKeyboardButton("🗑 حذف", callback_data=f"del_{uuid_id}"),
            types.InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="manage")
        )
        return kb

    def settings(self, settings_dict: dict) -> types.InlineKeyboardMarkup:
        """منوی تنظیمات اعلان‌ها برای کاربر."""
        kb = types.InlineKeyboardMarkup(row_width=2)
        daily_text = f"📊 گزارش روزانه: {'✅' if settings_dict.get('daily_reports', True) else '❌'}"
        expiry_text = f"⏰ هشدار انقضا: {'✅' if settings_dict.get('expiry_warnings', True) else '❌'}"
        kb.add(
            types.InlineKeyboardButton(daily_text, callback_data="toggle_daily_reports"),
            types.InlineKeyboardButton(expiry_text, callback_data="toggle_expiry_warnings")
        )
        hiddify_text = f"🇩🇪 هشدار حجم آلمان: {'✅' if settings_dict.get('data_warning_hiddify', True) else '❌'}"
        marzban_text = f"🇫🇷 هشدار حجم فرانسه: {'✅' if settings_dict.get('data_warning_marzban', True) else '❌'}"
        kb.add(
            types.InlineKeyboardButton(hiddify_text, callback_data="toggle_data_warning_hiddify"),
            types.InlineKeyboardButton(marzban_text, callback_data="toggle_data_warning_marzban")
        )
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
        return kb

    # ===============================================
    # متدهای ادمین با فرمت callback جدید
    # ===============================================

    def admin_panel(self) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("📜 گزارش گیری", callback_data="admin:select_server:reports_menu"),
            types.InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin:management_menu")
        )
        kb.add(
            types.InlineKeyboardButton("📊 تحلیل و آمار", callback_data="admin:select_server:analytics_menu"),
            types.InlineKeyboardButton("📤 پیام همگانی", callback_data="admin:broadcast")
        )
        kb.add(
            types.InlineKeyboardButton("🎂 تولد کاربران", callback_data="admin:list:birthdays:0"),
            types.InlineKeyboardButton("🗄️ پشتیبان‌گیری", callback_data="admin:backup_menu")
        )
        # دکمه جدید در این ردیف اضافه می‌شود
        kb.add(types.InlineKeyboardButton("🔄 رفرش مپینگ مرزبان", callback_data="admin:reload_maps"))
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back"))
        return kb

    # در فایل menu.py
    def admin_management_menu(self) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("آلمان 🇩🇪", callback_data="admin:manage_panel:hiddify"),
            types.InlineKeyboardButton("فرانسه 🇫🇷", callback_data="admin:manage_panel:marzban")
        )
        kb.add(types.InlineKeyboardButton("🔎 جستجوی جامع کاربر", callback_data="admin:search_user_global"))

        kb.add(types.InlineKeyboardButton("🤖 لیست کاربران ربات", callback_data="admin:list:bot_users:0"))
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin:panel"))
        return kb

    def admin_reports_menu(self, panel: str) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ فعال (۲۴ ساعت اخیر)", callback_data=f"admin:list:active_users:{panel}:0"),
            types.InlineKeyboardButton("📡 کاربران آنلاین", callback_data=f"admin:list:online_users:{panel}:0")
        )
        kb.add(
            types.InlineKeyboardButton("🚫 هرگز متصل نشده", callback_data=f"admin:list:never_connected:{panel}:0"),
            types.InlineKeyboardButton("⏳ غیرفعال (۱ تا ۷ روز)", callback_data=f"admin:list:inactive_users:{panel}:0")
        )
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به انتخاب پنل", callback_data="admin:select_server:reports_menu"))
        kb.add(types.InlineKeyboardButton("↩️ بازگشت به پنل اصلی", callback_data="admin:panel"))
        return kb

    def create_pagination_menu(self, base_callback: str, current_page: int, total_items: int, back_callback: str) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        back_text = "🔙 بازگشت"

        if total_items <= PAGE_SIZE:
            kb.add(types.InlineKeyboardButton(back_text, callback_data=back_callback))
            return kb

        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(types.InlineKeyboardButton("⬅️ قبلی", callback_data=f"{base_callback}:{current_page - 1}"))
        if (current_page + 1) * PAGE_SIZE < total_items:
            nav_buttons.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=f"{base_callback}:{current_page + 1}"))

        if nav_buttons:
            kb.row(*nav_buttons)

        kb.add(types.InlineKeyboardButton(back_text, callback_data=back_callback))
        return kb


    def admin_user_interactive_management(self, identifier: str, is_active: bool, panel: str) -> types.InlineKeyboardMarkup:
            kb = types.InlineKeyboardMarkup(row_width=2)
            
            status_text = "🔴 غیرفعال کردن" if is_active else "🟢 فعال کردن"
            # FIX: Sending parameters directly, not as a combined string
            kb.add(types.InlineKeyboardButton(status_text, callback_data=f"admin:tgl:{panel}:{identifier}"))
            
            kb.add(types.InlineKeyboardButton("🔄 ریست تاریخ تولد", callback_data=f"admin:rbd:{panel}:{identifier}"))
            
            kb.add(
                types.InlineKeyboardButton("🔄 ریست مصرف", callback_data=f"admin:rusg_m:{panel}:{identifier}"),
                types.InlineKeyboardButton("🗑 حذف کامل", callback_data=f"admin:del_cfm:{panel}:{identifier}")
            )
            
            kb.add(types.InlineKeyboardButton("🔧 ویرایش کاربر", callback_data=f"admin:edt:{panel}:{identifier}"))
            
            kb.add(types.InlineKeyboardButton("🔙 بازگشت به مدیریت پنل", callback_data=f"admin:manage_panel:{panel}"))
            
            return kb

    def admin_analytics_menu(self, panel: str) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("🏆 پرمصرف‌ترین کاربران", callback_data=f"admin:list:top_consumers:{panel}:0"))
        if panel == 'hiddify':
            kb.add(types.InlineKeyboardButton("🌡️ وضعیت سلامت پنل", callback_data="admin:health_check"))
        elif panel == 'marzban':
            kb.add(types.InlineKeyboardButton("🖥️ وضعیت سیستم", callback_data="admin:marzban_stats"))

        kb.add(types.InlineKeyboardButton("🔙 بازگشت به انتخاب پنل", callback_data="admin:select_server:analytics_menu"))
        kb.add(types.InlineKeyboardButton("↩️ بازگشت به پنل اصلی", callback_data="admin:panel"))
        return kb

    def broadcast_target_menu(self) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("📡 آنلاین", callback_data="admin:broadcast_target:online"),
            types.InlineKeyboardButton("✅ فعال اخیر", callback_data="admin:broadcast_target:active_1")
        )
        kb.add(
            types.InlineKeyboardButton("⏳ غیرفعال اخیر", callback_data="admin:broadcast_target:inactive_7"),
            types.InlineKeyboardButton("🚫 هرگز متصل نشده", callback_data="admin:broadcast_target:inactive_0")
        )
        kb.add(types.InlineKeyboardButton("👥 همه کاربران ربات", callback_data="admin:broadcast_target:all"))
        kb.add(types.InlineKeyboardButton("🔙 لغو و بازگشت", callback_data="admin:panel"))
        return kb

    def cancel_action(self, back_callback="back") -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 لغو عملیات", callback_data=back_callback))
        return kb

    def admin_edit_user_menu(self, identifier: str, panel: str) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("➕ افزودن حجم", callback_data=f"admin:ask_edt:add_gb:{panel}:{identifier}"),
            types.InlineKeyboardButton("➕ افزودن روز", callback_data=f"admin:ask_edt:add_days:{panel}:{identifier}")
        )
        # FIX: Corrected "adm:" to "admin:"
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{panel}:{identifier}"))

        return kb

    def quick_stats_menu(self, num_accounts: int, current_page: int) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        nav_buttons = []
        if num_accounts > 1:
            if current_page > 0:
                nav_buttons.append(types.InlineKeyboardButton("⬅️ اکانت قبلی", callback_data=f"qstats_acc_page_{current_page - 1}"))
            if current_page < num_accounts - 1:
                nav_buttons.append(types.InlineKeyboardButton("اکانت بعدی ➡️", callback_data=f"qstats_acc_page_{current_page + 1}"))

        if nav_buttons:
            kb.row(*nav_buttons)

        kb.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back"))
        return kb

    def admin_server_selection_menu(self, base_callback: str) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("آلمان 🇩🇪", callback_data=f"{base_callback}:hiddify"),
            types.InlineKeyboardButton("فرانسه 🇫🇷", callback_data=f"{base_callback}:marzban")
        )
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin:panel"))
        return kb

    def admin_backup_selection_menu(self) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton("🗂 دیتابیس ربات (آلمان)", callback_data="admin:backup:bot_db"),
            types.InlineKeyboardButton("📄 کاربران فرانسه (JSON)", callback_data="admin:backup:marzban")
        )
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin:panel"))
        return kb

    def admin_panel_management_menu(self, panel: str) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton("➕ افزودن کاربر جدید", callback_data=f"admin:add_user:{panel}"),
            types.InlineKeyboardButton("📋 لیست کاربران پنل", callback_data=f"admin:list:panel_users:{panel}:0")
        )
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به انتخاب پنل", callback_data="admin:management_menu"))
        return kb

    def admin_reset_usage_selection_menu(self, identifier: str, panel: str) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        btn_h = types.InlineKeyboardButton("آلمان 🇩🇪", callback_data=f"admin:reset_usage_action:hiddify:{identifier}")
        btn_m = types.InlineKeyboardButton("فرانسه 🇫🇷", callback_data=f"admin:reset_usage_action:marzban:{identifier}")
        btn_both = types.InlineKeyboardButton("هر دو پنل", callback_data=f"admin:reset_usage_action:both:{identifier}")
        btn_back = types.InlineKeyboardButton("🔙 لغو و بازگشت", callback_data=f"admin:user_summary:{panel}:{identifier}")
        kb.add(btn_h, btn_m)
        kb.add(btn_both)
        kb.add(btn_back)
        return kb

# ساخت یک نمونه از کلاس برای استفاده در کل پروژه
menu = Menu()
