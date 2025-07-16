from typing import Optional, Dict, Any, List
from hiddify_api_handler import hiddify_handler
from marzban_api_handler import marzban_handler
from database import db
from utils import validate_uuid

def get_combined_user_info(identifier: str) -> Optional[Dict[str, Any]]:
    is_uuid = validate_uuid(identifier)
    h_info = None
    m_info = None

    if is_uuid:
        h_info = hiddify_handler.user_info(identifier)
        m_info = marzban_handler.get_user_info(identifier)
    else:
        m_info = marzban_handler.get_user_by_username(identifier)
        if m_info and m_info.get('uuid'):
            h_info = hiddify_handler.user_info(m_info['uuid'])

    if not h_info and not m_info:
        return None

    if h_info and not m_info:
        h_info['breakdown'] = {'hiddify': h_info}
        return h_info
        
    if m_info and not h_info:
        m_info['breakdown'] = {'marzban': m_info}
        return m_info

    if h_info and m_info:
        combined = h_info
        combined['breakdown'] = {'hiddify': h_info, 'marzban': m_info}
        
        total_limit = h_info.get('usage_limit_GB', 0) + m_info.get('usage_limit_GB', 0)
        total_usage = h_info.get('current_usage_GB', 0) + m_info.get('current_usage_GB', 0)
        
        combined['usage_limit_GB'] = total_limit
        combined['current_usage_GB'] = total_usage
        combined['remaining_GB'] = max(0, total_limit - total_usage)
        combined['usage_percentage'] = (total_usage / total_limit * 100) if total_limit > 0 else 0
        
        h_online = h_info.get('last_online')
        m_online = m_info.get('last_online')
        if m_online and (not h_online or m_online > h_online):
            combined['last_online'] = m_online

        return combined
        
    return None # Should not be reached, but as a fallback

def delete_user_from_all_panels(identifier: str) -> bool:
    info = get_combined_user_info(identifier)
    if not info:
        return False

    h_success, m_success = True, True
    
    # Use the combined info to find the correct identifiers for deletion
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
    # This function combines users from both panels for broad reports.
    all_users_map = {}
    
    # Start with Hiddify users, which have UUIDs as primary keys.
    h_users = hiddify_handler.get_all_users()
    for user in h_users:
        uuid = user['uuid']
        user['breakdown'] = {'hiddify': user}
        all_users_map[uuid] = user

    # Now, add or merge Marzban users.
    m_users = marzban_handler.get_all_users()
    for user in m_users:
        uuid = user.get('uuid') # This might be None
        
        if uuid and uuid in all_users_map:
            # User is in both panels, merge the data.
            # This logic is a simplified version of get_combined_user_info
            # You can expand this if reports need combined totals.
            all_users_map[uuid]['breakdown']['marzban'] = user
        elif uuid:
            # User is only in Marzban but has a mapped UUID for some reason.
            user['breakdown'] = {'marzban': user}
            all_users_map[uuid] = user
        else:
            # User is only in Marzban and has no UUID. Use their name as a unique key for the report.
            user['breakdown'] = {'marzban': user}
            all_users_map[user['name']] = user
            
    return list(all_users_map.values())

def search_user(query: str) -> List[Dict[str, Any]]:
    query_lower = query.lower()
    results = []
    found_identifiers = set() # To avoid duplicates (e.g., user in both panels)

    # Search Hiddify panel by name or UUID
    hiddify_users = hiddify_handler.get_all_users()
    for user in hiddify_users:
        if query_lower in user.get('name', '').lower() or query_lower in user.get('uuid', ''):
            identifier = user.get('uuid')
            if identifier not in found_identifiers:
                results.append({**user, 'panel': 'hiddify'})
                found_identifiers.add(identifier)

    # Search Marzban panel by username
    marzban_users = marzban_handler.get_all_users()
    for user in marzban_users:
        identifier = user.get('uuid') or user.get('name')
        if identifier in found_identifiers:
            continue
        if query_lower in user.get('name', '').lower():
            results.append({**user, 'panel': 'marzban'})
            found_identifiers.add(identifier)

    return results