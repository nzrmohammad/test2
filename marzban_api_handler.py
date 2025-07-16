import requests
import logging
import json
from datetime import datetime, timedelta
import pytz
from config import MARZBAN_API_BASE_URL, MARZBAN_API_USERNAME, MARZBAN_API_PASSWORD, API_TIMEOUT
from database import db
from utils import validate_uuid

logger = logging.getLogger(__name__)

class MarzbanAPIHandler:
    def __init__(self):
        self.base_url = MARZBAN_API_BASE_URL
        self.username = MARZBAN_API_USERNAME
        self.password = MARZBAN_API_PASSWORD
        self.access_token = self._get_access_token()
        self.uuid_map = self._load_uuid_map()
        self.utc_tz = pytz.utc

# در فایل marzban_api_handler.py
def _load_uuid_map(self):
    """Loads the uuid_to_marzban_user.json file and creates both forward and reverse maps."""
    try:
        with open('uuid_to_marzban_user.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.username_to_uuid_map = {v: k for k, v in data.items()}
            return data
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

    def add_user(self, user_data: dict) -> dict | None:
        """Adds a new user to the Marzban panel."""
        if not self.access_token:
            return None
        
        try:
            url = f"{self.base_url}/api/user"
            headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
            
            # Prepare data for Marzban API
            expire_timestamp = 0
            if user_data.get('package_days', 0) > 0:
                expire_timestamp = int((datetime.now() + timedelta(days=user_data.get('package_days', 0))).timestamp())

            payload = {
                "username": user_data.get('username'),
                "proxies": {"vless": {}}, # Default proxy setting
                "data_limit": int(user_data.get('usage_limit_GB', 0) * (1024**3)),
                "expire": expire_timestamp,
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=API_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Marzban: Failed to add user '{user_data.get('username')}': {e}")
            return None

    def modify_user(self, username: str, data: dict = None, add_usage_gb: float = 0, add_days: int = 0) -> bool:
        """Modifies an existing Marzban user by username."""
        if not self.access_token:
            return False

        try:
            get_url = f"{self.base_url}/api/user/{username}"
            headers = {"Authorization": f"Bearer {self.access_token}"}
            current_response = requests.get(get_url, headers=headers, timeout=API_TIMEOUT)
            current_response.raise_for_status()
            current_data = current_response.json()

            # Initialize payload with data from the 'data' argument if it exists
            payload = data.copy() if data else {}

            if add_usage_gb != 0:
                current_limit = current_data.get('data_limit', 0)
                payload['data_limit'] = current_limit + int(add_usage_gb * (1024**3))

            if add_days != 0:
                current_expire_ts = current_data.get('expire', 0)
                base_time = datetime.fromtimestamp(current_expire_ts) if current_expire_ts > 0 else datetime.now()
                if base_time < datetime.now():
                    base_time = datetime.now()
                new_expire_dt = base_time + timedelta(days=add_days)
                payload['expire'] = int(new_expire_dt.timestamp())

            if not payload:
                # Nothing to change
                return True

            put_url = f"{self.base_url}/api/user/{username}"
            response = requests.put(put_url, headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}, json=payload, timeout=API_TIMEOUT)
            response.raise_for_status()
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Marzban: Failed to modify user '{username}': {e}")
            return False
    def _parse_marzban_datetime(self, date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            clean_str = date_str.split('.')[0].replace('T', ' ')
            naive_dt = datetime.strptime(clean_str, "%Y-%m-%d %H:%M:%S")
            return pytz.utc.localize(naive_dt)
        except (ValueError, TypeError) as e:
            logger.warning(f"Marzban: Could not parse datetime string '{date_str}': {e}")
            return None
        
    # --- THIS FUNCTION MUST EXIST ---
    def get_user_info(self, uuid: str) -> dict | None:
        """Gets a single user's details from Marzban by their Hiddify UUID."""
        if not self.access_token:
            return None
        
        # Find the Marzban username from the Hiddify UUID
        marzban_username = self.uuid_map.get(uuid)
        if not marzban_username:
            return None # If no mapping exists, the user is not in Marzban

        # Reuse the get_user_by_username logic
        return self.get_user_by_username(marzban_username)

    def get_all_users(self) -> list[dict]:
        """
        Fetches all users from the Marzban panel and returns their full,
        normalized data.
        """
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
                if username:
                    detailed_info = self.get_user_by_username(username)
                    if detailed_info:
                        all_users.append(detailed_info)
                        
            return all_users
        except requests.exceptions.RequestException as e:
            logger.error(f"Marzban: Failed to get all users: {e}")
            return []
        
    def get_user_by_username(self, username: str) -> dict | None:
        """Gets a single user's details from Marzban by their username."""
        if not self.access_token:
            return None
        try:
            url = f"{self.base_url}/api/user/{username}"
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(url, headers=headers, timeout=API_TIMEOUT)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            user = response.json()
            
            uuid = self.username_to_uuid_map.get(username, username)
            usage_gb = user.get('used_traffic', 0) / (1024 ** 3)
            limit_gb = user.get('data_limit', 0) / (1024 ** 3)
            expire_timestamp = user.get('expire')
            expire_days = None
            if expire_timestamp and expire_timestamp > 0:
                expire_datetime = datetime.fromtimestamp(expire_timestamp, tz=self.utc_tz)
                expire_days = (expire_datetime - datetime.now(self.utc_tz)).days

            return {
                "name": username,
                "uuid": uuid,
                "is_active": user.get('status') == 'active',
                "last_online": self._parse_marzban_datetime(user.get('online_at')),
                "usage_limit_GB": limit_gb,
                "current_usage_GB": usage_gb,
                "remaining_GB": max(0, limit_gb - usage_gb),
                "usage_percentage": (usage_gb / limit_gb * 100) if limit_gb > 0 else 0,
                "expire": expire_days,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Marzban: Failed to get user by username '{username}': {e}")
            return None

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

    def delete_user(self, username: str) -> bool:
        """Deletes a user from the Marzban panel by username."""
        if not self.access_token:
            return False
        try:
            url = f"{self.base_url}/api/user/{username}"
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.delete(url, headers=headers, timeout=API_TIMEOUT)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Marzban: Failed to delete user '{username}': {e}")
            return False

    def reset_user_usage(self, username: str) -> bool:
        """Resets a user's data usage in the Marzban panel."""
        if not self.access_token:
            return False
        try:
            url = f"{self.base_url}/api/user/{username}/reset"
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.post(url, headers=headers, timeout=API_TIMEOUT)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Marzban: Failed to reset usage for user '{username}': {e}")
            return False

marzban_handler = MarzbanAPIHandler()