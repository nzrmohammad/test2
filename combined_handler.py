from typing import Optional, Dict, Any, List
from hiddify_api_handler import hiddify_handler
from marzban_api_handler import marzban_handler
from database import db
from utils import validate_uuid

def get_combined_user_info(identifier: str) -> Optional[Dict[str, Any]]:
    is_uuid = validate_uuid(identifier)
    
    h_info_raw = hiddify_handler.user_info(identifier) if is_uuid else None
    m_info = marzban_handler.get_user_info(identifier)
    
    if not h_info_raw and not m_info:
        return None

    if h_info_raw and not m_info:
        h_info_raw['breakdown'] = {'hiddify': h_info_raw}
        return h_info_raw
    if not h_info_raw and m_info:
        m_info['breakdown'] = {'marzban': m_info}
        return m_info

    if h_info_raw and m_info:
        h_info_raw['breakdown'] = {'hiddify': h_info_raw, 'marzban': m_info}
        
        total_limit = h_info_raw.get('usage_limit_GB', 0) + m_info.get('usage_limit_GB', 0)
        total_usage = h_info_raw.get('current_usage_GB', 0) + m_info.get('current_usage_GB', 0)
        
        h_info_raw['usage_limit_GB'] = total_limit
        h_info_raw['current_usage_GB'] = total_usage
        h_info_raw['remaining_GB'] = max(0, total_limit - total_usage)
        h_info_raw['usage_percentage'] = (total_usage / total_limit * 100) if total_limit > 0 else 0
        
        h_online = h_info_raw.get('last_online')
        m_online = m_info.get('last_online')
        if m_online and (not h_online or m_online > h_online):
            h_info_raw['last_online'] = m_online

        return h_info_raw
    return None

def search_user(query: str) -> List[Dict[str, Any]]:
    query_lower = query.lower()
    results = []
    found_usernames = set()

    h_users = hiddify_handler.get_all_users()
    for user in h_users:
        if query_lower in user.get('name', '').lower():
            results.append({**user, 'panel': 'hiddify'})
            found_usernames.add(user.get('name'))

    m_users = marzban_handler.get_all_users()
    for user in m_users:
        if user.get('name') in found_usernames: continue
        if query_lower in user.get('name', '').lower():
            results.append({**user, 'panel': 'marzban'})

    return results

def delete_user_from_all_panels(identifier: str) -> bool:
    info = get_combined_user_info(identifier)
    if not info:
        return False

    h_success, m_success = True, True

    if 'hiddify' in info.get('breakdown', {}):
        h_success = hiddify_handler.delete_user(info['uuid'])

    if 'marzban' in info.get('breakdown', {}):
        m_success = marzban_handler.delete_user(info['name'])

    if h_success and m_success:
        db_id = db.get_uuid_id_by_uuid(info.get('uuid'))
        if db_id:
            db.deactivate_uuid(db_id)
            db.delete_user_snapshots(db_id)
    
    return h_success and m_success

def get_all_users_combined() -> List[Dict[str, Any]]:
    all_users_map = {}
    h_users = hiddify_handler.get_all_users()
    for user in h_users:
        all_users_map[user['uuid']] = user

    m_users = marzban_handler.get_all_users()
    for user in m_users:
        if user.get('uuid') in all_users_map:
            pass
        else:
            all_users_map[user['uuid']] = user
            
    return list(all_users_map.values())

def search_user(query: str) -> List[Dict[str, Any]]:
    query_lower = query.lower()
    results = []
    found_uuids = set()

    hiddify_users = hiddify_handler.get_all_users()
    for user in hiddify_users:
        if query_lower in user.get('name', '').lower() or query_lower in user.get('uuid', ''):
            results.append({**user, 'panel': 'hiddify'}) # اضافه کردن پنل مبدا
            found_uuids.add(user.get('uuid'))

    marzban_users = marzban_handler.get_all_users()
    for user in marzban_users:
        if user.get('uuid') in found_uuids:
            continue
        if query_lower in user.get('name', '').lower():
            results.append({**user, 'panel': 'marzban'}) # اضافه کردن پنل مبدا

    return results