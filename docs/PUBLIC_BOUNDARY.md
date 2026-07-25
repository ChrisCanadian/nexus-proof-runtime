# Public Boundary

This repository is a newly written, standalone reference implementation.

## Included

- Generic tool and evidence contracts
- Permission and approval gates
- JSON Schema input/output validation
- Scoped idempotency
- Execution receipts
- Verified local artifacts
- Narrow claim/evidence checks
- Synthetic provider and test fixtures

## Intentionally excluded

- Nexus Synapse SSR implementation or query structure
- Retrieval, ranking, weighting, thresholds, promotion, decay, or fallback logic
- Prompt assembly, prompt envelopes, or schema-to-prompt mappings
- Memory, preference learning, identity, voice, modes, reflection, or self-model behavior
- Senate, Thinker, Dyad, attention, focus, correction, or post-turn orchestration
- Production schemas, migrations, endpoints, tools, payloads, paths, logs, or configuration
- Real user content or benchmark data

The project demonstrates a general engineering principle:

> A model may propose and describe an action; only runtime-owned evidence can establish that the
> action occurred.

It does not disclose how Nexus Synapse reconstructs continuity or assembles a turn.

