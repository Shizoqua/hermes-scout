"""Password checks and hashing."""

MIN_LENGTH = 12


def check_policy(candidate):
    if len(candidate) < MIN_LENGTH:
        return f"use at least {MIN_LENGTH} characters"
    if candidate.lower() in {"password1234", "qwertyuiop12"}:
        return "too common"
    return None


def hash_password(hasher, candidate):
    """argon2id with a per-user salt; only the hash is stored, never the original text."""
    return hasher.hash(candidate)


def verify(hasher, stored_hash, candidate):
    return hasher.verify(stored_hash, candidate)
