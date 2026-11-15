import pytest
from app.evaluation.metrics import RAGMetricsEvaluator
from app.evaluation.schemas import EvaluationSample, EvaluationPrediction
from app.evaluation.runner import RAGEvaluationRunner
from app.evaluation.dataset import GOLDEN_EVALUATION_DATASET


def test_calculate_faithfulness_grounded():
    contexts = [
        "Employees must connect to the corporate VPN when working remotely. MFA is required.",
        "Workstations must have full-disk encryption enabled."
    ]
    grounded_answer = "Employees working remotely must connect to the corporate VPN with MFA enabled [1]."
    score = RAGMetricsEvaluator.calculate_faithfulness(grounded_answer, contexts)
    assert score >= 0.80


def test_calculate_faithfulness_hallucinated():
    contexts = [
        "Company policy requires 8 hours of sleep per day."
    ]
    hallucinated_answer = "Acme Corp provides free trips to Hawaii and gives each developer a Porsche 911."
    score = RAGMetricsEvaluator.calculate_faithfulness(hallucinated_answer, contexts)
    assert score == 0.0


def test_calculate_faithfulness_empty_inputs():
    assert RAGMetricsEvaluator.calculate_faithfulness("", ["Some context"]) == 0.0
    assert RAGMetricsEvaluator.calculate_faithfulness("Some answer", []) == 0.0


def test_calculate_answer_relevance():
    query = "What is the policy for remote VPN connections?"
    relevant_answer = "Remote employees are required to connect via corporate GlobalProtect VPN with multi-factor authentication."
    score = RAGMetricsEvaluator.calculate_answer_relevance(query, relevant_answer)
    assert score >= 0.70

    refusal_answer = "I do not know the answer because information is not provided."
    refusal_score = RAGMetricsEvaluator.calculate_answer_relevance(query, refusal_answer)
    assert refusal_score <= 0.40

    assert RAGMetricsEvaluator.calculate_answer_relevance("", "Some answer") == 0.0


def test_calculate_context_precision():
    ground_truth = ["Section 4.2: VPN is mandatory with multi-factor authentication."]
    
    # Top ranked match
    retrieved_top = [
        "Section 4.2: VPN is mandatory with multi-factor authentication.",
        "Unrelated cafeteria menu.",
    ]
    top_score = RAGMetricsEvaluator.calculate_context_precision(retrieved_top, ground_truth)
    assert top_score == 1.0

    # Low ranked match
    retrieved_low = [
        "Unrelated cafeteria menu.",
        "Section 4.2: VPN is mandatory with multi-factor authentication.",
    ]
    low_score = RAGMetricsEvaluator.calculate_context_precision(retrieved_low, ground_truth)
    assert low_score == 0.5

    # Zero match
    retrieved_none = ["Unrelated cafeteria menu."]
    none_score = RAGMetricsEvaluator.calculate_context_precision(retrieved_none, ground_truth)
    assert none_score == 0.0


def test_calculate_context_recall():
    ground_truth = [
        "Fact 1: VPN is mandatory with MFA.",
        "Fact 2: Workstations require disk encryption."
    ]
    
    # All captured
    retrieved_all = [
        "Policy requires VPN with MFA on all connections.",
        "Policy specifies workstations require full disk encryption."
    ]
    assert RAGMetricsEvaluator.calculate_context_recall(retrieved_all, ground_truth) == 1.0

    # Half captured
    retrieved_half = [
        "Policy requires VPN with MFA on all connections.",
        "Unrelated text."
    ]
    assert RAGMetricsEvaluator.calculate_context_recall(retrieved_half, ground_truth) == 0.5

    # None captured
    assert RAGMetricsEvaluator.calculate_context_recall(["Unrelated text."], ground_truth) == 0.0


def test_calculate_citation_accuracy():
    contexts = [
        "VPN is mandatory for remote employees.",
        "Workstations require disk encryption."
    ]
    
    valid_cited_answer = "Remote employees must use the VPN [1]. Workstations require encryption [2]."
    score = RAGMetricsEvaluator.calculate_citation_accuracy(valid_cited_answer, contexts)
    assert score >= 0.80

    invalid_citation = "Remote employees must use the VPN [99]."
    invalid_score = RAGMetricsEvaluator.calculate_citation_accuracy(invalid_citation, contexts)
    assert invalid_score == 0.0

    no_citations = "Remote employees must use the VPN."
    assert RAGMetricsEvaluator.calculate_citation_accuracy(no_citations, contexts) == 0.0


def test_evaluation_runner_end_to_end():
    runner = RAGEvaluationRunner()
    report = runner.run_benchmark(GOLDEN_EVALUATION_DATASET)

    assert report.total_samples == len(GOLDEN_EVALUATION_DATASET)
    assert report.mean_faithfulness >= 0.80
    assert report.mean_answer_relevance >= 0.70
    assert report.mean_context_precision >= 0.80
    assert report.mean_context_recall >= 0.80
    assert report.mean_citation_accuracy >= 0.80
    assert report.mean_overall_score >= 0.80

    md_report = runner.generate_markdown_report(report)
    assert "# Enterprise RAG Automated Benchmark Report" in md_report
    assert "eval-001" in md_report
    assert "Overall RAG Benchmark Score" in md_report
