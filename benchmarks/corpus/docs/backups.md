# Backups and restores

## Nightly dumps

A scheduled job runs `pg_dump` at 02:00 UTC for every region and uploads the compressed file to
object storage. Files are kept for 30 days, then expire automatically.

## Restore drill

Once a month someone on call restores last night's dump into a scratch instance and checks the row
counts against production. A drill that fails is treated as an incident.

## Point in time

Write-ahead logs are archived every five minutes, so we can recover to any moment in the last week.
