#!/usr/bin/env python3
"""Map dated usage drift for one term in a local text corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable


WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
DATE_RE = re.compile(r"(20\d{2})[-_/](\d{2})[-_/](\d{2})")
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "for", "from",
    "has", "have", "if", "in", "is", "it", "its", "not", "of", "on", "or",
    "that", "the", "their", "then", "there", "this", "to", "was", "with",
    "you", "your",
}


@dataclass(frozen=True)
class Hit:
    source: str
    date: str
    line: int
    snippet: str
    neighbors: tuple[str, ...]


def discover_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
            if any(part.startswith(".") for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def infer_date(path: Path, text: str) -> str:
    candidates = [str(path)] + text.splitlines()[:8]
    for candidate in candidates:
        match = DATE_RE.search(candidate)
        if match:
            year, month, day = match.groups()
            try:
                return date(int(year), int(month), int(day)).isoformat()
            except ValueError:
                continue
    return "undated"


def normalize_words(text: str) -> list[str]:
    return [word.lower() for word in WORD_RE.findall(text)]


def find_hits(path: Path, root: Path, term: str) -> list[Hit]:
    text = path.read_text(encoding="utf-8", errors="replace")
    doc_date = infer_date(path, text)
    term_words = normalize_words(term)
    if not term_words:
        raise ValueError("term must contain at least one word")

    hits: list[Hit] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        words = normalize_words(line)
        if not words:
            continue
        for idx in range(0, len(words) - len(term_words) + 1):
            if words[idx : idx + len(term_words)] != term_words:
                continue
            start = max(0, idx - 8)
            end = min(len(words), idx + len(term_words) + 8)
            neighbors = tuple(
                word
                for word in words[start:idx] + words[idx + len(term_words) : end]
                if word not in STOPWORDS and word not in term_words
            )
            hits.append(
                Hit(
                    source=str(path.relative_to(root)),
                    date=doc_date,
                    line=line_no,
                    snippet=line.strip()[:260],
                    neighbors=neighbors,
                )
            )
    return hits


def top_neighbors(hits: Iterable[Hit], limit: int = 12) -> list[dict[str, object]]:
    counter: Counter[str] = Counter()
    for hit in hits:
        counter.update(hit.neighbors)
    return [{"word": word, "count": count} for word, count in counter.most_common(limit)]


def jaccard_distance(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    return 1.0 - (len(left & right) / len(left | right))


def build_map(term: str, input_root: Path, output_root: Path) -> dict[str, object]:
    all_hits: list[Hit] = []
    files = discover_files(input_root)
    for path in files:
        all_hits.extend(find_hits(path, input_root, term))

    by_date: dict[str, list[Hit]] = defaultdict(list)
    for hit in all_hits:
        by_date[hit.date].append(hit)

    dated = []
    previous_words: set[str] | None = None
    for doc_date in sorted(by_date):
        hits = by_date[doc_date]
        words = {item["word"] for item in top_neighbors(hits)}
        drift_from_previous = None if previous_words is None else jaccard_distance(previous_words, words)
        dated.append(
            {
                "date": doc_date,
                "hit_count": len(hits),
                "top_neighbors": top_neighbors(hits),
                "drift_from_previous": drift_from_previous,
                "examples": [
                    {
                        "source": hit.source,
                        "line": hit.line,
                        "snippet": hit.snippet,
                    }
                    for hit in hits[:5]
                ],
            }
        )
        previous_words = words

    drift_scores = [
        bucket["drift_from_previous"]
        for bucket in dated
        if isinstance(bucket["drift_from_previous"], float)
    ]
    max_drift = max(drift_scores) if drift_scores else 0.0
    drift_level = "none"
    if max_drift >= 0.75:
        drift_level = "high"
    elif max_drift >= 0.45:
        drift_level = "medium"
    elif max_drift > 0:
        drift_level = "low"

    result = {
        "term": term,
        "input": str(input_root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents_scanned": len(files),
        "hit_count": len(all_hits),
        "drift_level": drift_level,
        "max_drift_from_previous": round(max_drift, 4),
        "dates": dated,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "drift-map.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    write_docket(result, output_root / "drift-docket.md")
    append_receipt(result, output_root / "drift-ledger.jsonl")
    return result


def write_docket(result: dict[str, object], path: Path) -> None:
    lines = [
        f"# Drift Docket: {result['term']}",
        "",
        f"- Documents scanned: {result['documents_scanned']}",
        f"- Hits: {result['hit_count']}",
        f"- Drift level: {result['drift_level']}",
        f"- Max date-to-date drift: {result['max_drift_from_previous']}",
        "",
    ]
    for bucket in result["dates"]:  # type: ignore[index]
        lines.append(f"## {bucket['date']} ({bucket['hit_count']} hits)")
        if bucket["drift_from_previous"] is not None:
            lines.append(f"Drift from previous bucket: {bucket['drift_from_previous']:.3f}")
        neighbors = ", ".join(
            f"{item['word']}:{item['count']}" for item in bucket["top_neighbors"]
        )
        lines.append(f"Neighbors: {neighbors or 'none'}")
        lines.append("")
        for example in bucket["examples"]:
            lines.append(f"- `{example['source']}:{example['line']}` {example['snippet']}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def append_receipt(result: dict[str, object], path: Path) -> None:
    previous_hash = ""
    if path.exists():
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            try:
                previous_hash = json.loads(lines[-1]).get("entry_hash", "")
            except json.JSONDecodeError:
                previous_hash = ""
    receipt = {
        "term": result["term"],
        "generated_at": result["generated_at"],
        "documents_scanned": result["documents_scanned"],
        "hit_count": result["hit_count"],
        "drift_level": result["drift_level"],
        "previous_hash": previous_hash,
    }
    encoded = json.dumps(receipt, sort_keys=True)
    receipt["entry_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--term", required=True, help="term or short phrase to map")
    parser.add_argument("--input", default="context", help="local corpus directory")
    parser.add_argument("--output", default=None, help="output directory")
    args = parser.parse_args()

    input_root = Path(args.input).resolve()
    if not input_root.exists():
        raise SystemExit(f"input directory does not exist: {input_root}")
    slug = re.sub(r"[^a-z0-9]+", "-", args.term.lower()).strip("-") or "term"
    output_root = Path(args.output or f"output/{slug}").resolve()
    result = build_map(args.term, input_root, output_root)
    print(
        f"mapped '{result['term']}': {result['hit_count']} hits, "
        f"{result['drift_level']} drift, output={output_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
