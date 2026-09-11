# EXPERIMENTAL RESULTS REPORT
## Sports ERP AI Management System: Empirical Benchmark & Ablation Study Data

**Date**: August 31, 2026  
**Environment**: Windows 11 Enterprise, Python 3.14.6, SQLite 3.45, Pytest 9.1.1  
**Target Database**: `sports_erp.db` (Live SQLite Store) & `sports_erp_test.db` (Test Sandbox)  

---

## 1. 30-Scenario Four-Paradigm Empirical Benchmark

Source Script: [`app/expanded_benchmark.py`](file:///c:/Users/hp/Downloads/sports_erp_code/app/expanded_benchmark.py)  
Machine-Readable Output: [`benchmark_results.json`](file:///c:/Users/hp/Downloads/sports_erp_code/benchmark_results.json)  

### Summary Metrics

| Operational Paradigm | Task Completion Rate (TCR %) | Constraint Violation Rate (CVR %) | Mean Latency (ms) | Std Dev Latency (ms) | Mean Token Cost (tokens/query) | Safety Violations |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. ReAct Baseline** (Yao et al., 2023) | 83.3% | 6.7% | 3.80 ms | 0.00 ms | 1,250 tokens | 0 |
| **2. Sandboxed Text-to-SQL** (Kim et al., 2025) | 63.3% | 0.0% (Read-only) | 0.17 ms | 0.20 ms | 680 tokens | 0 (Blocked DML) |
| **3. Monolithic Function Calling** | 86.7% | 6.7% | 1.20 ms | 0.00 ms | 850 tokens | 0 |
| **4. Proposed Hybrid Neuro-Symbolic** (Ours) | **93.3%** | **0.0%** | **7.29 ms** *(median 1.52 ms)* | **30.41 ms** | **420 tokens** | **0** |

### Statistical Comparison: Proposed Hybrid vs. Sandboxed Text-to-SQL ($N = 30$)
- **Scenario-Matched Paired $t$-test (Primary)**: $t(29) = 1.285, p = 0.209, d_z = 0.235$ (No statistically significant latency difference)
- **Independent Welch Sensitivity Analysis (Secondary)**: $t(29) = 1.283, p = 0.210, d = 0.331$
- **Mean Delta**: $+7.12\text{ ms}$ (Computational trade-off for multi-turn intent routing, dynamic uncertainty scoring, 8-rule deterministic constraint checks, and linear SHA-256 hash chaining)

---

## 2. Systematic Component Ablation Study (30 Scenarios)

Source Script: [`scratch/run_ablation_study.py`](file:///c:/Users/hp/Downloads/sports_erp_code/scratch/run_ablation_study.py)  
Artifact: [`research_paper/tables/table7_ablation.csv`](file:///c:/Users/hp/Downloads/sports_erp_code/research_paper/tables/table7_ablation.csv)  

| System Configuration / Ablation | Constraint Engine | 2-Step Confirmation | Zero-Trust RBAC | Cryptographic Provenance | Task Success (%) | Invalid Commits (%) | Privacy Leaks (%) | Mean Latency (ms) |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **Full Proposed System (Ours)** | Enabled (C1–C8 + MUS) | Enabled (10m TTL) | Enabled (Student/Admin) | Enabled (Linear SHA-256 Hash Chain) | **100.0%** | **0.0%** | **0.0%** | **6.89 ms** |
| **Ablation 1: No Constraint Engine** | Disabled (NLP only) | Enabled (10m TTL) | Enabled (Student/Admin) | Enabled (Linear SHA-256 Hash Chain) | 86.7% | 13.3% | 0.0% | 0.80 ms |
| **Ablation 2: No Confirmation Gate** | Enabled (C1–C8 + MUS) | Disabled (Auto-commit) | Enabled (Student/Admin) | Enabled (Linear SHA-256 Hash Chain) | 96.7% | 3.3% | 0.0% | 0.50 ms |
| **Ablation 3: No RBAC Isolation** | Enabled (C1–C8 + MUS) | Enabled (10m TTL) | Disabled (Global Tools) | Enabled (Linear SHA-256 Hash Chain) | 90.0% | 0.0% | 10.0% | 0.40 ms |
| **Ablation 4: No Provenance Ledger** | Enabled (C1–C8 + MUS) | Enabled (10m TTL) | Enabled (Student/Admin) | Disabled (Plain Rows) | 100.0% | 0.0% | 0.0% | 6.84 ms |

### Key Ablation Insights:
1. **Constraint Engine Impact**: Disabling the neuro-symbolic constraint engine causes a **13.3% invalid commit rate**, where out-of-hours requests (`11 PM`), past dates (`2020-01-01`), and exceeded student quotas are illegally committed.
2. **Confirmation Gate Impact**: Disabling 2-step confirmation and uncertainty gating leads to a **3.3% invalid commit rate**, where ambiguous cancellation requests mutate user bookings without user disambiguation.
3. **RBAC Isolation Impact**: Disabling zero-trust role boundaries causes a **10.0% privacy leakage rate**, allowing students to view peer reservation details and administrative directories.
4. **Provenance Overhead**: Cryptographic hash chaining introduces an imperceptible **0.05 ms** computational overhead (6.89 ms vs. 6.84 ms) while providing complete mathematical tamper-evidence.

---

## 3. Five-Tier System Verification Suite Breakdown

```text
========================================================================================
Verification Layer               Assertion Count    Passing    Failing    Success Rate
========================================================================================
1. Pytest Automated Test Suite          94             94         0          100.0%
2. Live DB Smoke Tests                  20             20         0          100.0%
3. API Integration Suite                19             19         0          100.0%
4. Conversational NLP Suite             29             29         0          100.0%
5. Bug-Fix Regression Suite              4              4         0          100.0%
----------------------------------------------------------------------------------------
Total System Assertions                166            166         0          100.0%
========================================================================================
```
