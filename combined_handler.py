from typing import Optional, Dict, Any, List
from hiddify_api_handler import hiddify_handler
from marzban_api_handler import marzban_handler
from database import db
from utils import validate_uuid
import logging

logger = logging.getLogger(__name__)

def get_combined_user_info(identifier: str) -> Optional[Dict[str, Any]]:
    is_uuid = validate_uuid(identifier)
    h_info, m_info = None, None

    if is_uuid:
        h_info = hiddify_handler.user_info(identifier)
        m_info = marzban_handler.get_user_info(identifier)
    else:
        m_info = marzban_handler.get_user_by_username(identifier)
        if m_info and m_info.get('uuid'):
            h_info = hiddify_handler.user_info(m_info['uuid'])
            
    if not h_info and not m_info: return None

    # Use Hiddify as base if it exists, otherwise Marzban
    base_info = (h_info or m_info).copy()
    
    # Always create the breakdown structure for consistent formatting
    base_info['breakdown'] = {
        'hiddify': h_info if h_info else {},
        'marzban': m_info if m_info else {}
    }
    
    # Correctly recalculate totals
    h_limit = h_info.get('usage_limit_GB', 0) if h_info else 0
    m_limit = m_info.get('usage_limit_GB', 0) if m_info else 0
    total_limit = h_limit + m_limit
    
    h_usage = h_info.get('current_usage_GB', 0) if h_info else 0
    m_usage = m_info.get('current_usage_GB', 0) if m_info else 0
    total_usage = h_usage + m_usage
    
    base_info['usage_limit_GB'] = total_limit
    base_info['current_usage_GB'] = total_usage
    base_info['remaining_GB'] = max(0, total_limit - total_usage)
    base_info['usage_percentage'] = (total_usage / total_limit * 100) if total_limit > 0 else 0
    
    # Finalize name and choose the latest online time
    base_info['name'] = (h_info or m_info).get('name')
    h_online = h_info.get('last_online') if h_info else None
    m_online = m_info.get('last_online') if m_info else None
    
    if m_online and (not h_online or m_online > h_online):
        base_info['last_online'] = m_online
    else:
        base_info['last_online'] = h_online

    return base_info

# ... (The rest of the file can remain the same)
def delete_user_from_all_panels(identifier: str) -> bool:
    info = get_combined_user_info(identifier)
    if not info: return False
    h_success, m_success = True, True
    h_uuid = info.get('uuid')
    m_username = info.get('name') if 'marzban' in info.get('breakdown', {}) else None
    if h_uuid and 'hiddify' in info.get('breakdown', {}):
        h_success = hiddify_handler.delete_user(h_uuid)
    if m_username and 'marzban' in info.get('breakdown', {}):
        m_success = marzban_handler.delete_user(m_username)
    if h_success and m_success and h_uuid:
        db_id = db.get_uuid_id_by_uuid(h_uuid)
        if db_id:
            db.deactivate_uuid(db_id)
            db.delete_user_snapshots(db_id)
    return h_success and m_success

def get_all_users_combined() -> List[Dict[str, Any]]:
    all_users_map = {}
    h_users = hiddify_handler.get_all_users()
    for user in h_users:
        uuid = user['uuid']
        user['breakdown'] = {'hiddify': user}
        all_users_map[uuid] = user

    m_users = marzban_handler.get_all_users()
    for user in m_users:
        uuid = user.get('uuid')
        if uuid and uuid in all_users_map:
            all_users_map[uuid]['breakdown']['marzban'] = user
        else:
            key = uuid or user['name']
            user['breakdown'] = {'marzban': user}
            all_users_map[key] = user
            
    return list(all_users_map.values())

def search_user(query: str) -> List[Dict[str, Any]]:
    query_lower = query.lower()
    results, found_identifiers = [], set()

    all_users = get_all_users_combined()
    for user in all_users:
        identifier = user.get('uuid') or user.get('name')
        if identifier in found_identifiers: continue
        
        match = query_lower in user.get('name', '').lower() or \
                (user.get('uuid') and query_lower in user.get('uuid'))
        
        if match:
            panel = 'hiddify' if 'hiddify' in user.get('breakdown', {}) else 'marzban'
            results.append({**user, 'panel': panel})
            found_identifiers.add(identifier)
    return results