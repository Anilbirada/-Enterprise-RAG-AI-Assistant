# Enterprise RAG Automated Benchmark Report

**Execution Timestamp:** `2026-11-15T13:53:54.505446+00:00`  
**Total Samples Evaluated:** `5`  
**Average Latency:** `120.0 ms`

## Summary Scores (Scale 0.0 - 1.0)

| Metric | Score | Status | Description |
| :--- | :---: | :---: | :--- |
| **Faithfulness / Groundedness** | `1.0000` | ✅ PASS | Factual adherence to retrieved source chunks |
| **Answer Relevance** | `0.8405` | ✅ PASS | Query alignment and semantic completeness |
| **Context Precision** | `1.0000` | ✅ PASS | Mean Average Precision of relevant chunks |
| **Context Recall** | `1.0000` | ✅ PASS | Coverage of necessary ground-truth facts |
| **Citation Accuracy** | `0.9000` | ✅ PASS | Verification of bracket citations against source |
| **Overall RAG Benchmark Score** | `0.9451` | ✅ PASS | Weighted composite benchmark performance |

## Sample Breakdown

| ID | Query | Faithfulness | Relevance | Precision | Recall | Citations | Overall |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `eval-001` | What is the company policy regarding r... | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | **1.00** |
| `eval-002` | What are our customer SLA response tim... | 1.00 | 0.73 | 1.00 | 1.00 | 0.50 | **0.86** |
| `eval-003` | How does the engineering onboarding pr... | 1.00 | 0.88 | 1.00 | 1.00 | 1.00 | **0.97** |
| `eval-004` | What is the data retention schedule fo... | 1.00 | 0.73 | 1.00 | 1.00 | 1.00 | **0.93** |
| `eval-005` | What are the annual PTO accrual rates ... | 1.00 | 0.88 | 1.00 | 1.00 | 1.00 | **0.97** |

---
*Report generated automatically by the Enterprise RAG Evaluation Engine.*