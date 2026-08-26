# Owner Release Checklist

This file is retained as historical owner-operational guidance for the initial public release.
The `v0.1.1` release was published on 2026-07-31 as a normal security-hardening reference release,
not as a GitHub prerelease and not as a production certification.

## Initial-release controls — historical record

- [x] Confirm the public repository name and description.
- [x] Confirm Apache-2.0 is the intended licence.
- [x] Confirm `Nexus Proof Runtime` does not create unwanted trademark confusion.
- [x] Run `ruff check .` and `pytest`.
- [x] Run a secret scanner on the fresh repository.
- [x] Confirm every fixture is synthetic.
- [x] Confirm no private Git history is imported.
- [x] Confirm no Nexus SSR, memory, identity, prompt, mode, Senate, Thinker, Dyad, or production
      correction code is added.
- [x] Create the GitHub repository with a fresh initial commit.
- [x] Publish `v0.1.1` as a security-hardening reference release.

This checklist does not claim third-party security review, production certification, or current Nexus
runtime parity. Current release status belongs in the README, tagged release, and repository history.

## October V1 SSR Gist

Leave the existing V1 SSR Gist as a dated origin artifact. Do not import it into this repository,
combine its Git history with this project, or present it as the current SSR implementation.

The archival framing remains:

> Historical V1 proof of concept, originally published in 2025. This intentionally incomplete
> reference predates the current Nexus Synapse runtime. It omits production schemas, coordination
> logic, ranking/weighting, prompt assembly, operational constraints, and current implementation
> details. It is preserved as an origin artifact, not maintained production software.

If a repository-format SSR publication is wanted later, write a new sanitized retrospective that
explains the public contract and evolution without copying the Gist's implementation details.
