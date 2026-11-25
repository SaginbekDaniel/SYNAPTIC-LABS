"""Related-alert grouping (B-042): connected components over shared accounts, deterministic and order-free."""

from __future__ import annotations

import random

import pytest

from nexora.analytics.alert_groups import Groupable, group_items, groups_of


def g(item_id: str, subject: str, *accounts: str) -> Groupable:
    return Groupable(item_id, subject, frozenset(accounts))


FUNNEL = g("a1", "HUB", "s1", "s2", "HUB")
FANOUT = g("a2", "HUB", "HUB", "r1", "r2")  # same hub, other kind: H-11's case
CHAIN = g("a3", "r2", "r2", "x1", "x2")  # shares r2 with the fan-out only
LONE = g("a4", "Z", "z1", "z2")


def test_members_rule_joins_formations_that_share_any_account_transitively() -> None:
    by = group_items([FUNNEL, FANOUT, CHAIN, LONE], rule="members")
    assert by["a1"] == by["a2"] == by["a3"]
    assert by["a1"].item_ids == ("a1", "a2", "a3") and by["a1"].size == 3
    assert by["a4"].item_ids == ("a4",)
    assert len(groups_of(by)) == 2


def test_subject_rule_only_joins_formations_on_the_same_hub() -> None:
    by = group_items([FUNNEL, FANOUT, CHAIN, LONE], rule="subject")
    assert by["a1"] == by["a2"]
    assert by["a3"].item_ids == ("a3",)


@pytest.mark.parametrize("seed", range(20))
def test_grouping_does_not_depend_on_input_order(seed: int) -> None:
    """Metamorphic: any permutation of the same items gives the same groups and the same group ids."""
    rng = random.Random(seed)
    items = [g(f"id{n:02d}", f"S{rng.randrange(8)}", *(f"acc{rng.randrange(30)}" for _ in range(3))) for n in range(25)]
    reference = {k: (v.group_id, v.item_ids) for k, v in group_items(items).items()}
    shuffled = items[:]
    rng.shuffle(shuffled)
    assert {k: (v.group_id, v.item_ids) for k, v in group_items(shuffled).items()} == reference


def test_group_id_is_content_derived() -> None:
    first = group_items([FUNNEL, FANOUT])["a1"].group_id
    assert group_items([FANOUT, FUNNEL])["a2"].group_id == first
    # A different membership is a different group.
    assert group_items([FUNNEL, FANOUT, CHAIN])["a1"].group_id != first
    # The rule is part of the identity.
    assert group_items([FUNNEL, FANOUT], rule="subject")["a1"].group_id != first


def test_every_item_is_kept_exactly_once() -> None:
    items = [FUNNEL, FANOUT, CHAIN, LONE]
    by = group_items(items)
    assert sorted(by) == sorted(i.item_id for i in items)
    assert sorted(i for grp in groups_of(by) for i in grp.item_ids) == sorted(i.item_id for i in items)


def test_empty_input_and_duplicate_ids() -> None:
    assert group_items([]) == {}
    with pytest.raises(ValueError, match="unique"):
        group_items([FUNNEL, FUNNEL])
