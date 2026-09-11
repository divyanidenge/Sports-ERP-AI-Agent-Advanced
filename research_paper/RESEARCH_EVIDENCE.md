# RESEARCH EVIDENCE & EMPIRICAL BASELINE REPORT
## Sports ERP AI Management System: An Agentic AI Architecture for Conversational Resource Allocation, Neuro-Symbolic Invariant Verification, and Cryptographic Governance

**Academic Context**: M.Tech CSE (AI/ML) Master's Thesis & Peer-Reviewed Research Publication  
**Date of Verification**: August 31, 2026  
**System Repository**: `Sports-ERP-AI-Agent-Advanced` (Branch: `main`)  
**Underlying Stack**: FastAPI, Streamlit, SQLAlchemy, SQLite (`sports_erp.db`), Python 3.14, Gemini LLM / Agentic NLP  

---

## 1. Executive Ground-Truth Summary

Every claim, metric, algorithmic formulation, and architectural component presented in the research paper is directly derived from the verified source code and reproducible test suite of the Sports ERP AI Management System.

### Empirical Verification Suite Results

| Test Layer | Test Executable / Script | Assertion Count | Result | Key Subsystems Verified |
| :--- | :--- | :---: | :---: | :--- |
| **Full Unit & Integration Suite** | `pytest -v` | **94 / 94** | **100% PASSED** | C1â€“C8 Constraint Engine, MUS/MCS Solvers, Sprint Contracts, PERR Workflow, SHA-256 Ledger, SQL Sandbox, RBAC Isolation |
| **Live Database Smoke Tests** | `scratch/verify_complete_research_advancements_live.py` | **20 / 20** | **100% PASSED** | Live SQLite `sports_erp.db` persistence, user authentication, 2-step booking commit, tamper detection, benchmark export |
| **API & Context Regression** | `test_api.py` | **19 / 19** | **100% PASSED** | FastAPI endpoints, JWT auth, session TTL (10m), context disarming on unrelated interruptions, administrative lockout |
| **Conversational Query Suite** | `scratch/test_all_user_manual_queries.py` | **29 / 29** | **100% PASSED** | 18 Student intents (catalog, bookings, attendance, analytics) + 11 Admin governance intents (named resolution, audit, benchmark) |
| **Targeted Edge-Case Suite** | `scratch/test_bug_fixes_verification.py` | **4 / 4** | **100% PASSED** | Zero-candidate sport filtering, ordinal/ID disambiguation (`"id 41"`), atomic restore flow, temporal/operating hours pre-validation |
| **Total Cumulative Assertions** | **Entire System** | **166 / 166** | **100% PASSED** | Zero functional regressions, zero security bypasses, zero data corruption |

---

## 2. Five Core Research Contributions

### Contribution 1: Symbolic Minimal Unsatisfiable Subsets (MUS) & Minimal Correction Sets (MCS) Engine
* **Source Implementation**: [`app/symbolic_mus_engine.py`](file:///c:/Users/hp/Downloads/sports_erp_code/app/symbolic_mus_engine.py)
* **Underlying Theory**: Inspired by TRACE-CS (Vasileiou & Yeoh, 2024) and Boolean Core Reduction (Marques-Silva et al., 2012).
* **Formal Model**:
  $$\text{KB}_{\text{sports}} = \{C_1, C_2, C_3, C_4, C_5, C_6, C_7, C_8\}$$
  When a candidate reservation $R = \langle \text{user\_id}, \text{sport}, \text{facility}, \text{date}, \text{slot}, \text{role} \rangle$ induces unsatisfiability:
  $$\text{KB}_{\text{sports}} \cup \{R\} \models \bot$$
  The engine extracts the Minimal Unsatisfiable Subset $\mathcal{M} \subseteq \text{KB}_{\text{sports}} \cup \{R\}$ via deletion-based core reduction:
  $$\mathcal{M} \models \bot \quad \land \quad \forall c \in \mathcal{M}, \; (\mathcal{M} \setminus \{c\}) \not\models \bot$$
  It subsequently solves for the Minimal Correction Subset (MCS) $\mathcal{S}$ of parameters whose relaxation restores satisfiability:
  $$\text{MCS}(R) = \arg\min_{S \subseteq \text{Params}(R)} |S| \quad \text{s.t.} \quad \text{KB}_{\text{sports}} \cup \{R[S \leftarrow S']\} \not\models \bot$$
* **Verified Contrastive Explanations**: Produces deterministic, non-hallucinated explanations: *"Why not R? Because of conflict core M. Satisfiable if minimal relaxation S is applied (e.g. nearest available slots)."*

### Contribution 2: Dynamic Epistemic Uncertainty & Confidence-Gated Risk Harness
* **Source Implementation**: [`app/uncertainty_harness.py`](file:///c:/Users/hp/Downloads/sports_erp_code/app/uncertainty_harness.py)
* **Underlying Theory**: Continuous confidence gating $\Gamma(q, S) \in [0.0, 1.0]$:
  $$\Gamma(q, S) = w_E E_{\text{conf}} + w_A A_{\text{card}} + w_T T_{\text{det}} - w_R R_{\text{act}} + w_Q Q_{\text{safe}}$$
* **Execution Tiers**:
  1. `LOW_RISK_AUTO_EXECUTE` ($\Gamma \ge 0.85$ and Read-Only): Immediate autonomous execution and response synthesis.
  2. `MEDIUM_RISK_DISAMBIGUATION` ($0.50 \le \Gamma < 0.85$ or Ambiguous Cardinality): Prompts user with numbered candidate options (e.g., multiple active bookings).
  3. `HIGH_RISK_CONFIRMATION` ($\Gamma < 0.50$ or Consequential State Modification): Arms 2-step protected confirmation in session context.

### Contribution 3: Cryptographic Decision Provenance Ledger & Linear SHA-256 Hash Chaining
* **Source Implementation**: [`app/provenance_engine.py`](file:///c:/Users/hp/Downloads/sports_erp_code/app/provenance_engine.py), [`app/audit_service.py`](file:///c:/Users/hp/Downloads/sports_erp_code/app/audit_service.py)
* **Formal Model**:
  Every consequential state transition commits an audit record with a chained cryptographic token $\Pi_t$:
  $$P_t = \text{user\_id} \parallel \text{action} \parallel \text{resource\_type} \parallel \text{resource\_id} \parallel \text{details} \parallel \text{status}$$
  $$\Pi_t = \text{SHA256}(P_t \parallel \Pi_{t-1}), \quad \text{where } \Pi_0 = 0^{64}$$
* **Tamper Verification**: Forward and single-record verification endpoints (`GET /audit/verify/{id}`) verify payload hashes and predecessor links. Simulated bit-level tampering tests confirm 100% tamper detection.

### Contribution 4: Adaptive Sprint Contracts & Formal Reflection (PERR Workflow)
* **Source Implementation**: [`app/sprint_contract.py`](file:///c:/Users/hp/Downloads/sports_erp_code/app/sprint_contract.py), [`app/agents/orchestrator.py`](file:///c:/Users/hp/Downloads/sports_erp_code/app/agents/orchestrator.py)
* **Formal Model**:
  Planner creates a Sprint Contract $C = (\text{Goal}, A_{\text{crit}}, D_{\text{exp}}, G_{\text{rubric}}, \theta_{\text{accept}}=0.75)$.
  Reflector scores execution outputs against a weighted multi-attribute rubric:
  $$S(y) = 0.30 s_{\text{comp}} + 0.30 s_{\text{acc}} + 0.25 s_{\text{cons}} + 0.15 s_{\text{eff}}$$
  If $S(y) < 0.75$, triggers at most one bounded replan cycle ($K \le 1$) with decorrelated structural feedback.

### Contribution 5: 30-Scenario 4-Paradigm Empirical Benchmark
* **Source Implementation**: [`app/expanded_benchmark.py`](file:///c:/Users/hp/Downloads/sports_erp_code/app/expanded_benchmark.py), [`benchmark_results.json`](file:///c:/Users/hp/Downloads/sports_erp_code/benchmark_results.json)
* **Evaluated Paradigms**:
  1. ReAct Baseline (Yao et al., 2023)
  2. Sandboxed Read-Only Text-to-SQL (Kim et al., 2025)
  3. Monolithic Function Calling (Standard LLM Agent)
  4. Proposed Hybrid Neuro-Symbolic Agentic ERP
* **Empirical Results Summary**:
  - Proposed Task Completion Rate: **93.3%** (vs. 63.3% Text-to-SQL, 83.3% ReAct, 86.7% Monolithic FC)
  - Constraint Violation Rate: **0.0%** (vs. 6.7% ReAct, 6.7% Monolithic FC)
  - Mean Latency: Proposed **7.29 ms** (median 1.52 ms) vs. Text-to-SQL 0.17 ms.
  - Statistical Comparison vs. Text-to-SQL: Paired $t(29) = 1.285$, $p = 0.209$, $d_z = 0.235$ (Welch: $t(29) = 1.283$, $p = 0.210$, $d = 0.331$).

---

## 3. Database Schema & Data Models

* **`users` Table**: `id` (PK), `name`, `email` (UNIQUE), `hashed_password` (PBKDF2 100k iter), `role` ('student' | 'admin'), `is_blocked` (0 | 1), `created_at`.
* **`sports` Table**: `id` (PK), `name` (UNIQUE), `category`, `description`, `min_players`, `max_players`, `created_at`.
* **`facilities` Table**: `id` (PK), `name`, `sport_id` (FK sports), `location`, `capacity`, `is_available` (0 | 1), `created_at`.
* **`bookings` Table**: `id` (PK), `user_id` (FK users), `facility_id` (FK facilities), `sport_id` (FK sports), `booking_date`, `time_slot`, `status` ('confirmed' | 'cancelled'), `notes`, `idempotency_key` (UNIQUE), `created_at`.
  - *Concurrency Index*: `CREATE UNIQUE INDEX idx_active_facility_booking ON bookings (facility_id, booking_date, time_slot) WHERE status = 'confirmed'`.
* **`attendance` Table**: `id` (PK), `booking_id` (FK bookings), `user_id` (FK users), `check_in_time`, `status` ('present' | 'absent'), `marked_by` (FK users), `created_at`.
* **`audit_logs` Table**: `id` (PK), `user_id`, `user_email`, `action`, `resource_type`, `resource_id`, `details`, `status`, `ip_address`, `provenance_token`, `prev_provenance_token`, `created_at`.

---

## 4. Codebase Evidence Cross-Reference Table

| Research Claim / Feature | Source File in Codebase | Line Numbers / Verification Function |
| :--- | :--- | :--- |
| **8 Deterministic Invariants (C1â€“C8)** | `app/constraint_engine.py` | Lines 45â€“185 (`evaluate_all_constraints`) |
| **MUS/MCS Core Reduction & Solver** | `app/symbolic_mus_engine.py` | Lines 120â€“310 (`extract_mus`, `compute_mcs_relaxations`) |
| **Dynamic Uncertainty Scoring $\Gamma(q, S)$** | `app/uncertainty_harness.py` | Lines 44â€“145 (`evaluate_uncertainty`) |
| **Linear SHA-256 Hash Chain Provenance** | `app/provenance_engine.py` | Lines 45â€“125 (`compute_payload_token`, `verify_provenance_chain`) |
| **Sprint Contracts & PERR Scoring $S(y)$** | `app/sprint_contract.py` | Lines 51â€“140 (`evaluate_contract_satisfaction`) |
| **Specialist Multi-Agent Swarm** | `app/agents/` | `booking_agent.py`, `availability_agent.py`, `attendance_agent.py`, `analytics_agent.py`, `governance_agent.py` |
| **Two-Stage Intent Router** | `app/agents/orchestrator.py` | Lines 55â€“120 (`route_query_to_agents`) |
| **Two-Step Affirmation & Context TTL** | `app/query_agent.py` | Lines 210â€“350 (Session context & pending action disarming) |
| **Multi-Turn Disambiguation & Restore** | `app/query_agent.py` | Lines 615â€“770 (Candidate follow-ups & `restore_booking`) |
| **Atomic Booking Restore & Audit** | `app/sports_service.py` | Lines 376â€“488 (`restore_booking`) |
| **Sandboxed SQL Interceptor** | `app/expanded_benchmark.py` | Lines 65â€“110 (`execute_sandboxed_sql`) |
| **30-Scenario Empirical Benchmark** | `app/expanded_benchmark.py` | Lines 180â€“360 (`run_expanded_benchmark_suite`) |
