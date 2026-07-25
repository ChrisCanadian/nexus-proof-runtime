# Security and Scope

## Reporting

Please report suspected vulnerabilities privately to the repository owner before opening a public
issue containing exploit details.

## Security properties in scope

- Host-owned principal and permission context
- Deny-by-default tool authorization
- Explicit approval requirements
- Input and result schema validation
- Scoped idempotent replay
- Receipt and artifact evidence checks
- Basename-only artifact filenames
- Atomic artifact replacement
- SHA-256 tamper detection

## Out of scope

This reference does not sandbox Python handlers. A handler runs with the permissions of its host
process. Network isolation, operating-system permissions, secrets management, malware scanning,
rate limiting, distributed locking, and forced process termination belong to the deployment layer.

Timeouts set the cooperative cancellation token and return a timed-out outcome. A handler that may
ignore cancellation must be isolated in a worker process or container controlled by the host.

Receipts establish what this runtime recorded; they are not cryptographic non-repudiation and are
not a substitute for an externally secured audit log.

