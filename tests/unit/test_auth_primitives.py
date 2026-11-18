"""Password hashing and token primitives (no database)."""

from __future__ import annotations

from nexora.auth import passwords, service, tokens


def test_argon2id_hashes_verify_and_are_salted():
    h1, h2 = passwords.hash_password("correct horse battery"), passwords.hash_password("correct horse battery")
    assert h1.startswith("$argon2id$v=19$m=65536,t=3,p=4$") and h1 != h2
    assert passwords.verify_password(h1, "correct horse battery")
    assert not passwords.verify_password(h1, "correct horse batterY")
    assert not passwords.verify_password("not-a-hash", "anything")
    assert not passwords.needs_rehash(h1)


def test_passwords_are_unicode_normalised():
    # "ﬁ" (U+FB01 ligature) and "fi" are the same password after NFKC.
    assert passwords.verify_password(passwords.hash_password("ﬁnancial-network-1"), "financial-network-1")


def test_password_policy_is_length_based():
    assert passwords.password_problem("short") is not None
    assert passwords.password_problem("x" * 12) is None
    assert passwords.password_problem("x" * 257) is not None


def test_session_tokens_are_random_and_well_formed():
    a, b = tokens.new_session_token(), tokens.new_session_token()
    assert a != b and tokens.well_formed(a) and len(a) == 43
    assert not tokens.well_formed(a + "=") and not tokens.well_formed("a b")
    assert tokens.token_digest(a) != tokens.token_digest(b) and len(tokens.token_digest(a)) == 64


def test_csrf_token_is_bound_to_the_session():
    a, b = tokens.new_session_token(), tokens.new_session_token()
    assert tokens.csrf_matches(a, tokens.csrf_token(a))
    assert not tokens.csrf_matches(a, tokens.csrf_token(b))
    assert not tokens.csrf_matches(a, "")
    assert not tokens.csrf_matches(a, "é" * 64)  # non-ASCII input does not crash the comparison


def test_usernames_normalise_and_validate():
    assert service.normalize_username("  Ａnalyst.One ") == "analyst.one"  # full-width A → A
    assert service.username_problem("ab") is not None
    assert service.username_problem("analyst one") is not None
    assert service.username_problem("analyst.one@bank-x_1") is None
