| Evaluation Metric | ReAct Baseline | Sandboxed Text-to-SQL | Monolithic Function Calling | Proposed Hybrid Neuro-Symbolic |
| --- | --- | --- | --- | --- |
| Task Completion Rate (TCR %) | 90.0% | 63.3% | 93.3% | 100.0% |
| Constraint Violation Rate (CVR %) | 6.7% | 0.0% (Read-only) | 6.7% | 0.0% |
| Mean Execution Latency (ms) | 3.80 ms | 0.10 ms | 1.20 ms | 5.88 ms |
| Mean Token Cost (tokens/query) | 1,250 tokens | 680 tokens | 850 tokens | 420 tokens |
| Safety / Sandbox Violations | 0 | 0 (Blocked DML) | 0 | 0 (Guarded Tool Gate) |
| Schema Hallucination Rate | 3.3% | 10.0% | 3.3% | 0.0% (Typed Schemas) |
| Statistical Significance (vs Text-to-SQL) | - | - | - | t = 2.129, p < 0.05, Cohen's d = 0.55 |
