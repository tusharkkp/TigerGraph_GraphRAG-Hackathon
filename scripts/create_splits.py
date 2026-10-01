"""Generate stratified train/val/test splits for the 100 public questions.

Produces data/splits.json with deterministic, stratified splits (seed 42).
"""

import json
import random
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_FILE = PROJECT_ROOT / "Dataset" / "questions" / "eval_public.jsonl"
OUTPUT_FILE = PROJECT_ROOT / "data" / "splits.json"


def create_splits(seed: int = 42, dev_n: int = 60, val_n: int = 20, test_n: int = 20) -> dict:
    """Create stratified splits preserving qtype distribution."""
    # Load questions
    questions = []
    with open(QUESTIONS_FILE) as f:
        for line in f:
            questions.append(json.loads(line.strip()))

    assert len(questions) == 100, f"Expected 100 questions, got {len(questions)}"
    assert dev_n + val_n + test_n == 100, "Splits must sum to 100"

    # Group by qtype for stratification
    by_type: dict[str, list[str]] = defaultdict(list)
    for q in questions:
        by_type[q["qtype"]].append(q["qid"])

    rng = random.Random(seed)

    # Shuffle within each type
    for qtype in by_type:
        rng.shuffle(by_type[qtype])

    # Allocate proportionally: dev=60%, val=20%, test=20%
    dev_ids, val_ids, test_ids = [], [], []

    for _qtype, qids in sorted(by_type.items()):
        n = len(qids)
        n_dev = round(n * dev_n / 100)
        n_val = round(n * val_n / 100)
        # remainder goes to test

        dev_ids.extend(qids[:n_dev])
        val_ids.extend(qids[n_dev : n_dev + n_val])
        test_ids.extend(qids[n_dev + n_val :])

    # Final shuffle of each split
    rng.shuffle(dev_ids)
    rng.shuffle(val_ids)
    rng.shuffle(test_ids)

    # Verify no overlap
    all_ids = set(dev_ids) | set(val_ids) | set(test_ids)
    assert len(all_ids) == 100, f"Expected 100 unique IDs, got {len(all_ids)}"
    assert not (set(dev_ids) & set(val_ids)), "dev/val overlap!"
    assert not (set(dev_ids) & set(test_ids)), "dev/test overlap!"
    assert not (set(val_ids) & set(test_ids)), "val/test overlap!"

    # Load hidden question IDs to verify they never appear in splits
    hidden_file = PROJECT_ROOT / "Dataset" / "questions" / "eval_hidden.jsonl"
    hidden_ids = set()
    with open(hidden_file) as f:
        for line in f:
            hidden_ids.add(json.loads(line.strip())["qid"])

    assert not (all_ids & hidden_ids), "Public question IDs overlap with hidden IDs!"

    # Build type distribution per split for documentation
    def type_dist(ids: list[str]) -> dict[str, int]:
        dist: dict[str, int] = defaultdict(int)
        qid_to_type = {q["qid"]: q["qtype"] for q in questions}
        for qid in ids:
            dist[qid_to_type[qid]] += 1
        return dict(sorted(dist.items()))

    result = {
        "seed": seed,
        "splits": {
            "dev": sorted(dev_ids),
            "val": sorted(val_ids),
            "test": sorted(test_ids),
        },
        "counts": {
            "dev": len(dev_ids),
            "val": len(val_ids),
            "test": len(test_ids),
        },
        "type_distribution": {
            "dev": type_dist(dev_ids),
            "val": type_dist(val_ids),
            "test": type_dist(test_ids),
        },
    }

    return result


if __name__ == "__main__":
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    splits = create_splits()
    with open(OUTPUT_FILE, "w") as f:
        json.dump(splits, f, indent=2)
    print(f"Splits written to {OUTPUT_FILE}")
    print(f"  dev:  {splits['counts']['dev']} questions — {splits['type_distribution']['dev']}")
    print(f"  val:  {splits['counts']['val']} questions — {splits['type_distribution']['val']}")
    print(f"  test: {splits['counts']['test']} questions — {splits['type_distribution']['test']}")
