from telebot import types
from config import EMOJIS, PAGE_SIZE

class Menu:
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
            kb.add(types.InlineKeyboardButton(f"{EMOJIS['crown']} پنل مدیریت", callback_data="admin_panel"))
        return kb

    def accounts(self, rows) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=1)
        for r in rows:
            name = r.get('name', 'کاربر ناشناس')
            kb.add(types.InlineKeyboardButton(f"📊 {name}", callback_data=f"acc_{r['id']}"))
        kb.add(types.InlineKeyboardButton("➕ افزودن اکانت جدید", callback_data="add"))
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
        return kb
    
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
            # تغییر اصلی اینجاست: callback به win_select اشاره می‌کند
            types.InlineKeyboardButton("⏱ مصرف بازه‌ای", callback_data=f"win_select_{uuid_id}"),
            types.InlineKeyboardButton(f"{EMOJIS['globe']} دریافت لینک‌ها", callback_data=f"getlinks_{uuid_id}")
        )
        kb.add(
            types.InlineKeyboardButton("🗑 حذف", callback_data=f"del_{uuid_id}"),
            types.InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="manage")
        )
        return kb

    def settings(self, settings_dict: dict) -> types.InlineKeyboardMarkup:
        """This is the new, correct settings menu."""
        kb = types.InlineKeyboardMarkup(row_width=2)
        
        # General Warnings
        daily_text = f"📊 گزارش روزانه: {'✅' if settings_dict.get('daily_reports', True) else '❌'}"
        expiry_text = f"⏰ هشدار انقضا: {'✅' if settings_dict.get('expiry_warnings', True) else '❌'}"
        kb.add(
            types.InlineKeyboardButton(daily_text, callback_data="toggle_daily_reports"),
            types.InlineKeyboardButton(expiry_text, callback_data="toggle_expiry_warnings")
        )
        
        # Server-Specific Data Warnings
        hiddify_text = f"🇩🇪 هشدار حجم آلمان: {'✅' if settings_dict.get('data_warning_hiddify', True) else '❌'}"
        marzban_text = f"🇫🇷 هشدار حجم فرانسه: {'✅' if settings_dict.get('data_warning_marzban', True) else '❌'}"
        kb.add(
            types.InlineKeyboardButton(hiddify_text, callback_data="toggle_data_warning_hiddify"),
            types.InlineKeyboardButton(marzban_text, callback_data="toggle_data_warning_marzban")
        )
        
        # Back Button
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
        return kb

    def admin_panel(self) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        btn_reports = types.InlineKeyboardButton("📜 گزارش گیری", callback_data="admin_select_server_for_reports")
        btn_manage = types.InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_management_menu")
        btn_analytics = types.InlineKeyboardButton("📊 تحلیل و آمار", callback_data="admin_select_server_for_analytics")
        btn_broadcast = types.InlineKeyboardButton("📤 پیام همگانی", callback_data="admin_broadcast")
        btn_birthdays = types.InlineKeyboardButton("🎂 تولد کاربران", callback_data="admin_birthdays_0")
        btn_backup = types.InlineKeyboardButton("🗄️ پشتیبان‌گیری", callback_data="admin_select_backup")
        btn_back = types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back")
        kb.add(btn_reports, btn_manage)
        kb.add(btn_analytics, btn_broadcast)
        kb.add(btn_birthdays, btn_backup)
        kb.add(btn_back)
        return kb

    def admin_management_menu(self) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
        types.InlineKeyboardButton("آلمان 🇩🇪", callback_data="admin_manage_panel_hiddify"),
        types.InlineKeyboardButton("فرانسه 🇫🇷", callback_data="admin_manage_panel_marzban")
    )
        kb.add(types.InlineKeyboardButton("🤖 لیست کاربران ربات", callback_data="admin_list_bot_users_0"))
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin_panel"))
        return kb

    def admin_reports_menu(self, panel: str) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        btn_online = types.InlineKeyboardButton("📡 کاربران آنلاین", callback_data=f"admin_online_{panel}_0")
        btn_active = types.InlineKeyboardButton("✅ فعال (۲۴ ساعت اخیر)", callback_data=f"admin_active_1_{panel}_0")
        btn_inactive = types.InlineKeyboardButton("⏳ غیرفعال (۱ تا ۷ روز)", callback_data=f"admin_inactive_7_{panel}_0")
        btn_never = types.InlineKeyboardButton("🚫 هرگز متصل نشده", callback_data=f"admin_inactive_0_{panel}_0")
        btn_back_to_select = types.InlineKeyboardButton("🔙 بازگشت به انتخاب پنل", callback_data="admin_select_server_for_reports")
        btn_back = types.InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin_panel")
        kb.add(btn_active, btn_online)
        kb.add(btn_never, btn_inactive)
        kb.add(btn_back_to_select)
        kb.add(btn_back)
        return kb

    def create_pagination_menu(self, base_callback: str, current_page: int, total_items: int, back_callback: str) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        
        # Determine the text for the back button
        if "reports" in back_callback:
             back_text = "🔙 بازگشت به گزارشات"
        else:
             back_text = "🔙 بازگشت"

        if total_items <= PAGE_SIZE:
            # Pass the full callback data (e.g., "admin_reports_menu_hiddify")
            kb.add(types.InlineKeyboardButton(back_text, callback_data=back_callback))
            return kb

        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(types.InlineKeyboardButton("⬅️ قبلی", callback_data=f"{base_callback}_{current_page - 1}"))
        
        if (current_page + 1) * PAGE_SIZE < total_items:
            nav_buttons.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=f"{base_callback}_{current_page + 1}"))
        
        if nav_buttons:
            kb.row(*nav_buttons)
        
        kb.add(types.InlineKeyboardButton(back_text, callback_data=back_callback))
        return kb

    def admin_user_interactive_management(self, identifier: str, is_active: bool, panel: str) -> types.InlineKeyboardMarkup:
        """Shows the main management menu for a user, using a string identifier."""
        kb = types.InlineKeyboardMarkup(row_width=2)
        status_text = "🔴 غیرفعال کردن" if is_active else "🟢 فعال کردن"
        
        # Callbacks now use the string identifier (UUID/username)
        kb.add(types.InlineKeyboardButton(status_text, callback_data=f"ad_tgl_{panel}_{identifier}"))
        kb.add(types.InlineKeyboardButton("🔄 ریست تاریخ تولد", callback_data=f"ad_bday_{panel}_{identifier}"))
        kb.add(
            types.InlineKeyboardButton("🔄 ریست مصرف", callback_data=f"ad_rst_{panel}_{identifier}"),
            types.InlineKeyboardButton("🗑 حذف کامل", callback_data=f"ad_del_{panel}_{identifier}")
        )
        kb.add(types.InlineKeyboardButton("🔧 ویرایش کاربر", callback_data=f"ad_edt_{panel}_{identifier}"))
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به مدیریت پنل", callback_data=f"admin_manage_panel_{panel}"))
        return kb

    def confirm_delete(self, identifier: str) -> types.InlineKeyboardMarkup:
        """Confirmation menu for deletion, using a string identifier."""
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"ad_cdel_{identifier}"),
            types.InlineKeyboardButton("❌ خیر، لغو", callback_data=f"ad_nodel_{identifier}")
        )
        return kb

    def admin_analytics_menu(self, panel: str) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton("🏆 پرمصرف‌ترین کاربران", callback_data=f"admin_top_consumers_{panel}_0")
        )
        
        # بر اساس پنل، دکمه مناسب نمایش داده می‌شود
        if panel == 'hiddify':
            kb.add(types.InlineKeyboardButton("🌡️ وضعیت سلامت پنل", callback_data="admin_health_check"))
        elif panel == 'marzban':
            kb.add(types.InlineKeyboardButton("🖥️ وضعیت سیستم", callback_data="admin_marzban_system_stats"))
        
        # بازگشت به منوی انتخاب سرور برای بخش تحلیل
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به انتخاب پنل", callback_data="admin_select_server_for_analytics"))
        return kb
    
    def broadcast_target_menu(self) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("📡 آنلاین", callback_data="broadcast_target_online"),
            types.InlineKeyboardButton("✅ فعال اخیر", callback_data="broadcast_target_active_1")
        )
        kb.add(
            types.InlineKeyboardButton("⏳ غیرفعال اخیر", callback_data="broadcast_target_inactive_7"),
            types.InlineKeyboardButton("🚫 هرگز متصل نشده", callback_data="broadcast_target_inactive_0")
        )
        kb.add(types.InlineKeyboardButton("👥 همه کاربران ربات", callback_data="broadcast_target_all"))
        kb.add(types.InlineKeyboardButton("🔙 لغو و بازگشت", callback_data="admin_panel"))
        return kb
    
    def cancel_action(self, back_callback="back") -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 لغو عملیات", callback_data=back_callback))
        return kb

    def admin_edit_user_menu(self, identifier: str, panel: str) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("➕ افزودن حجم", callback_data=f"ad_act_addgb_{panel}_{identifier}"),
            types.InlineKeyboardButton("➕ افزودن روز", callback_data=f"ad_act_adddays_{panel}_{identifier}")
        )
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"ad_sr_{panel}_{identifier}"))
        return kb
    
    def quick_stats_menu(self, num_accounts: int, current_page: int) -> types.InlineKeyboardMarkup:
        """منوی صفحه‌بندی برای بخش آمار فوری بر اساس اکانت."""
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
        btn_h = types.InlineKeyboardButton("آلمان 🇩🇪", callback_data=f"{base_callback}_hiddify")
        btn_m = types.InlineKeyboardButton("فرانسه 🇫🇷", callback_data=f"{base_callback}_marzban")
        btn_back = types.InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin_panel")
        kb.add(btn_h, btn_m)
        kb.add(btn_back)

        return kb


    def admin_backup_selection_menu(self) -> types.InlineKeyboardMarkup:
        """منوی انتخاب نوع پشتیبان‌گیری را نمایش می‌دهد."""
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton("🗂 دیتابیس ربات (آلمان)", callback_data="admin_backup_bot_db"),
            types.InlineKeyboardButton("📄 کاربران فرانسه (JSON)", callback_data="admin_backup_marzban")
        )
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin_panel"))
        return kb

    def admin_panel_management_menu(self, panel: str) -> types.InlineKeyboardMarkup:
        """Displays management options for a specific panel."""
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton("➕ افزودن کاربر جدید", callback_data=f"admin_add_user_{panel}"),
            types.InlineKeyboardButton("🔍 جستجوی کاربر", callback_data=f"admin_search_user_{panel}"),
            types.InlineKeyboardButton("📋 لیست کاربران پنل", callback_data=f"admin_list_panel_users_{panel}_0")
        )
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به انتخاب پنل", callback_data="admin_management_menu"))
        return kb

    def admin_reset_usage_selection_menu(self, identifier: str, panel: str) -> types.InlineKeyboardMarkup:
        """Displays a menu to select which panel's usage to reset."""
        kb = types.InlineKeyboardMarkup(row_width=2)
        # Callback format: ad_crst_{panel_to_reset}_{identifier}
        btn_h = types.InlineKeyboardButton("آلمان 🇩🇪", callback_data=f"ad_crst_hiddify_{identifier}")
        btn_m = types.InlineKeyboardButton("فرانسه 🇫🇷", callback_data=f"ad_crst_marzban_{identifier}")
        btn_both = types.InlineKeyboardButton("هر دو پنل", callback_data=f"ad_crst_both_{identifier}")
        # The back button should return to the user management menu
        btn_back = types.InlineKeyboardButton("🔙 لغو و بازگشت", callback_data=f"ad_sr_{panel}_{identifier}")
        kb.add(btn_h, btn_m)
        kb.add(btn_both)
        kb.add(btn_back)
        return kb

menu = Menu()