# 🏅 Campus Sports ERP & AI Assistant System

A comprehensive, production-ready University Sports ERP system with **FastAPI Backend**, **Streamlit Frontend**, **SQLite Database**, **Role-Based Access Control (RBAC)**, and an **Intelligent AI Assistant** capable of answering natural-language queries and executing administrative commands (such as blocking/unblocking users).

---

## 🌟 Key Features

1. **Role-Based Authentication (RBAC):**
   - Student & Admin registration and login with secure PBKDF2-SHA256 password hashing and JWT access tokens.
   - Real-time account status checks (blocked accounts cannot log in and have access revoked immediately).

2. **Sports & Facilities Management:**
   - Sports discipline catalog (indoor, outdoor, aquatic, racket sports with min/max player constraints).
   - Multi-facility management with location tracking, capacity limits, and operational availability toggles.

3. **Smart Booking System:**
   - Conflict-free court reservation with automated double-booking prevention.
   - Student self-service reservation management and cancellation workflows.

4. **Attendance Tracking:**
   - Check-in verification system for reserved slots with timestamps and status logging.

5. **User Administration (Admin Only):**
   - Interactive user directory with account status controls (Instant Block / Unblock buttons).

6. **🤖 AI Assistant Chat:**
   - Natural language query understanding:
     - *"show my bookings"* / *"check my schedule"*
     - *"list sports"* / *"show available sports"*
     - *"show facilities"* / *"list courts"*
     - *"show overview"* / *"dashboard stats"*
   - **Automated Admin Actions via Chat:**
     - Type `"block user id 3"` -> instantly blocks user #3 (Admin only; student attempts are denied).
     - Type `"unblock user id 3"` -> restores account access.
     - Type `"list all users"` -> outputs interactive user directory table.
   - **Open-Ended AI Fallback:** Powered by Google Gemini (when `GEMINI_API_KEY` is provided) or smart contextual campus advisor.

---

## 📁 Project Architecture

```
sports_erp/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py             # Environment configuration & JWT settings
│   │   ├── database.py           # SQLite connection, schemas & seed data
│   │   ├── models.py             # Pydantic data validation schemas
│   │   ├── auth.py               # JWT tokens & role dependencies
│   │   ├── auth_service.py       # Authentication & user operations
│   │   ├── auth_router.py        # /auth endpoints
│   │   ├── sports_service.py     # Sports, Facilities, Bookings & Dashboard logic
│   │   ├── sports_router.py      # /sports, /facilities, /bookings, /attendance routes
│   │   ├── query_agent.py        # AI Agent NLP parser, actions & Gemini fallback
│   │   ├── agent_router.py       # /agent/query endpoint
│   │   └── main.py               # FastAPI application definition & CORS
│   ├── main.py                   # Root runner entrypoint
│   ├── test_api.py               # Comprehensive automated test suite
│   ├── .env.example
│   ├── .env
│   └── requirements.txt
├── frontend/
│   ├── api_client.py             # HTTP client helper for FastAPI communication
│   ├── streamlit_app.py          # Complete multi-page Streamlit application
│   ├── .env.example
│   ├── .env
│   └── requirements.txt
└── README.md
```

---

## 🚀 Quickstart Guide

### 1. Default Pre-Seeded Accounts

When the backend starts, the SQLite database is automatically created with sample data and the following accounts:

| Role | Email | Password |
| :--- | :--- | :--- |
| **Admin** | `admin@sports.edu` | `admin123` |
| **Student 1** | `student@sports.edu` | `student123` |
| **Student 2** | `priya@sports.edu` | `priya123` |
| **Student 3** | `amit@sports.edu` | `amit123` |

---

### 2. Backend Setup & Run

Open a terminal and navigate to `backend/`:

```bash
cd backend

# 1. Create and activate virtual environment (optional but recommended)
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Mac/Linux:
# source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start FastAPI server
uvicorn main:app --reload --port 8000
```

- API Base URL: `http://localhost:8000`
- Interactive Swagger Documentation: `http://localhost:8000/docs`

---

### 3. Frontend Setup & Run

Open a separate terminal and navigate to `frontend/`:

```bash
cd frontend

# 1. Create and activate virtual environment (optional but recommended)
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Mac/Linux:
# source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start Streamlit web app
streamlit run streamlit_app.py
```

- Browser will automatically open at: `http://localhost:8501`

---

## 🧪 Running Automated Tests

A complete verification test suite is included in `backend/test_api.py` that verifies all 13 core workflows end-to-end:

```bash
cd backend
python test_api.py
```

Expected output:
```
============================================================
🚀 STARTING SPORTS ERP END-TO-END VERIFICATION
============================================================
✅ 1. Health check passed
✅ 2. Admin Login successful (JWT acquired)
✅ 3. Student Login successful (JWT acquired)
✅ 4. Student asks AI 'show my bookings' -> Responded: 'Found 2 booking(s)...'
✅ 5. Student attempts 'block user id 1' -> Correctly denied
✅ 6. Admin commands 'block user id 2' -> Action Executed: User ID 2 blocked
✅ 7. Blocked student tries to login -> Correctly rejected (403 Forbidden)
✅ 8. Admin commands 'unblock id 2' -> Action Executed: User ID 2 unblocked
✅ 9. Unblocked student logs in again -> Restored successfully
✅ 10. AI query 'list sports' -> Returned 6 sports
✅ 11. AI query 'show overview' -> KPI Stats retrieved
✅ 12. Admin query 'list all users' -> Retrieved users list
✅ 13. Open-ended fallback question -> Answered cleanly
============================================================
🎉 ALL 13 TEST CASES PASSED SUCCESSFULLY!
============================================================
```

---

## 🔑 Optional: Google Gemini API Key

The core NLP intent parser, booking engine, and administrative actions work 100% locally with zero external API dependencies. 

If you would like advanced open-ended reasoning for free-form questions in the AI Assistant:
1. Get a free API key from [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Set it in `backend/.env`:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```
3. Restart the backend server.
