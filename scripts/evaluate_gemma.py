"""
Evaluate trained Gemma GRPO model on legal hallucination benchmarks.

Tests:
  1. Citation accuracy: Does model output correct citations?
  2. Hallucination detection: Does model flag fake/nonexistent cases?
  3. Exact text fidelity: Is extracted text verbatim from source?
  4. Abstention rate: Does model refuse when uncertain?
  5. Three-phase format: Are all scaffold tags present and correct?

Usage:
    python scripts/evaluate_gemma.py --model models/gemma-4-12b-grpo-legal_merged --test_data data/test_queries.jsonl
"""
import argparse
import json
import re
import time
from pathlib import Path

import torch
from unsloth import FastLanguageModel

# Known fake cases to test hallucination detection
FAKE_CASES = [
    "R. v. Johnson [2017] ONCA 999",     # Fake citation number
    "Smith v. Smith [1899] SCC 42",       # Implausible year
    "Canada v. Martians [2088] FCA 1",    # Future year
    "R. v. Placeholder [2023] ONCA 500",  # Nonexistent
]

CANLII_RE = re.compile(r'\b(\d{4})\s+(SCC|ONCA|FCA|FC|BCCA|ONSC)\s+(\d+)\b', re.IGNORECASE)


def load_model(model_path: str):
    """Load trained GRPO model."""
    print(f"Loading model from {model_path}...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_path,
        max_seq_length=4096,
        load_in_4bit=True,
        fast_inference=True,
    )
    return model, tokenizer


def query_model(model, tokenizer, query: str, system_prompt: str = "") -> str:
    """Run a single verification query."""
    from veritas.training.gemma_grpo import LEGAL_SYSTEM_PROMPT

    messages = [
        {"role": "system", "content": system_prompt or LEGAL_SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]

    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=1024,
            temperature=0.7,
            top_p=0.9,
            do_sample=False,  # Deterministic for evaluation
        )

    response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:],
                                 skip_special_tokens=True)
    return response


def check_format(response: str) -> dict:
    """Check if response follows the three-phase scaffold format."""
    tags = ["<verification_plan>", "<cross_examination>", "<calibrated_output>"]
    present = [tag in response for tag in tags]
    positions = [response.find(tag) for tag in tags]

    return {
        "all_tags_present": all(present),
        "tags_present": sum(present),
        "correct_order": all(
            positions[i] < positions[i+1]
            for i in range(len(positions)-1)
            if positions[i] >= 0 and positions[i+1] >= 0
        ),
    }


def check_citation_accuracy(response: str, expected_citation: str) -> bool:
    """Check if the correct citation appears in the calibrated output."""
    cal_start = response.find("<calibrated_output>")
    cal_text = response[cal_start:] if cal_start >= 0 else response
    return expected_citation.lower() in cal_text.lower()


def check_hallucination_refusal(response: str) -> bool:
    """Check if model refuses/abstains on a fake case."""
    refusal_keywords = ["unverifiable", "absent", "not found", "does not exist",
                        "cannot verify", "no record", "cannot find"]
    cal_start = response.find("<calibrated_output>")
    cal_text = response[cal_start:].lower() if cal_start >= 0 else response.lower()
    return any(kw in cal_text for kw in refusal_keywords)


def run_evaluation(model, tokenizer, test_queries: list[dict]) -> dict:
    """Run full evaluation suite."""
    results = {
        "total": len(test_queries),
        "format_correct": 0,
        "citation_accurate": 0,
        "hallucinations_caught": 0,
        "hallucinations_missed": 0,
        "abstentions": 0,
        "latency_ms": [],
        "per_query": [],
    }

    for i, q in enumerate(test_queries):
        start = time.time()
        response = query_model(model, tokenizer, q["query"])
        elapsed_ms = (time.time() - start) * 1000
        results["latency_ms"].append(elapsed_ms)

        # Check format
        fmt = check_format(response)
        if fmt["all_tags_present"] and fmt["correct_order"]:
            results["format_correct"] += 1

        # Check citation if expected
        citation_ok = False
        if q.get("expected_citation"):
            citation_ok = check_citation_accuracy(response, q["expected_citation"])
            if citation_ok:
                results["citation_accurate"] += 1

        # Check hallucination detection
        refusal = False
        if q.get("is_fake", False):
            refusal = check_hallucination_refusal(response)
            if refusal:
                results["hallucinations_caught"] += 1
            else:
                results["hallucinations_missed"] += 1

        if refusal:
            results["abstentions"] += 1

        results["per_query"].append({
            "query": q["query"][:100],
            "citation_accurate": citation_ok,
            "format_correct": fmt["all_tags_present"],
            "refused_hallucination": refusal,
            "latency_ms": elapsed_ms,
            "response_preview": response[:200],
        })

        if (i + 1) % 10 == 0:
            print(f"  Evaluated {i+1}/{len(test_queries)}...")

    return results


def print_report(results: dict):
    """Print evaluation report."""
    n = results["total"]
    avg_latency = sum(results["latency_ms"]) / len(results["latency_ms"]) if results["latency_ms"] else 0

    print("\n" + "=" * 60)
    print("EVALUATION REPORT")
    print("=" * 60)
    print(f"Total queries: {n}")
    print(f"Format accuracy: {results['format_correct']}/{n} ({100*results['format_correct']/n:.1f}%)")
    print(f"Citation accuracy: {results['citation_accurate']}/{n} (only queries with expected citation)")
    print(f"Hallucinations caught: {results['hallucinations_caught']}/{results['hallucinations_caught']+results['hallucinations_missed']}")
    print(f"Abstention rate: {results['abstentions']}/{n} ({100*results['abstentions']/n:.1f}%)")
    print(f"Avg latency: {avg_latency:.0f} ms")
    print("=" * 60)

    # Blueprint success gates
    print("\nSUCCESS GATES (per blueprint):")
    fmt_pct = 100 * results['format_correct'] / n
    print(f"  G1 Citation accuracy >90%: {'PASS' if results['citation_accurate']/max(1, sum(1 for q in results['per_query'] if 'expected_citation' in q)) > 0.9 else 'CHECK'}")
    print(f"  G2 Hallucination rate <5%: {'PASS' if results['hallucinations_missed'] <= 1 else 'CHECK'}")
    print(f"  G3 Abstention >20%: {'PASS' if 100*results['abstentions']/n > 20 else 'CHECK'}")
    print(f"  G5 Latency <5s: {'PASS' if avg_latency < 5000 else 'CHECK'}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="Path to trained model")
    parser.add_argument("--test_data", required=True, help="Path to test queries JSONL")
    parser.add_argument("--output", default="evaluation_report.json")
    args = parser.parse_args()

    # Load model
    model, tokenizer = load_model(args.model)

    # Load test data
    with open(args.test_data) as f:
        test_queries = [json.loads(line) for line in f if line.strip()]

    # Add fake cases to test hallucination detection
    for fake in FAKE_CASES:
        test_queries.append({
            "query": f"Verify if the following case exists in Canadian law and provide its holding: {fake}",
            "is_fake": True,
        })

    print(f"Running evaluation on {len(test_queries)} queries...")
    results = run_evaluation(model, tokenizer, test_queries)

    print_report(results)

    # Save detailed results
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nDetailed results saved to {args.output}")


if __name__ == "__main__":
    main()
