# REPRODUCIBILITY GUIDE
## Sports ERP AI Management System: Exact Commands and Verification Procedures

This document provides step-by-step instructions to reproduce all empirical benchmarks, unit tests, live smoke tests, ablation studies, and manuscript artifacts.

---

## 1. Prerequisites and Environment Setup

- **Operating System**: Windows 10/11, macOS, or Linux
- **Python Version**: Python 3.10+ (Tested on Python 3.14.6)
- **Virtual Environment Setup**:
  ```bash
  # Clone or navigate to the repository
  cd c:\Users\hp\Downloads\sports_erp_code

  # Install required dependencies
  pip install -r requirements.txt
  pip install pytest docx matplotlib
  ```

---

## 2. Executing Automated Test & Verification Suites

### A. Full Unit & Integration Test Suite (94 Tests)
```powershell
pytest -v
```
*Expected Output*: `94 passed, 1 warning in ~20.16s`.

### B. Live Database Smoke Tests (20 Tests on `sports_erp.db`)
```powershell
python scratch/verify_complete_research_advancements_live.py
```
*Expected Output*: `[SUCCESS] ALL 20 LIVE SMOKE TESTS PASSED PERFECTLY ON SPORTS_ERP.DB!`.

### C. FastAPI REST Gateway & Context Regression (19 Assertions)
```powershell
python test_api.py
```
*Expected Output*: `[SUCCESS] ALL REGRESSION AND INTENT TESTS PASSED PERFECTLY!`.

### D. Conversational NLP Query Suite (29 Real-World Scenarios)
```powershell
python scratch/test_all_user_manual_queries.py
```
*Expected Output*: `[SUCCESS] ALL 29 STUDENT AND ADMIN QUERIES PASSED!`.

### E. Targeted Disambiguation & Restore Regressions (4 Tests)
```powershell
python scratch/test_bug_fixes_verification.py
```
*Expected Output*: `[ALL 4 BUG REPRODUCTIONS AND FIXES PASSED 100%!]`.

---

## 3. Reproducing the 30-Scenario Benchmark & Ablation Study

### A. Execute 30-Scenario Benchmark Suite
```powershell
pytest tests/test_expanded_benchmark.py -v
```
*Artifact Generated*: `benchmark_results.json`.

### B. Execute Systematic Component Ablation Study
```powershell
python scratch/run_ablation_study.py
```
*Artifacts Generated*: `research_paper/tables/table_ablation_study.json`, `research_paper/tables/table7_ablation.csv`.

---

## 4. Re-Generating Figures, Tables, and Manuscripts

### A. Generate 300-DPI Publication Figures
```powershell
python scratch/generate_paper_figures.py
```
*Output*: 6 PNG figures in `research_paper/figures/`.

### B. Generate CSV and Markdown Research Tables
```powershell
python scratch/generate_paper_tables.py
python scratch/export_ablation_table.py
```
*Output*: 7 structured tables in `research_paper/tables/`.

### C. Build Final Research Manuscript (.DOCX & .PDF)
```powershell
python scratch/build_final_research_paper.py
```
*Output*: 
- `research_paper/Sports_ERP_AI_Final_Research_Paper.docx`
- `research_paper/Sports_ERP_AI_Final_Research_Paper.pdf`
