import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_BASE_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")

def _get_headers(token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def api_login(email, password):
    url = f"{API_BASE_URL}/auth/login"
    resp = requests.post(url, json={"email": email, "password": password}, timeout=10)
    return resp

def api_register(name, email, password, role):
    url = f"{API_BASE_URL}/auth/register"
    resp = requests.post(url, json={"name": name, "email": email, "password": password, "role": role}, timeout=10)
    return resp

def api_get_sports():
    url = f"{API_BASE_URL}/sports"
    return requests.get(url, timeout=10)

def api_add_sport(token, name, category, description, min_players, max_players):
    url = f"{API_BASE_URL}/sports"
    payload = {
        "name": name,
        "category": category,
        "description": description,
        "min_players": min_players,
        "max_players": max_players
    }
    return requests.post(url, json=payload, headers=_get_headers(token), timeout=10)

def api_delete_sport(token, sport_id):
    url = f"{API_BASE_URL}/sports/{sport_id}"
    return requests.delete(url, headers=_get_headers(token), timeout=10)

def api_get_facilities():
    url = f"{API_BASE_URL}/facilities"
    return requests.get(url, timeout=10)

def api_add_facility(token, name, sport_id, location, capacity, is_available=1):
    url = f"{API_BASE_URL}/facilities"
    payload = {
        "name": name,
        "sport_id": sport_id,
        "location": location,
        "capacity": capacity,
        "is_available": is_available
    }
    return requests.post(url, json=payload, headers=_get_headers(token), timeout=10)

def api_toggle_facility(token, facility_id):
    url = f"{API_BASE_URL}/facilities/{facility_id}/toggle"
    return requests.patch(url, headers=_get_headers(token), timeout=10)

def api_get_bookings(token, all_users=False):
    url = f"{API_BASE_URL}/bookings?all_users={'true' if all_users else 'false'}"
    return requests.get(url, headers=_get_headers(token), timeout=10)

def api_create_booking(token, facility_id, sport_id, booking_date, time_slot, notes=""):
    url = f"{API_BASE_URL}/bookings"
    payload = {
        "facility_id": facility_id,
        "sport_id": sport_id,
        "booking_date": booking_date,
        "time_slot": time_slot,
        "notes": notes
    }
    return requests.post(url, json=payload, headers=_get_headers(token), timeout=10)

def api_cancel_booking(token, booking_id):
    url = f"{API_BASE_URL}/bookings/{booking_id}"
    return requests.delete(url, headers=_get_headers(token), timeout=10)

def api_get_attendance(token):
    url = f"{API_BASE_URL}/attendance"
    return requests.get(url, headers=_get_headers(token), timeout=10)

def api_get_my_attendance(token):
    url = f"{API_BASE_URL}/attendance/my"
    return requests.get(url, headers=_get_headers(token), timeout=10)

def api_mark_attendance(token, booking_id, user_id, status="present"):
    url = f"{API_BASE_URL}/attendance"
    payload = {
        "booking_id": booking_id,
        "user_id": user_id,
        "status": status
    }
    return requests.post(url, json=payload, headers=_get_headers(token), timeout=10)

def api_get_dashboard(token):
    url = f"{API_BASE_URL}/dashboard/overview"
    return requests.get(url, headers=_get_headers(token), timeout=10)

def api_list_users(token):
    url = f"{API_BASE_URL}/auth/users"
    return requests.get(url, headers=_get_headers(token), timeout=10)

def api_block_user(token, user_id):
    url = f"{API_BASE_URL}/auth/users/{user_id}/block"
    return requests.post(url, headers=_get_headers(token), timeout=10)

def api_unblock_user(token, user_id):
    url = f"{API_BASE_URL}/auth/users/{user_id}/unblock"
    return requests.post(url, headers=_get_headers(token), timeout=10)

def api_ask_agent(token, query, session_id="default_session"):
    url = f"{API_BASE_URL}/agent/query"
    payload = {"query": query, "session_id": session_id}
    return requests.post(url, json=payload, headers=_get_headers(token), timeout=15)

def api_ask_agent_voice(token, audio_bytes, session_id="default_session", filename="recording.wav"):
    url = f"{API_BASE_URL}/agent/voice-query"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    files = {"file": (filename, audio_bytes, "audio/wav")}
    data = {"session_id": session_id}
    return requests.post(url, files=files, data=data, headers=headers, timeout=25)


def api_get_audit_logs(token, limit=50):
    url = f"{API_BASE_URL}/audit-logs?limit={limit}"
    return requests.get(url, headers=_get_headers(token), timeout=10)

def api_verify_provenance(token, audit_id):
    url = f"{API_BASE_URL}/audit/verify-provenance/{audit_id}"
    return requests.get(url, headers=_get_headers(token), timeout=10)

def api_get_advanced_analytics(token):
    url = f"{API_BASE_URL}/analytics/advanced"
    return requests.get(url, headers=_get_headers(token), timeout=10)

def api_run_comprehensive_benchmark(token):
    url = f"{API_BASE_URL}/analytics/comprehensive-benchmark"
    return requests.get(url, headers=_get_headers(token), timeout=30)
