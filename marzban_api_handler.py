import requests
import logging
import json
from datetime import datetime
import pytz
from config import MARZBAN_API_BASE_URL, MARZBAN_API_USERNAME, MARZBAN_API_PASSWORD, API_TIMEOUT

logger = logging.getLogger(__name__)

class MarzbanAPIHandler:
    def __init__(self):
        self.base_url = MARZBAN_API_BASE_URL
        self.username = MARZBAN_API_USERNAME
        self.password = MARZBAN_API_PASSWORD
        self.access_token = self._get_access_token()
        self.uuid_map = self._load_uuid_map()
        self.utc_tz = pytz.utc

    def _load_uuid_map(self):
        """Loads the uuid_to_marzban_user.json file and creates both forward and reverse maps."""
        try:
            with open('uuid_to_marzban_user.json', 'r', encoding='utf-8') as f:
                # --- START OF FIX ---
                # Load the data from the file ONCE into a variable
                data = json.load(f)
                # Create the reverse map from the loaded data
                self.username_to_uuid_map = {v: k for k, v in data.items()}
                # Return the forward map
                return data
                # --- END OF FIX ---
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning("uuid_to_marzban_user.json not found or invalid. Marzban mapping will be disabled.")
            self.username_to_uuid_map = {}
            return {}

    def _get_access_token(self):
        """Fetches the access token from Marzban panel."""
        try:
            url = f"{self.base_url}/api/admin/token"
            data = {"username": self.username, "password": self.password}
            response = requests.post(url, data=data, timeout=API_TIMEOUT)
            response.raise_for_status()
            return response.json().get("access_token")
        except requests.exceptions.RequestException as e:
            logger.error(f"Marzban: Failed to get access token: {e}")
            return None

    def _parse_marzban_datetime(self, date_str: str | None) -> datetime | None:
        """
        رشته تاریخ API مرزبان را به شیء datetime استاندارد تبدیل می‌کند.
        این نسخه برای کار با فرمت شامل میلی‌ثانیه اصلاح شده است.
        """
        if not date_str:
            return None
        try:
            # بخش میلی‌ثانیه را جدا می‌کنیم تا سازگاری کامل شود
            clean_str = date_str.split('.')[0].replace('T', ' ')
            # فرمت تاریخ را به شکل YYYY-MM-DD HH:MM:SS در می‌آوریم
            naive_dt = datetime.strptime(clean_str, "%Y-%m-%d %H:%M:%S")
            # آن را به منطقه زمانی UTC تبدیل می‌کنیم
            return pytz.utc.localize(naive_dt)
        except (ValueError, TypeError) as e:
            logger.warning(f"Marzban: Could not parse datetime string '{date_str}': {e}")
            return None

    def get_user_info(self, uuid: str) -> dict | None:
        if not self.access_token:
            return None
        marzban_username = self.uuid_map.get(uuid, uuid)
        try:
            url = f"{self.base_url}/api/user/{marzban_username}"
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(url, headers=headers, timeout=API_TIMEOUT)
            if response.status_code == 404:
                logger.warning(f"Marzban: User '{marzban_username}' (from UUID {uuid}) not found.")
                return None
            response.raise_for_status()
            data = response.json()
            
            usage_gb = data.get('used_traffic', 0) / (1024 ** 3)
            limit_gb = data.get('data_limit', 0) / (1024 ** 3)
            
            return {
                "current_usage_GB": usage_gb,
                "usage_limit_GB": limit_gb,
                "is_active": data.get('status') == 'active',
                # --- شروع تغییر ---
                "last_online": self._parse_marzban_datetime(data.get('online_at'))
                # --- پایان تغییر ---
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Marzban: Failed to get user info for {marzban_username}: {e}")
            if "Token has expired" in str(e):
                self.access_token = self._get_access_token()
                return self.get_user_info(uuid)
            return None

    def get_all_users(self) -> list[dict]:
        """Fetches a list of all users from the Marzban panel."""
        if not self.access_token:
            return []
        try:
            url = f"{self.base_url}/api/users"
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(url, headers=headers, timeout=API_TIMEOUT)
            response.raise_for_status()
            users_data = response.json().get("users", [])
            
            all_users = []
            for user in users_data:
                username = user.get("username")
                uuid = self.username_to_uuid_map.get(username, "") # Find UUID from username
                
                usage_gb = user.get('used_traffic', 0) / (1024 ** 3)
                limit_gb = user.get('data_limit', 0) / (1024 ** 3)
                
                expire_timestamp = user.get('expire')
                expire_days = None
                if expire_timestamp and expire_timestamp > 0:
                    try:
                        expire_datetime = datetime.fromtimestamp(expire_timestamp, tz=self.utc_tz)
                        expire_days = (expire_datetime - datetime.now(self.utc_tz)).days
                    except (ValueError, TypeError):
                        expire_days = None

                all_users.append({
                    "name": username,
                    "uuid": uuid,
                    "is_active": user.get('status') == 'active',
                    "last_online": self._parse_marzban_datetime(user.get('online_at')),
                    "usage_limit_GB": limit_gb,
                    "current_usage_GB": usage_gb,
                    "remaining_GB": max(0, limit_gb - usage_gb),
                    "usage_percentage": (usage_gb / limit_gb * 100) if limit_gb > 0 else 0,
                    "expire": expire_days,
                    "created_at": self._parse_marzban_datetime(user.get('created_at'))
                })
            return all_users
        except requests.exceptions.RequestException as e:
            logger.error(f"Marzban: Failed to get all users: {e}")
            return []

    def get_system_stats(self) -> dict | None:
            """اطلاعات و آمار کلی سیستم را از پنل مرزبان دریافت می‌کند."""
            if not self.access_token:
                return None
            try:
                url = f"{self.base_url}/api/system"
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(url, headers=headers, timeout=API_TIMEOUT)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"Marzban: Failed to get system stats: {e}")
                return None

marzban_handler = MarzbanAPIHandler()