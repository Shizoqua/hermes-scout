# Security policy

## Reporting a vulnerability

Found a weakness? Email the security inbox with steps to reproduce. Do not open a public ticket.
We reply within two working days and credit reporters once a fix ships.

## Practices

- Secrets live in the vault, never in the repository or in environment files committed by mistake.
- Every response sets a strict Content-Security-Policy header.
- Dependencies are scanned on every pull request.
