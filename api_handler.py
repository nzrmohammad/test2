import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import pytz
import requests
from requests.adapters import HTTPAdapter, Retry
from cachetools import cached

from config import HIDDIFY_DOMAIN, ADMIN_PROXY_PATH, ADMIN_UUID, API_TIMEOUT, api_cache
from utils import safe_float
from marzban_api_handler import marzban_handler

logger = logging.getLogger(__name__)

class HiddifyAPIHandler:
    def __init__(self):
        self.base_url = f"{HIDDIFY_DOMAIN.rstrip('/')}/{ADMIN_PROXY_PATH.strip('/')}/api/v2/admin"
        self.api_key = ADMIN_UUID
        self.tehran_tz = pytz.timezone("Asia/Tehran")
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "Hiddify-API-Key": self.api_key,
            "Accept": "application/json"
        })
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def _parse_api_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str or date_str.startswith('0001-01-01'):
            return None
        try:
            clean_str = date_str.split('.')[0].replace('T', ' ')
            naive_dt = datetime.strptime(clean_str, "%Y-%m-%d %H:%M:%S")
            return pytz.utc.localize(naive_dt)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse datetime string '{date_str}'")
            return None

    def _calculate_remaining_days(self, start_date_str: Optional[str], package_days: Optional[int]) -> Optional[int]:
        if package_days in [None, 0]:
            return None
        if not start_date_str:
            start_date = datetime.now(self.tehran_tz).date()
        else:
            try:
                start_date = datetime.strptime(start_date_str.split('T')[0], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                 logger.warning(f"Could not parse start_date string '{start_date_str}', using today's date.")
                 start_date = datetime.now(self.tehran_tz).date()
        expiration_date = start_date + timedelta(days=package_days)
        return (expiration_date - datetime.now(self.tehran_tz).date()).days

    def _norm(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict): return None
        try:
            usage_limit = safe_float(raw.get("usage_limit_GB", 0))
            current_usage = safe_float(raw.get("current_usage_GB", 0))
            return {
                "name": raw.get("name") or "کاربر ناشناس",
                "uuid": raw.get("uuid", "").lower(),
                "is_active": bool(raw.get("is_active", raw.get("enable", False))),
                "last_online": self._parse_api_datetime(raw.get("last_online")),
                "usage_limit_GB": usage_limit,
                "current_usage_GB": current_usage,
                "remaining_GB": max(0, usage_limit - current_usage),
                "usage_percentage": (current_usage / usage_limit * 100) if usage_limit > 0 else 0,
                "expire": self._calculate_remaining_days(raw.get("start_date"), raw.get("package_days")),
                "mode": raw.get("mode", "no_reset")
            }
        except Exception as e:
            logger.error(f"Data normalization failed: {e}, raw data: {raw}")
            return None

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Any]:
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.request(method, url, timeout=API_TIMEOUT, **kwargs)
            response.raise_for_status()
            return response.json() if response.status_code != 204 else True
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {method} {url} - {e}")
            return None

    def test_connection(self) -> bool:
        return self._request("GET", "/user/") is not None

    @cached(api_cache)
    def get_all_users(self, panel: str | None = None) -> List[Dict[str, Any]]:
        if panel == 'hiddify':
            data = self._request("GET", "/user/")
            if not data: return []
            raw_users = data if isinstance(data, list) else data.get("results", []) or data.get("users", [])
            return [norm_user for u in raw_users if (norm_user := self._norm(u))]
        
        if panel == 'marzban':
            return marzban_handler.get_all_users()
            
        # Default behavior: combine data
        hiddify_users = self.get_all_users(panel='hiddify')
        all_users = []
        for user_info in hiddify_users:
            combined_info = self.user_info(user_info['uuid'])
            if combined_info:
                all_users.append(combined_info)
        return all_users

    def user_info(self, uuid: str) -> Optional[Dict[str, Any]]:
        hiddify_raw_data = self._request("GET", f"/user/{uuid}/")
        if not hiddify_raw_data:
            return None
        
        hiddify_info = self._norm(hiddify_raw_data)
        if not hiddify_info:
            return None

        hiddify_info['breakdown'] = {
            'hiddify': {
                'usage': hiddify_info['current_usage_GB'],
                'limit': hiddify_info['usage_limit_GB'],
                'last_online': hiddify_info.get('last_online')
            }
        }

        marzban_info = marzban_handler.get_user_info(uuid)
        if marzban_info:
            hiddify_info['breakdown']['marzban'] = {
                'usage': marzban_info['current_usage_GB'],
                'limit': marzban_info['usage_limit_GB'],
                'last_online': marzban_info.get('last_online')
            }
            
            total_limit = hiddify_info['usage_limit_GB'] + marzban_info['usage_limit_GB']
            total_usage = hiddify_info['current_usage_GB'] + marzban_info['current_usage_GB']
            
            hiddify_info['usage_limit_GB'] = total_limit
            hiddify_info['current_usage_GB'] = total_usage
            hiddify_info['remaining_GB'] = max(0, total_limit - total_usage)
            hiddify_info['usage_percentage'] = (total_usage / total_limit * 100) if total_limit > 0 else 0
            
            h_online = hiddify_info.get('last_online')
            m_online = marzban_info.get('last_online')
            if m_online and (not h_online or m_online > h_online):
                hiddify_info['last_online'] = m_online

        return hiddify_info
        
    def get_panel_info(self) -> Optional[Dict[str, Any]]:
        panel_info_url = f"{HIDDIFY_DOMAIN.rstrip('/')}/{ADMIN_PROXY_PATH.strip('/')}/api/v2/panel/info/"
        try:
            response = self.session.get(panel_info_url, timeout=API_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request for panel info failed: {e}")
            return None
        
    def get_top_consumers(self, panel: str | None = None) -> List[Dict[str, Any]]:
        all_users = self.get_all_users(panel=panel)
        if not all_users: return []
        return sorted(all_users, key=lambda u: u.get('current_usage_GB', 0), reverse=True)

    def online_users(self, panel: str | None = None) -> List[Dict[str, Any]]:
        all_users = self.get_all_users(panel=panel)
        online = []
        three_minutes_ago = datetime.now(pytz.utc) - timedelta(minutes=3)
        for user in all_users:
            if user.get('is_active') and user.get('last_online') and user['last_online'].astimezone(pytz.utc) >= three_minutes_ago:
                online.append(user)
        return online

    def get_active_users(self, days: int, panel: str | None = None) -> List[Dict[str, Any]]:
        all_users = self.get_all_users(panel=panel)
        active = []
        deadline = datetime.now(pytz.utc) - timedelta(days=days)
        for user in all_users:
            if user.get('last_online') and user['last_online'].astimezone(pytz.utc) >= deadline:
                active.append(user)
        return active

    def get_inactive_users(self, min_days: int, max_days: int, panel: str | None = None) -> List[Dict[str, Any]]:
        all_users = self.get_all_users(panel=panel)
        inactive = []
        now_utc = datetime.now(pytz.utc)
        for user in all_users:
            last_online = user.get('last_online')
            if min_days == -1 and last_online is None:
                inactive.append(user)
                continue
            if last_online:
                days_since_online = (now_utc - last_online.astimezone(pytz.utc)).days
                if min_days <= days_since_online < max_days:
                    inactive.append(user)
        return inactive

    def add_user(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        new_user_raw = self._request("POST", "/user/", json=data)
        if new_user_raw and new_user_raw.get('uuid'):
            return self.user_info(new_user_raw['uuid'])
        logger.error(f"Failed to add user. Data: {data}, Response: {new_user_raw}")
        return None

    def modify_user(self, uuid: str, data: dict = None, add_usage_gb: float = 0, add_days: int = 0) -> bool:
        if data:
            return self._request("PATCH", f"/user/{uuid}/", json=data) is not None

        payload = {}
        if add_usage_gb or add_days:
            current_info = self.user_info(uuid)
            if not current_info:
                logger.error(f"Cannot modify user {uuid}: Could not fetch current info.")
                return False

            if add_usage_gb:
                current_limit_gb = current_info.get("usage_limit_GB", 0)
                payload["usage_limit_GB"] = current_limit_gb + add_usage_gb

            if add_days:
                current_expire_days = current_info.get("expire", 0)
                if current_expire_days < 0:
                    current_expire_days = 0
                payload["package_days"] = current_expire_days + add_days
        
        if not payload:
            return True
        
        return self._request("PATCH", f"/user/{uuid}/", json=payload) is not None

    def delete_user(self, uuid: str) -> bool:
        return self._request("DELETE", f"/user/{uuid}/") is True

    def reset_user_usage(self, uuid: str) -> bool:
        return self.modify_user(uuid, {"current_usage_GB": 0})

api_handler = HiddifyAPIHandler()