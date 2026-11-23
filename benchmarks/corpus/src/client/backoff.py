"""HTTP client helpers: wait and try again when the server pushes back."""

import random
import time

MAX_ATTEMPTS = 6
BASE_DELAY = 0.5


def call_with_retry(send, request):
    """Send ``request``; on HTTP 429 or 503 wait with exponential delay plus jitter and resend."""
    for attempt in range(MAX_ATTEMPTS):
        response = send(request)
        if response.status not in (429, 503):
            return response
        retry_after = response.headers.get("Retry-After")
        delay = float(retry_after) if retry_after else BASE_DELAY * 2**attempt
        time.sleep(delay + random.uniform(0, delay / 2))
    return response
