"""Background job queue for applying edits."""

MAX_ATTEMPTS = 5
DEAD_LETTER = "sync-dead-letter"


def handle(job, apply, queue):
    try:
        apply(job)
    except Exception:
        job["attempts"] = job.get("attempts", 0) + 1
        if job["attempts"] >= MAX_ATTEMPTS:
            queue.push(DEAD_LETTER, job)  # parked for a human to look at
        else:
            queue.push("sync", job, delay=30 * job["attempts"])
