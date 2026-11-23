# Postmortem: 14 March outage

## Summary

For 47 minutes every client failed to connect. The TLS certificate on the gateway had expired at
09:12 UTC and nobody was warned beforehand.

## Cause

Certificates were renewed by hand from a calendar reminder. The reminder belonged to an engineer who
had left, so it never fired.

## Fixes

- Certificates now renew automatically every 60 days.
- A monitoring alert fires when any certificate has fewer than 14 days left.
- Renewal ownership moved to the platform rota instead of one person.
