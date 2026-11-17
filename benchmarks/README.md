# Benchmarks

`results/bench-v1.json` is the artifact of an executed run of

```bash
uv run python scripts/run_benchmark.py
```

It is committed so that every number shown on the Evaluation screen (`GET /api/v1/evaluation`)
and in `docs/EVALUATION.md` is traceable to a specific code commit, configuration hash and
set of generated datasets (seed ranges and dataset hashes are recorded per split).

All data is **synthetic** (`nexora.evaluation.generator`, suite `bench-v1`). The results describe
behaviour on scenarios written by the same team that wrote the detectors; they are not a claim
about accuracy on real banking data.
