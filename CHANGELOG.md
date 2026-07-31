# Changelog

## 0.1.1 - 2026-07-31

### Security

- Bind receipt-backed success claims to the trusted active principal and scope.
- Bind artifact records and claims to their creating principal and scope.
- Require host-owned claim-verification context; model claims cannot supply identity.
- Isolate per-execution timeout cancellation from the reusable host context.

### Tests

- Add invariant tests for receipt, scope, artifact, idempotency, identity, correlation, and
  cancellation isolation.

### Compatibility

- `ClaimGate.check()` now requires a trusted `context` keyword argument.
- `ArtifactStore.create()` now requires the creating `ExecutionContext`.
