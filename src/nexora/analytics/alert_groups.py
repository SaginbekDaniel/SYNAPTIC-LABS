"""Group related review items (backlog B-042, finding H-11).

Formations are fingerprinted per pattern kind, so one hub can open several alerts - a collection funnel *and* a
fan-out on the same account, for example. Grouping lets the analyst see them as one piece of work. It is a pure,
read-side view: it never merges, alters or drops an alert or an assessment.

Two items are related when they share an **anchor** account. The anchor rule is a parameter because it decides
how far grouping reaches:

* ``"subject"`` - the formation's subject (hub) account only. Conservative: two formations on the same hub.
* ``"members"`` - any account of the formation. Reaches further, but a busy legitimate account (a payroll agent,
  a merchant) can chain unrelated networks into one group.

The choice between them is measured, not assumed (``docs/handoff/probes/alert_grouping.py``, synthetic bench-v1):
on the dev split ``subject`` leaves 1.39 review units per flagged network unchanged (the repeated alerts sit on
different hubs of one network), ``members`` brings it to 1.02 with no group joining two planted networks; the
validation split gives 1.19 -> 1.00, also without a wrong merge. ``members`` is therefore the default and the
rule the API uses.

Grouping is a connected-components problem (union-find), so it is deterministic and independent of input order:
the group id is content-derived from the sorted ids of its items.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from nexora.domain.ids import stable_uuid

AnchorRule = Literal["subject", "members"]


@dataclass(frozen=True)
class Groupable:
    item_id: str
    subject: str
    accounts: frozenset[str]

    def anchors(self, rule: AnchorRule) -> frozenset[str]:
        return frozenset((self.subject,)) if rule == "subject" else self.accounts | {self.subject}


@dataclass(frozen=True)
class Group:
    group_id: str
    item_ids: tuple[str, ...]  # sorted

    @property
    def size(self) -> int:
        return len(self.item_ids)


class _UnionFind:
    def __init__(self, ids: Iterable[str]) -> None:
        self.parent = {i: i for i in ids}

    def find(self, x: str) -> str:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # The smaller id becomes the root, so the forest's shape does not depend on input order.
            lo, hi = sorted((ra, rb))
            self.parent[hi] = lo


def group_items(items: Iterable[Groupable], rule: AnchorRule = "members") -> dict[str, Group]:
    """Map every item id to its group. Items without a related item form a group of one.

    The result depends only on the set of items and the rule, never on their order.
    """
    items = list(items)
    ids = [i.item_id for i in items]
    if len(set(ids)) != len(ids):
        raise ValueError("item ids must be unique")
    uf = _UnionFind(ids)
    first_owner: dict[str, str] = {}
    for item in sorted(items, key=lambda i: i.item_id):
        for account in sorted(item.anchors(rule)):
            owner = first_owner.setdefault(account, item.item_id)
            if owner != item.item_id:
                uf.union(owner, item.item_id)
    members: dict[str, list[str]] = {}
    for i in ids:
        members.setdefault(uf.find(i), []).append(i)
    by_item: dict[str, Group] = {}
    for group_members in members.values():
        sorted_ids = tuple(sorted(group_members))
        group = Group(group_id=stable_uuid("alert-group", rule, *sorted_ids), item_ids=sorted_ids)
        for i in sorted_ids:
            by_item[i] = group
    return by_item


def groups_of(by_item: Mapping[str, Group]) -> list[Group]:
    """Distinct groups, in a stable order (by group id)."""
    return sorted({g.group_id: g for g in by_item.values()}.values(), key=lambda g: g.group_id)
