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
- Principal- and scope-bound receipt and artifact claims
- Basename-only artifact filenames
- Atomic artifact replacement
- SHA-256 tamper detection
- Parent cancellation propagation with per-execution timeout isolation

## Evidence ownership

Claim verification requires a trusted host context. A successful tool receipt verifies only when
its kind and status are valid and its principal ID and scope exactly match that context. Artifact
records capture the same owner fields at creation, and artifact claims enforce both ownership and
content integrity. Model-authored Claim values contain only a kind and reference ID, so they cannot
supply or override identity.

Correlation IDs remain trace linkage rather than authorization boundaries. A principal may
legitimately cite durable evidence from an earlier correlation within the same scope. Crossing
either the principal or scope boundary is rejected with a specific mismatch result.

## Cancellation lifecycle

ExecutionContext owns the parent cancellation signal. ToolExecutor derives a fresh linked child
signal for every invocation. A timeout cancels only that child, so sequential and concurrent calls
using the same trusted identity context remain independent. Explicit host cancellation of the
parent propagates to every child and prevents later calls.

Cancellation is cooperative. A handler that ignores cancellation must be isolated in a worker
process or container controlled by the host.

## Test interpretation

Line coverage measures executed statements; it does not establish these security properties.
Dedicated invariant tests separately exercise receipt ownership, scope ownership, artifact
ownership, idempotency isolation, model identity exclusion, and cancellation isolation.

## Out of scope

This reference does not sandbox Python handlers. A handler runs with the permissions of its host
process. Network isolation, operating-system permissions, secrets management, malware scanning,
rate limiting, distributed locking, and forced process termination belong to the deployment layer.

Receipts establish what this runtime recorded; they are not cryptographic non-repudiation and are
not a substitute for an externally secured audit log.