# Larkspur architecture

Larkspur keeps task lists in sync across phones, tablets and the web app.

## Components

- **Gateway**: a small HTTP service that checks access and forwards calls to the right worker.
- **Workers**: pick jobs off the queue (`src/sync/queue.py`) and apply them.
- **Primary store**: PostgreSQL 16, one schema per region.
- **Cache**: Redis, in front of the hottest reads (`src/storage/cache.py`).
- **Search**: built into the primary store (`src/search/index.py`).

## Request flow

1. A device sends a batch of edits to the gateway.
2. The gateway writes them to the queue and answers 202 straight away.
3. A worker merges the edits (`src/sync/conflicts.py`) and writes the result.
4. Other devices pick up the change on their next poll.
