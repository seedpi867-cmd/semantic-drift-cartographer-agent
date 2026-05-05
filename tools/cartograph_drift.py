#!/usr/bin/env python3
"""Map dated usage drift for one term in a local text corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable


# Split on punctuation inside compounds so phrase queries still find
# variants such as "local-AI", "open_source", and "human-approval".
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
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
    before_neighbors: tuple[str, ...]
    after_neighbors: tuple[str, ...]
    neighbors: tuple[str, ...]


def discover_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
            if any(part.startswith(".") for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_corpus(source_roots: Iterable[Path], output_root: Path) -> dict[str, object]:
    """Copy Markdown/text files from source roots into a stable local corpus."""
    imported: list[dict[str, object]] = []
    seen_destinations: set[Path] = set()
    output_root.mkdir(parents=True, exist_ok=True)

    for source_root in source_roots:
        source_root = source_root.resolve()
        if not source_root.exists():
            raise FileNotFoundError(f"source directory does not exist: {source_root}")
        if not source_root.is_dir():
            raise NotADirectoryError(f"source is not a directory: {source_root}")

        namespace = source_root.name or "source"
        for source_path in discover_files(source_root):
            relative_path = source_path.relative_to(source_root)
            destination_path = output_root / namespace / relative_path
            if destination_path in seen_destinations:
                raise FileExistsError(f"duplicate import destination: {destination_path}")
            seen_destinations.add(destination_path)
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination_path)
            imported.append(
                {
                    "source": str(source_path),
                    "imported_as": str(destination_path.relative_to(output_root)),
                    "bytes": destination_path.stat().st_size,
                    "sha256": file_sha256(destination_path),
                }
            )

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output": str(output_root),
        "documents_imported": len(imported),
        "documents": imported,
    }
    manifest_path = output_root / "import-manifest.json"
    manifest_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


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
            before_neighbors = tuple(
                word
                for word in words[start:idx]
                if word not in STOPWORDS and word not in term_words
            )
            after_neighbors = tuple(
                word
                for word in words[idx + len(term_words) : end]
                if word not in STOPWORDS and word not in term_words
            )
            hits.append(
                Hit(
                    source=str(path.relative_to(root)),
                    date=doc_date,
                    line=line_no,
                    snippet=line.strip()[:260],
                    before_neighbors=before_neighbors,
                    after_neighbors=after_neighbors,
                    neighbors=before_neighbors + after_neighbors,
                )
            )
    return hits


def top_neighbors(hits: Iterable[Hit], limit: int = 12) -> list[dict[str, object]]:
    counter: Counter[str] = Counter()
    for hit in hits:
        counter.update(hit.neighbors)
    return [{"word": word, "count": count} for word, count in counter.most_common(limit)]


def top_directional_neighbors(
    hits: Iterable[Hit],
    direction: str,
    limit: int = 12,
) -> list[dict[str, object]]:
    counter: Counter[str] = Counter()
    for hit in hits:
        if direction == "before":
            counter.update(hit.before_neighbors)
        elif direction == "after":
            counter.update(hit.after_neighbors)
        else:
            raise ValueError(f"unknown neighbor direction: {direction}")
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
                "top_before_neighbors": top_directional_neighbors(hits, "before"),
                "top_after_neighbors": top_directional_neighbors(hits, "after"),
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
    write_meaning_pressure(result, output_root / "meaning-pressure.md")
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
        before_neighbors = ", ".join(
            f"{item['word']}:{item['count']}" for item in bucket["top_before_neighbors"]
        )
        after_neighbors = ", ".join(
            f"{item['word']}:{item['count']}" for item in bucket["top_after_neighbors"]
        )
        lines.append(f"Before: {before_neighbors or 'none'}")
        lines.append(f"After: {after_neighbors or 'none'}")
        lines.append("")
        for example in bucket["examples"]:
            lines.append(f"- `{example['source']}:{example['line']}` {example['snippet']}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def neighbor_words(bucket: dict[str, object]) -> set[str]:
    return {str(item["word"]) for item in bucket["top_neighbors"]}  # type: ignore[index]


def evidence_snippets(bucket: dict[str, object], limit: int = 2) -> list[str]:
    snippets: list[str] = []
    for example in bucket["examples"][:limit]:  # type: ignore[index]
        snippets.append(f"`{example['source']}:{example['line']}` {example['snippet']}")
    return snippets


def classify_meaning_pressure(result: dict[str, object]) -> list[dict[str, object]]:
    """Name likely semantic pressures from neighbor evidence without certainty."""
    buckets = list(result["dates"])  # type: ignore[arg-type]
    if not buckets:
        return [
            {
                "pressure": "insufficient-evidence",
                "confidence": "high",
                "reason": "No dated usage buckets were found.",
                "evidence": [],
            }
        ]

    first_words = neighbor_words(buckets[0])
    last_words = neighbor_words(buckets[-1])
    all_words = [neighbor_words(bucket) for bucket in buckets]
    cumulative_words = set().union(*all_words) if all_words else set()
    max_drift = float(result.get("max_drift_from_previous", 0.0))
    hit_count = int(result.get("hit_count", 0))
    snippets = " ".join(
        str(example["snippet"]).lower()
        for bucket in buckets
        for example in bucket["examples"]  # type: ignore[index]
    )

    pressures: list[dict[str, object]] = []
    first_size = len(first_words)
    last_size = len(last_words)
    overlap = len(first_words & last_words)

    ambiguity_cues = {"between", "or", "stretched", "vague", "overloaded", "ambiguous"}
    capture_cues = {
        "approval", "browser", "controller", "desktop", "hosted", "interface",
        "marketing", "operator", "privacy", "regional", "storage", "tools",
        "workflow",
    }

    if len(buckets) >= 3 and len(cumulative_words) >= max(8, first_size + 4) and max_drift >= 0.45:
        pressures.append(
            {
                "pressure": "broadening",
                "confidence": "medium",
                "reason": (
                    "The term appears in expanding neighbor contexts rather than staying "
                    "near one stable cluster."
                ),
                "evidence": [
                    f"First bucket neighbors: {', '.join(sorted(first_words)) or 'none'}",
                    f"All observed neighbors: {len(cumulative_words)} distinct words across {len(buckets)} buckets",
                    *evidence_snippets(buckets[-1]),
                ],
            }
        )

    if first_size >= 6 and last_size <= max(3, first_size // 2) and overlap > 0:
        pressures.append(
            {
                "pressure": "narrowing",
                "confidence": "low",
                "reason": (
                    "The later evidence uses fewer neighboring concepts while retaining "
                    "part of the earlier cluster."
                ),
                "evidence": [
                    f"First bucket has {first_size} neighbor words; last bucket has {last_size}.",
                    f"Shared words: {', '.join(sorted(first_words & last_words)) or 'none'}",
                    *evidence_snippets(buckets[-1]),
                ],
            }
        )

    capture_words = sorted(cumulative_words & capture_cues)
    if capture_words and max_drift >= 0.45:
        pressures.append(
            {
                "pressure": "capture",
                "confidence": "medium" if len(capture_words) >= 2 else "low",
                "reason": (
                    "A later usage cluster is being pulled toward an operational, product, "
                    "or governance context."
                ),
                "evidence": [
                    f"Capture cue neighbors: {', '.join(capture_words)}",
                    *evidence_snippets(buckets[-1]),
                ],
            }
        )

    if (max_drift >= 0.75 and overlap == 0 and hit_count >= 2) or any(cue in snippets for cue in ambiguity_cues):
        pressures.append(
            {
                "pressure": "ambiguity",
                "confidence": "medium",
                "reason": (
                    "The term is carrying multiple incompatible or weakly overlapping "
                    "neighbor clusters."
                ),
                "evidence": [
                    f"First-to-last neighbor overlap: {overlap}",
                    f"Maximum date-to-date drift: {max_drift:.4f}",
                    *evidence_snippets(buckets[-1]),
                ],
            }
        )

    if not pressures:
        pressures.append(
            {
                "pressure": "stable-or-insufficient",
                "confidence": "medium",
                "reason": (
                    "The available evidence does not strongly indicate broadening, "
                    "narrowing, capture, or ambiguity."
                ),
                "evidence": [
                    f"Maximum date-to-date drift: {max_drift:.4f}",
                    f"Dated buckets: {len(buckets)}",
                ],
            }
        )

    return pressures


def write_meaning_pressure(result: dict[str, object], path: Path) -> None:
    pressures = classify_meaning_pressure(result)
    lines = [
        f"# Meaning Pressure: {result['term']}",
        "",
        "This report names likely semantic pressure from corpus evidence. It is a signal, not a verdict.",
        "",
        f"- Hits: {result['hit_count']}",
        f"- Drift level: {result['drift_level']}",
        f"- Max date-to-date drift: {result['max_drift_from_previous']}",
        "",
        "## Likely Pressures",
        "",
    ]

    for item in pressures:
        lines.append(f"### {item['pressure']} ({item['confidence']} confidence)")
        lines.append(str(item["reason"]))
        lines.append("")
        for evidence in item["evidence"]:  # type: ignore[index]
            lines.append(f"- {evidence}")
        lines.append("")

    lines.extend(
        [
            "## Reading Rule",
            "",
            "Treat these labels as prompts for review. The report preserves evidence first and avoids claiming a final definition.",
            "",
        ]
    )
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


def run_map(args: argparse.Namespace) -> int:
    if not args.term:
        raise SystemExit("--term is required")

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


def run_import_corpus(args: argparse.Namespace) -> int:
    result = import_corpus([Path(path) for path in args.sources], Path(args.output).resolve())
    print(
        f"imported {result['documents_imported']} documents into "
        f"{result['output']}/import-manifest.json"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    import_parser = subparsers.add_parser(
        "import-corpus",
        help="copy local Markdown/text directories into a scan-ready corpus",
    )
    import_parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        required=True,
        help="source directory to import; pass once for blog and once for knowledge",
    )
    import_parser.add_argument(
        "--output",
        default="context/seed-corpus",
        help="destination corpus directory",
    )
    import_parser.set_defaults(func=run_import_corpus)

    parser.add_argument("--term", help="term or short phrase to map")
    parser.add_argument("--input", default="context", help="local corpus directory")
    parser.add_argument("--output", default=None, help="output directory")
    parser.set_defaults(func=run_map)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
