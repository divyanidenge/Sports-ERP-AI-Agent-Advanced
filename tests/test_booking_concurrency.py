import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi.testclient import TestClient
from app.main import app

def test_simultaneous_concurrent_bookings_on_same_court_and_slot(admin_token):
    """
    Concurrency Test:
    Simulates 5 concurrent threads attempting to book the EXACT SAME facility, date, and slot simultaneously.
    Verifies that the partial unique index and atomic transaction guard ensures EXACTLY ONE booking succeeds,
    and the other 4 receive clean HTTP 400 conflict responses.
    """
    target_facility_id = 1 # Badminton Court 1
    target_sport_id = 2    # Badminton
    target_date = "2026-11-20"
    target_slot = "18:00 - 19:00"

    headers = {"Authorization": f"Bearer {admin_token}"}

    def attempt_booking(thread_idx):
        # Create dedicated client per thread to simulate independent concurrent HTTP connections
        local_client = TestClient(app)
        return local_client.post(
            "/bookings",
            json={
                "facility_id": target_facility_id,
                "sport_id": target_sport_id,
                "booking_date": target_date,
                "time_slot": target_slot,
                "notes": f"Concurrent thread #{thread_idx}"
            },
            headers=headers
        )

    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(attempt_booking, i) for i in range(5)]
        for future in as_completed(futures):
            results.append(future.result())

    success_count = sum(1 for r in results if r.status_code == 200)
    conflict_count = sum(1 for r in results if r.status_code == 400)

    assert success_count == 1, f"Expected exactly 1 successful booking, got {success_count}"
    assert conflict_count == 4, f"Expected 4 conflicts, got {conflict_count}"

    for r in results:
        if r.status_code == 400:
            assert "already booked" in r.json()["detail"]

def test_idempotency_key_prevents_duplicate_booking(client, student_token):
    """
    Idempotency Test:
    Submitting two requests with the same idempotency key returns the existing booking
    without creating a duplicate database entry.
    """
    headers = {"Authorization": f"Bearer {student_token}"}
    idemp_key = "idemp_test_uuid_2026_xyz"

    req_payload = {
        "facility_id": 2, # Badminton Court 2
        "sport_id": 2,
        "booking_date": "2026-11-21",
        "time_slot": "16:00 - 17:00",
        "notes": "Idempotent booking test",
        "idempotency_key": idemp_key
    }

    # Request 1
    resp1 = client.post("/bookings", json=req_payload, headers=headers)
    assert resp1.status_code == 200
    booking1 = resp1.json()

    # Request 2 (Duplicate with same idempotency key)
    resp2 = client.post("/bookings", json=req_payload, headers=headers)
    assert resp2.status_code == 200
    booking2 = resp2.json()

    # Verify both requests return the exact same booking ID
    assert booking1["id"] == booking2["id"]
    assert booking1["idempotency_key"] == idemp_key
    assert booking2["idempotency_key"] == idemp_key
