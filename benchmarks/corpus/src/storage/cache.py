"""Read-through cache in front of the primary store."""

TTL_SECONDS = 300


def get_list(cache, store, list_id):
    key = f"list:{list_id}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    value = store.load_list(list_id)
    cache.set(key, value, ttl=TTL_SECONDS)
    return value


def save_list(cache, store, list_id, value):
    """Write to the store first, then drop the cached copy so the next read sees fresh data."""
    store.save_list(list_id, value)
    cache.delete(f"list:{list_id}")
