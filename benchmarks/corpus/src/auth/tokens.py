"""Access tokens for signed-in users."""

import secrets
import time

TOKEN_TTL_SECONDS = 900  # an access token is valid for 15 minutes
REFRESH_TTL_SECONDS = 30 * 24 * 3600


def issue_pair(user_id, sign):
    now = int(time.time())
    access = sign({"sub": user_id, "exp": now + TOKEN_TTL_SECONDS})
    refresh = secrets.token_urlsafe(32)
    return access, refresh


def rotate(refresh_store, old_refresh, user_id, sign):
    """Each refresh token works once; using it hands out a new pair and burns the old one."""
    refresh_store.revoke(old_refresh)
    access, refresh = issue_pair(user_id, sign)
    refresh_store.save(refresh, user_id, ttl=REFRESH_TTL_SECONDS)
    return access, refresh
