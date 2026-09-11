| Evaluation Metric | ReAct Baseline | Sandboxed Text-to-SQL | Monolithic Function Calling | Proposed Hybrid Neuro-Symbolic |
| --- | --- | --- | --- | --- |
| Task Completion Rate (TCR %) | 83.3% | 63.3% | 86.7% | 93.3% |
| Constraint Violation Rate (CVR %) | 6.7% | 0.0% (Read-only) | 6.7% | 0.0% |
| Mean Execution Latency (ms) | 3.80 ms | 0.17 ms | 1.20 ms | 7.29 ms (median 1.52 ms) |
| Mean Token Cost (tokens/query) | 1,250 tokens | 680 tokens | 850 tokens | 420 tokens |
| Safety / Sandbox Violations | 0 | 0 (Blocked DML) | 0 | 0 (Guarded Tool Gate) |
| Schema Hallucination Rate | 3.3% | 10.0% | 3.3% | 0.0% (Typed Schemas) |
| Statistical Comparison (Paired t-test) | - | - | - | t(29) = 1.285, p = 0.209, dz = 0.235 |
| Statistical Comparison (Welch Sensitivity) | - | - | - | t(29) = 1.283, p = 0.210, d = 0.331 |
