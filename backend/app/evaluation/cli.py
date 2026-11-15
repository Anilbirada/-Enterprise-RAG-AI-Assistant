import argparse
import sys
import json
from pathlib import Path

from app.evaluation.runner import RAGEvaluationRunner


def main():
    parser = argparse.ArgumentParser(description="Enterprise RAG Evaluation Suite")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="docs/rag-evaluation-report.md",
        help="Output path for Markdown benchmark report",
    )
    parser.add_argument(
        "--json-output",
        "-j",
        type=str,
        default=None,
        help="Optional path to output raw JSON report",
    )
    args = parser.parse_args()

    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("[INFO] Initializing Enterprise RAG Automated Benchmark...")
    runner = RAGEvaluationRunner()
    report = runner.run_benchmark()

    md_report = runner.generate_markdown_report(report)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md_report, encoding="utf-8")
    print(f"[SUCCESS] Benchmark report successfully written to: {output_path}")

    if args.json_output:
        json_path = Path(args.json_output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")
        print(f"[SUCCESS] JSON report written to: {json_path}")

    print("\n" + "=" * 50)
    print(f"Overall RAG Benchmark Score: {report.mean_overall_score:.4f} / 1.0000")
    print(f"Faithfulness:                {report.mean_faithfulness:.4f}")
    print(f"Answer Relevance:            {report.mean_answer_relevance:.4f}")
    print(f"Context Precision:           {report.mean_context_precision:.4f}")
    print(f"Context Recall:              {report.mean_context_recall:.4f}")
    print(f"Citation Accuracy:           {report.mean_citation_accuracy:.4f}")
    print("=" * 50)


if __name__ == "__main__":
    main()
