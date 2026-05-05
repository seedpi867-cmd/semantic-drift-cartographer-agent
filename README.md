# semantic-drift-cartographer-agent

An autonomous loop for mapping how important words change meaning across dated local text.

The agent does not decide the true meaning of a term. It records usage evidence: source paths, dates, snippets, neighboring words, date-to-date drift scores, and a hash-linked run ledger.

## Quick Start

```bash
git clone https://github.com/seedpi867-cmd/semantic-drift-cartographer-agent.git
cd semantic-drift-cartographer-agent
python3 tools/cartograph_drift.py --term agent --input samples/corpus --output output/agent
```

Outputs:

- `drift-map.json` structured dated usage evidence
- `drift-docket.md` human-readable shift docket
- `drift-ledger.jsonl` hash-linked run receipts

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
- Single term or short phrase matching.
- Date inference from path or first lines.
- Neighbor-word comparison by date bucket.
- Markdown and JSON outputs.
- Hash-linked run ledger.

## Verify

```bash
python3 -m unittest tests/test_cartograph_drift.py
python3 -m py_compile tools/cartograph_drift.py tests/test_cartograph_drift.py
```

## License

MIT.
