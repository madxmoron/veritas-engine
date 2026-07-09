"""
Generate GRPO self-scaffolding training pairs from A2AJ Canadian case law dataset.

Output format (one JSON object per line):
{
    "text": "The full case text...",
    "citation": "2020 ONCA 123",
    "name": "R. v. Smith",
    "type": "citation" | "holding" | "statute",
    "court": "ONCA",
    "year": 2020
}

Usage:
    python scripts/generate_grpo_pairs.py --dataset a2aj/canadian-case-law --courts ONCA,SCC,FCA --output data/grpo_pairs.jsonl
"""
import argparse
import json
import random
from pathlib import Path

random.seed(3407)


def load_a2aj_dataset(courts: list[str] = None, min_chars: int = 1000,
                      max_examples: int = 50000, lang: str = "en"):
    """
    Load and filter A2AJ dataset from HuggingFace.
    
    Args:
        courts: Court abbreviations to include (e.g., ["ONCA", "SCC", "FCA"])
        min_chars: Minimum decision text length
        max_examples: Maximum examples to process
        lang: Language ("en" or "fr")
    
    Returns:
        Filtered dataset
    """
    from datasets import load_dataset

    print(f"Loading a2aj/canadian-case-law...")
    dataset = load_dataset("a2aj/canadian-case-law", split="train")
    print(f"Total rows: {len(dataset):,}")

    # Filter by court
    if courts:
        dataset = dataset.filter(lambda x: x.get("dataset") in courts)
        print(f"After court filter ({courts}): {len(dataset):,}")

    # Filter by language (text field)
    text_field = f"unofficial_text_{lang}"
    dataset = dataset.filter(lambda x: x.get(text_field) and len(str(x[text_field])) >= min_chars)
    print(f"After text length filter (>={min_chars} chars): {len(dataset):,}")

    # Cap
    if len(dataset) > max_examples:
        dataset = dataset.select(range(max_examples))

    print(f"Final dataset size: {len(dataset):,}")
    return dataset, text_field


def generate_training_pairs(dataset, text_field: str) -> list[dict]:
    """
    Convert filtered A2AJ cases into GRPO training pairs.
    
    Each pair contains the case text as the "claim" to verify,
    with metadata for reward function scoring.
    """
    pairs = []

    for i, row in enumerate(dataset):
        text = str(row.get(text_field, ""))
        citation = str(row.get(f"citation_en", ""))
        name = str(row.get(f"name_en", ""))
        court = str(row.get("dataset", ""))
        date = str(row.get(f"document_date_{text_field[-2:]}", ""))

        # Extract year from citation or date
        year = None
        try:
            year = int(citation.split()[0])
        except (ValueError, IndexError):
            try:
                year = int(date[:4])
            except (ValueError, IndexError):
                year = 2020  # fallback

        # Type 1: Citation extraction (always)
        pairs.append({
            "text": text,
            "citation": citation,
            "name": name,
            "type": "citation",
            "court": court,
            "year": year,
        })

        # Type 2: Holding extraction (if text mentions legal principles)
        if any(kw in text.lower() for kw in ["held", "holding", "applied", "followed",
                                               "overturned", "distinguished",
                                               "the court", "the judge", "we find",
                                               "we conclude"]):
            pairs.append({
                "text": text,
                "citation": citation,
                "name": name,
                "type": "holding",
                "court": court,
                "year": year,
            })

        # Type 3: Statute reference (if text mentions statutes)
        if any(kw in text.lower() for kw in ["statute", "act", "code", "regulation",
                                               "criminal code", "charter",
                                               "r.s.o", "r.s.c", "s.o."]):
            pairs.append({
                "text": text,
                "citation": citation,
                "name": name,
                "type": "statute",
                "court": court,
                "year": year,
            })

        if (i + 1) % 5000 == 0:
            print(f"  Processed {i+1:,} cases, generated {len(pairs):,} pairs")

    print(f"Generated {len(pairs):,} total training pairs")
    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="a2aj/canadian-case-law")
    parser.add_argument("--courts", default="ONCA,SCC,FCA",
                        help="Comma-separated court abbreviations")
    parser.add_argument("--output", default="data/grpo_pairs.jsonl")
    parser.add_argument("--min_chars", type=int, default=1000,
                        help="Minimum decision text length")
    parser.add_argument("--max_examples", type=int, default=50000,
                        help="Max dataset rows to process")
    parser.add_argument("--lang", default="en", choices=["en", "fr"])
    parser.add_argument("--sample", type=int, default=0,
                        help="If >0, randomly sample this many pairs from output")
    args = parser.parse_args()

    courts = [c.strip() for c in args.courts.split(",")]

    # Load
    dataset, text_field = load_a2aj_dataset(
        courts=courts,
        min_chars=args.min_chars,
        max_examples=args.max_examples,
        lang=args.lang,
    )

    # Generate pairs
    pairs = generate_training_pairs(dataset, text_field)

    # Sample if requested
    if args.sample > 0 and args.sample < len(pairs):
        pairs = random.sample(pairs, args.sample)
        print(f"Sampled {args.sample} pairs")

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    print(f"Saved {len(pairs):,} pairs to {output_path}")


if __name__ == "__main__":
    main()
