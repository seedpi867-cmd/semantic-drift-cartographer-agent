# semantic-drift-cartographer-agent

An autonomous loop for mapping how important words change meaning across dated local text.

The agent does not decide the true meaning of a term. It records usage evidence: source paths, dates, snippets, neighboring words before and after the term, date-to-date drift scores, and a hash-linked run ledger.

## Quick Start

```bash
git clone https://github.com/seedpi867-cmd/semantic-drift-cartographer-agent.git
cd semantic-drift-cartographer-agent
python3 tools/cartograph_drift.py --term agent --input samples/corpus --output output/agent
```

To import Seed's own writing into a scan-ready corpus:

```bash
python3 tools/cartograph_drift.py import-corpus --source ../blog --source ../knowledge --output context/seed-corpus
python3 tools/cartograph_drift.py --term agent --input context/seed-corpus --output output/seed-agent
```

Outputs:

- `drift-map.json` structured dated usage evidence, including combined and directional neighbor windows
- `drift-docket.md` human-readable shift docket with before/after neighbor lines
- `meaning-pressure.md` likely broadening, narrowing, capture, and ambiguity signals
- `asymmetry-report.md` directional evidence comparing before-neighbor domain cues with after-neighbor obligation cues
- `drift-ledger.jsonl` hash-linked run receipts
- `import-manifest.json` source, destination, byte count, and hash for imported corpus files

## Why This Exists

Powerful words become infrastructure. `agent`, `local AI`, `approval`, `safety`, and `open source` can start as precise terms and become marketing labels, policy triggers, or vague permission slips.

This agent makes that drift visible from local evidence.

## Agent Loop

The repo is built on [brain-loop](https://github.com/seedpi867-cmd/brain-loop). To run it as a waking agent, edit `config.sh`, drop dated `.md` or `.txt` files into `context/`, and run:

```bash
./brain-loop.sh
```

Each cycle should choose one term, run the local cartographer, write an interpretation note, and update memory.

## First Slice

- Local-only corpus scanning.
- Corpus import from local `blog/` and `knowledge/` directories.
- Single term or short phrase matching.
- Date inference from path or first lines.
- Neighbor-word comparison by date bucket, with combined, before, and after windows.
- Markdown and JSON outputs.
- Meaning-pressure report that names likely semantic pressure from evidence.
- Asymmetry report that asks whether the left side identifies domains while the right side attaches obligations.
- Hash-linked run ledger.

## Verify

```bash
python3 -m unittest tests/test_cartograph_drift.py
python3 -m py_compile tools/cartograph_drift.py tests/test_cartograph_drift.py
```

## License

MIT.
