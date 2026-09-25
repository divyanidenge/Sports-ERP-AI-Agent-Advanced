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

## 🔬 Research & Experimental Modules

### 1. Z3 SMT Combinatorial Tournament Scheduler (`app/tournament_solver.py`)
- **Engine**: Microsoft Z3 SMT Solver with bounded integer arithmetic.
- **Formulation**: Eliminates pairwise court overlap, team concurrent scheduling, and enforces minimum physical rest intervals ($\ge 2$ hours).
- **Unsat Core Reporting**: Pinpoints exact conflicting constraints (court capacity, team rest interval bottlenecks) when a tournament cannot be scheduled.

### 2. Machine Learning Facility Demand Forecasting (`app/demand_forecaster.py`, `app/demand_dataset.py`)
- **Dataset**: `[SYNTHETIC DATASET — RESEARCH EXPERIMENTATION ONLY]` 20,440 hourly records across 365 days generated using domain heuristics (diurnal morning/evening peaks, exam schedules, weather).
- **Model**: Gradient Boosting Regressor (80/20 train/test chronological split).
- **Empirical Results**: MAE: 7.47% occupancy (vs Historical Mean Baseline MAE: 10.77%), achieving a **30.64% relative MAE improvement**.
- **Advisory Output**: Provides congestion classification and low-demand alternative slot recommendations.

### 3. Optional Voice Interaction Pipeline (`app/voice_service.py`)
- **STT**: `SpeechRecognition` library handling audio input.
- **TTS**: `gTTS` (Google Text-to-Speech) with `pyttsx3` offline fallback.
- **Architecture**: Directly reuses existing agent reasoning and verification pipeline without modifying backend business logic.

---

## 📊 Reproducible Experimental Benchmarks

Run the standalone empirical benchmarks with the following commands:

```bash
# 1. Z3 SMT Tournament Scheduling Benchmark
python tests/benchmark_tournament.py

# 2. Machine Learning Demand Forecasting Benchmark
python tests/benchmark_forecasting.py

# 3. Confirmation Policy Simulation Benchmark [50 Scenarios]
python tests/benchmark_confirmation_policies.py

# 4. Voice Interaction Latency & Pipeline Benchmark
python tests/benchmark_voice.py

# 5. Full Unit & Integration Test Suite (106 Tests)
pytest -v
```

---

## 🛡️ Research Integrity & Ethical Disclosures

1. **Synthetic Datasets**: All demand forecasting models are evaluated strictly on synthetic facility usage logs (`app/demand_dataset.py`). No real-world student personal health or athletic tracking data was collected.
2. **Simulation Benchmarks**: The confirmation policy evaluations (`tests/benchmark_confirmation_policies.py`) are automated algorithmic simulations across 50 scripted dialog scenarios. No human-subject clinical or behavioral trials were conducted.
3. **Reproducibility**: All benchmark scripts log deterministic JSON metrics (`tournament_benchmark_results.json`, `forecast_benchmark_results.json`, `confirmation_benchmark_results.json`, `voice_benchmark_results.json`) directly into the repository.
