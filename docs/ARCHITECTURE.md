# Architecture

## Trust boundary

The model may supply only a tool name, version, schema-valid arguments, and structured claims
containing a claim kind plus evidence reference ID. The host application owns the principal,
scope, permissions, approvals, parent cancellation signal, claim-verification context, receipts,
and artifacts.

![Nexus Proof Runtime trust boundary](assets/trust-boundary.svg)

| Component | Responsibility | Does not decide |
|---|---|---|
| ToolRegistry | Versioned manifest/handler lookup and visibility | Whether a result is true |
| PolicyEngine | Permissions, enablement, approvals | Model intent |
| ToolExecutor | Validation, retry, timeout isolation, idempotency, terminal recording | User identity |
| ReceiptStore | Durable execution evidence with principal and scope | Natural-language claims |
| ArtifactStore | Owner-bound atomic bytes, metadata, SHA-256 verification | Whether content is good |
| ClaimGate | Authorize structured claims against trusted context and evidence | Rewrite model prose |
| ProviderGateway | Capability filtering and narrow fallback | Tool authorization |

## Execution order

1. Resolve an exact tool version.
2. Evaluate host-owned permissions and approvals.
3. Validate model-authored arguments.
4. Hash canonical arguments and look for an exactly scoped replay.
5. Derive a fresh execution-local cancellation signal linked to the host parent.
6. Invoke the handler with trusted identity plus that child signal.
7. Validate the handler output.
8. Record a terminal receipt and execution record.
9. Verify claim ownership and artifact bytes before accepting structured claims.

The order is intentionally small and generic. It is not a description of the Nexus Synapse
conversation runtime.

## Evidence authorization identity

Receipt and artifact claim verification requires an exact match on:

    principal ID + scope

Evidence remains valid across correlation IDs within that boundary. Correlations link operations
for tracing and may change between creation and later presentation; treating them as authorization
would prevent legitimate later-turn citation without adding an ownership boundary.

Claim values do not contain identity fields. The active principal and scope come only from an
ExecutionContext or ClaimVerificationContext supplied by the trusted host.

## Idempotency identity

An idempotency replay requires an exact match on:

    key + principal + scope + tool name + tool version + canonical argument hash

Reusing a caller-provided key with different arguments, a different principal, or a different
scope does not replay an unrelated result.

## Cancellation ownership

ExecutionContext retains the host-owned parent cancellation signal. ToolExecutor creates a linked
child signal for each invocation. Timeouts cancel only the child signal. Explicit host
cancellation propagates to active children and intentionally prevents later invocations using the
same parent context.

This remains cooperative cancellation; non-cooperative handlers require process or container
isolation.

## Failure semantics

Only ToolRuntimeError instances marked retryable, or a code explicitly listed in a manifest, may
retry. Unexpected programming errors terminate the execution as failed. Provider fallback
similarly catches only RetryableProviderError, so application bugs are not silently reclassified
as provider outages.