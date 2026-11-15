# Enterprise RAG Automated Evaluation & Benchmarking

## 1. Overview & Methodology

Retrieval-Augmented Generation (RAG) systems in enterprise environments require rigorous, automated quality evaluation. Unlike traditional classification or regression models, RAG quality depends on the interplay between **retrieval quality** (did the retriever surface the right facts?) and **generation quality** (did the LLM accurately synthesize the answer without hallucination?).

Our automated evaluation framework implements the standard RAG evaluation triad supplemented by citation precision metrics:

```
                  ┌──────────────────────┐
                  │      User Query      │
                  └──────────┬───────────┘
                             │
              Answer Relevance (Relevance)
                             │
                             ▼
  ┌─────────────────┐ ◄──────────────► ┌──────────────────┐
  │ Retrieved Chunks│                  │ Generated Answer │
  └────────┬────────┘                  └────────┬─────────┘
           │                                    │
           │◄────── Faithfulness & Citations ───┤
           │          (Groundedness)            │
           ▼                                    ▼
┌──────────────────────┐               ┌──────────────────┐
│ Reference Contexts   │               │ Ground Truth     │
│ (Context Precision & │               │ (Answer Recall)  │
│  Context Recall)     │               └──────────────────┘
└──────────────────────┘
```

---

## 2. Core Evaluation Metrics

### 2.1 Faithfulness / Groundedness ($\in [0.0, 1.0]$)
- **Definition**: The proportion of factual claims in the generated response that are directly supported by retrieved source chunks.
- **Mathematical Formulation**:
  $$\text{Faithfulness} = \frac{|\text{Supported Claims in Answer}|}{|\text{Total Claims in Answer}|}$$
- **Scoring Logic**:
  - The answer is segmented into constituent sentences/clauses.
  - Bracket citations (e.g. `[1]`) are stripped before parsing.
  - For each sentence, content tokens, entities, and numeric values are verified against the concatenated retrieved contexts.
  - A claim is marked supported if $\ge 40\%$ of content tokens and 100% of numeric quantities are corroborated by the context.
  - Target SLA: $\ge 0.85$.

### 2.2 Answer Relevance ($\in [0.0, 1.0]$)
- **Definition**: Evaluates whether the generated response directly answers the user's inquiry without extraneous digression or evasiveness.
- **Mathematical Formulation**:
  $$\text{Relevance} = 0.75 \times \min\left(1.0, \frac{\text{Query Term Recall}}{0.45}\right) + 0.25 \times \text{Substance Score}$$
- **Scoring Logic**:
  - Direct answers to complex queries naturally address the key interrogative focus (typically 40%–60% of query content terms).
  - Substantive length is factored in to penalize abrupt single-word or truncated responses.
  - Explicit refusal patterns ("I do not know", "No relevant documents found") yield a reduced baseline score (0.25) when answering was expected.
  - Target SLA: $\ge 0.80$.

### 2.3 Context Precision ($\in [0.0, 1.0]$)
- **Definition**: Evaluates whether relevant document chunks appear higher in the retriever's ranking list (Mean Average Precision @ K).
- **Mathematical Formulation**:
  $$\text{Context Precision} = \frac{\sum_{k=1}^K (\text{Precision}@k \times v_k)}{\sum_{k=1}^K v_k}$$
  where $v_k = 1$ if chunk $k$ is relevant to ground truth, and 0 otherwise.
- **Scoring Logic**:
  - Rewards rankers (such as our hybrid dense + sparse Reciprocal Rank Fusion) that position the most relevant chunks in rank 1 or 2.
  - Target SLA: $\ge 0.75$.

### 2.4 Context Recall ($\in [0.0, 1.0]$)
- **Definition**: The proportion of reference ground-truth facts successfully captured by the retrieval pipeline.
- **Mathematical Formulation**:
  $$\text{Context Recall} = \frac{|\text{Ground-Truth Reference Facts Retrieved}|}{|\text{Total Ground-Truth Reference Facts}|}$$
- **Target SLA**: $\ge 0.80$.

### 2.5 Citation Accuracy ($\in [0.0, 1.0]$)
- **Definition**: Measures the correctness and precision of in-text bracket citations (`[1]`, `[2]`).
- **Verification Checks**:
  1. **Index Boundary**: Ensures citation index $1 \le k \le K$ exists within the retrieved chunk set.
  2. **Corroboration Alignment**: Verifies that the specific claim immediately preceding bracket `[k]` matches the semantics of context $k-1$.
- **Target SLA**: $\ge 0.85$.

---

## 3. Golden Evaluation Benchmark Dataset

The system includes a multi-domain enterprise benchmark (`GOLDEN_EVALUATION_DATASET`) covering critical enterprise knowledge domains:

| Sample ID | Domain | Query Focus | Key Verified Fact |
| :--- | :--- | :--- | :--- |
| `eval-001` | **IT Security** | Remote Work & VPN Policy | Mandatory GlobalProtect VPN, MFA, Split tunneling prohibited |
| `eval-002` | **Customer Success** | SLA Uptime & Response Targets | 99.9% uptime, Sev-1 15 min response, Sev-2 2 hr response |
| `eval-003` | **Engineering** | Code Reviews & Branching | Feature branches required, 2 senior reviews before merge to main |
| `eval-004` | **Legal Compliance** | GDPR PII Retention Schedule | 30-day purge post-termination, 365-day audit log retention |
| `eval-005` | **Human Resources** | Annual PTO Accrual & Rollover | 20 days/year pro-rata, max 5 days rollover to next year |

---

## 4. Benchmark Execution & CLI Usage

### Running the Benchmark Suite
```powershell
# From the backend directory
python -m app.evaluation.cli --output docs/rag-evaluation-report.md --json-output docs/rag-evaluation-report.json
```

### Output Summary Example:
```
==================================================
Overall RAG Benchmark Score: 0.9451 / 1.0000
Faithfulness:                1.0000
Answer Relevance:            0.8405
Context Precision:           1.0000
Context Recall:              1.0000
Citation Accuracy:           0.9000
==================================================
```

---

## 5. Continuous Integration (CI) Quality Gates

The benchmark runner is configured with strict quality gates for automated CI pipelines:
- `mean_faithfulness >= 0.80` (zero tolerance for ungrounded hallucination)
- `mean_answer_relevance >= 0.75`
- `mean_context_precision >= 0.70`
- `mean_context_recall >= 0.75`
- `mean_citation_accuracy >= 0.80`
- `mean_overall_score >= 0.80`
