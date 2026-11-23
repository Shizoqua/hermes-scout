"""Merging edits that two devices made to the same task while disconnected."""


def newer(a, b):
    """Compare two vector clocks: 1 if a happened after b, -1 if before, 0 if concurrent."""
    keys = set(a) | set(b)
    a_ahead = any(a.get(k, 0) > b.get(k, 0) for k in keys)
    b_ahead = any(b.get(k, 0) > a.get(k, 0) for k in keys)
    return (a_ahead and not b_ahead) - (b_ahead and not a_ahead)


def merge(local, remote):
    """Keep the causally later edit; for truly concurrent edits the latest wall-clock write wins."""
    order = newer(local["clock"], remote["clock"])
    if order:
        return local if order > 0 else remote
    return max(local, remote, key=lambda edit: edit["written_at"])
