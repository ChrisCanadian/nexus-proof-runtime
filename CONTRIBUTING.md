# Contributing

Contributions should preserve the project's narrow boundary: verified tool execution and evidence.
Please do not add Nexus-specific cognitive, memory, identity, prompt, or orchestration concepts.

Before submitting a change:

```bash
ruff check .
pytest
```

Add failure-path tests for changes to authorization, idempotency, execution, artifacts, or claims.
Use synthetic fixtures only. Do not include credentials, private endpoints, production logs, user
data, or copied code from a private system.

