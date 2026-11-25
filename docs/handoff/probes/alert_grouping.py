"""Measure alert grouping rules on the exposed bench-v1 DEV split (backlog B-042).

Run from the repository root:  uv run python docs/handoff/probes/alert_grouping.py [split]

For the shipped configuration, takes every flagged review item and compares the anchor rules of
``nexora.analytics.alert_groups``:

* review units per flagged planted network - how many separate things an analyst opens for one network
  (without grouping this is the harness's ``alerts.per_flagged_network``);
* wrong merges - groups that join items matched to *different* planted networks, and how many of those mix a
  suspicious network with a legitimate one (the harmful case: fraud hidden in a legitimate hub's group);
* the largest group.

Development data only. Never run it on ``sealed`` (consumed) or ``sealed_v2`` (uses are reserved for frozen
detector candidates). Synthetic data: shows behaviour on our scenarios, not on bank data.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict

from nexora.analytics.alert_groups import Groupable, group_items, groups_of
from nexora.analytics.config import default_config
from nexora.evaluation import benchmark as b

ALLOWED = {"dev", "validation"}


def main(split: str) -> None:
    if split not in ALLOWED:
        raise SystemExit(f"refusing split {split!r}: only {sorted(ALLOWED)} (development data)")
    datasets = b.load_split(split)
    evals = b.run_experiments(datasets, [b.Experiment("shipped", b.nexora_method(default_config()))])["shipped"]
    print(f"split={split} datasets={len(evals)} config=shipped")
    for rule in ("none", "subject", "members"):
        units_per_network: list[int] = []
        wrong_merges = mixed_labels = largest = flagged_items = groups_total = 0
        for ev in evals:
            pairs = [(i, m) for i, m in zip(ev.items, ev.matches, strict=True) if i.flagged and i.queued]
            flagged_items += len(pairs)
            if rule == "none":
                unit_of = {i.item_id: i.item_id for i, _ in pairs}
            else:
                by_item = group_items((Groupable(i.item_id, i.subject, i.accounts) for i, _ in pairs), rule)
                unit_of = {k: g.group_id for k, g in by_item.items()}
                groups = groups_of(by_item)
                groups_total += len(groups)
                largest = max([largest, *(g.size for g in groups)])
                scen: dict[str, set[tuple[str, str]]] = defaultdict(set)
                for i, m in pairs:
                    if m is not None:
                        scen[unit_of[i.item_id]].add((m.scenario_id, m.label))
                for found in scen.values():
                    if len({s for s, _ in found}) > 1:
                        wrong_merges += 1
                        mixed_labels += len({label for _, label in found}) > 1
            units: dict[str, set[str]] = defaultdict(set)
            for i, m in pairs:
                if m is not None:
                    units[m.scenario_id].add(unit_of[i.item_id])
            units_per_network.extend(len(u) for u in units.values())
        mean = sum(units_per_network) / len(units_per_network)
        dist = Counter(units_per_network)
        line = (
            f"rule={rule:8} flagged_items={flagged_items} networks={len(units_per_network)} "
            f"units_per_network={mean:.4f} dist={dict(sorted(dist.items()))}"
        )
        if rule != "none":
            line += f" groups={groups_total} wrong_merges={wrong_merges}"
            line += f" mixed_label_merges={mixed_labels} largest={largest}"
        print(line)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dev")
