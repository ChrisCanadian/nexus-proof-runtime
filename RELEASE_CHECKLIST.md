# Owner Release Checklist

This file is operational guidance for the repository owner and may be removed from a tagged public
release.

- [ ] Confirm the public repository name and description.
- [ ] Confirm Apache-2.0 is the intended licence.
- [ ] Confirm `Nexus Proof Runtime` does not create unwanted trademark confusion.
- [ ] Run `ruff check .` and `pytest`.
- [ ] Run a secret scanner on the fresh repository.
- [ ] Confirm every fixture is synthetic.
- [ ] Confirm no private Git history is imported.
- [ ] Confirm no Nexus SSR, memory, identity, prompt, mode, Senate, Thinker, Dyad, or production
      correction code is added.
- [ ] Create the GitHub repository with a fresh initial commit.
- [ ] Enable branch protection and required `validate` checks.
- [ ] Publish `0.1.0` as a release candidate, not a production certification.

## October V1 SSR Gist

Leave the existing V1 SSR Gist as a dated origin artifact. Do not import it into this repository,
combine its Git history with this project, or present it as the current SSR implementation.

Add a short archival header to the Gist:

> Historical V1 proof of concept, originally published in 2025. This intentionally incomplete
> reference predates the current Nexus Synapse runtime. It omits production schemas, coordination
> logic, ranking/weighting, prompt assembly, operational constraints, and current implementation
> details. It is preserved as an origin artifact, not maintained production software.

If a repository-format SSR publication is wanted later, write a new sanitized retrospective that
explains the public contract and evolution without copying the Gist's implementation details.

