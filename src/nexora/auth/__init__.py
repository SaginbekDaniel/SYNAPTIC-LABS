"""Named-user authentication: Argon2id password hashes and server-side sessions.

Only established primitives are used: ``argon2-cffi`` (Argon2id, RFC 9106 parameters) for passwords,
``secrets`` for session tokens, SHA-256/HMAC from the standard library for at-rest token digests and
the session-bound CSRF token. No custom cryptography.
"""
