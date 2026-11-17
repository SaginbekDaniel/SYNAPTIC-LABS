"""Canonical directed graph snapshot (spec §8).

* One aggregate edge per ordered account pair and currency, built only from eligible
  (``posted``) transfers.
* Self-transfers are kept as records and counted per node, but never become graph
  edges, so they cannot inflate distinct-counterparty counts.
* Original transfers stay addressable by id for time-aware evidence.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import networkx as nx

from nexora.domain.ids import canonical_json, sha256_hex
from nexora.domain.money import amount_to_str
from nexora.domain.transfers import ObservedTransfer

GRAPH_VERSION = "graph-v1"


@dataclass(frozen=True, slots=True)
class AggregatedEdge:
    sender: str
    receiver: str
    currency: str
    amount_minor: int
    n_transactions: int
    transaction_ids: tuple[str, ...]
    first_date: date
    last_date: date


@dataclass
class NodeMetrics:
    account_id: str
    in_degree: int = 0
    out_degree: int = 0
    incoming_minor: int = 0
    outgoing_minor: int = 0
    incoming_count: int = 0
    outgoing_count: int = 0
    self_transfer_count: int = 0
    first_seen: date | None = None
    last_seen: date | None = None
    active_days: int = 0


@dataclass
class CurrencyGraph:
    currency: str
    graph: nx.DiGraph
    edges: dict[tuple[str, str], AggregatedEdge]
    metrics: dict[str, NodeMetrics]


@dataclass
class GraphSnapshotData:
    transfers: dict[str, ObservedTransfer]
    by_currency: dict[str, CurrencyGraph]
    input_manifest_sha256: str
    eligible_count: int
    excluded_count: int
    window_start: date | None
    window_end: date | None
    accounts: frozenset[str] = field(default_factory=frozenset)

    @property
    def currencies(self) -> list[str]:
        return sorted(self.by_currency)

    @property
    def nodes_count(self) -> int:
        return len(self.accounts)

    @property
    def edges_count(self) -> int:
        return sum(len(g.edges) for g in self.by_currency.values())


def input_manifest_sha256(transfers: list[ObservedTransfer]) -> str:
    """Order-independent hash of the canonical analysed input."""
    rows = sorted(
        (
            t.transaction_id,
            t.sender,
            t.receiver,
            amount_to_str(t.amount_minor),
            t.currency,
            t.observed_date.isoformat(),
            t.occurred_at.isoformat() if t.occurred_at else "",
            t.precision,
            t.status,
        )
        for t in transfers
    )
    return sha256_hex(canonical_json(rows))


def build_snapshot(transfers: list[ObservedTransfer]) -> GraphSnapshotData:
    by_id: dict[str, ObservedTransfer] = {}
    for t in transfers:
        if t.transaction_id in by_id:
            raise ValueError(f"duplicate transaction id in snapshot input: {t.transaction_id}")
        by_id[t.transaction_id] = t

    eligible = sorted((t for t in transfers if t.eligible), key=lambda t: t.transaction_id)
    pair_tx: dict[tuple[str, str, str], list[ObservedTransfer]] = defaultdict(list)
    accounts: set[str] = set()
    node_days: dict[tuple[str, str], set[date]] = defaultdict(set)
    metrics_by_cur: dict[str, dict[str, NodeMetrics]] = defaultdict(dict)

    def metric(cur: str, account: str) -> NodeMetrics:
        m = metrics_by_cur[cur].get(account)
        if m is None:
            m = NodeMetrics(account_id=account)
            metrics_by_cur[cur][account] = m
        return m

    for t in eligible:
        accounts.update((t.sender, t.receiver))
        for acc in (t.sender, t.receiver):
            m = metric(t.currency, acc)
            node_days[(t.currency, acc)].add(t.observed_date)
            m.first_seen = t.observed_date if m.first_seen is None else min(m.first_seen, t.observed_date)
            m.last_seen = t.observed_date if m.last_seen is None else max(m.last_seen, t.observed_date)
        if t.is_self_transfer:
            metric(t.currency, t.sender).self_transfer_count += 1
            continue
        pair_tx[(t.sender, t.receiver, t.currency)].append(t)
        s = metric(t.currency, t.sender)
        r = metric(t.currency, t.receiver)
        s.outgoing_minor += t.amount_minor
        s.outgoing_count += 1
        r.incoming_minor += t.amount_minor
        r.incoming_count += 1

    by_currency: dict[str, CurrencyGraph] = {}
    for cur in sorted(metrics_by_cur):
        g: nx.DiGraph = nx.DiGraph()
        g.add_nodes_from(sorted(metrics_by_cur[cur]))
        edges: dict[tuple[str, str], AggregatedEdge] = {}
        for (snd, rcv, c), txs in sorted(pair_tx.items()):
            if c != cur:
                continue
            edge = AggregatedEdge(
                sender=snd,
                receiver=rcv,
                currency=cur,
                amount_minor=sum(t.amount_minor for t in txs),
                n_transactions=len(txs),
                transaction_ids=tuple(t.transaction_id for t in txs),
                first_date=min(t.observed_date for t in txs),
                last_date=max(t.observed_date for t in txs),
            )
            edges[(snd, rcv)] = edge
            g.add_edge(snd, rcv, amount_minor=edge.amount_minor, n_transactions=edge.n_transactions)
        for acc, m in metrics_by_cur[cur].items():
            m.in_degree = g.in_degree(acc)
            m.out_degree = g.out_degree(acc)
            m.active_days = len(node_days[(cur, acc)])
        by_currency[cur] = CurrencyGraph(currency=cur, graph=g, edges=edges, metrics=metrics_by_cur[cur])

    dates = [t.observed_date for t in eligible]
    return GraphSnapshotData(
        transfers=by_id,
        by_currency=by_currency,
        input_manifest_sha256=input_manifest_sha256(transfers),
        eligible_count=len(eligible),
        excluded_count=len(transfers) - len(eligible),
        window_start=min(dates) if dates else None,
        window_end=max(dates) if dates else None,
        accounts=frozenset(accounts),
    )
