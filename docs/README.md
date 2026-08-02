# TAILER Documentation

The active documentation set is intentionally small.

Current checkpoint (2026-08-02): Iteration 1 persistence is complete. Iteration
2 secure-provider implementation and its 182-case mocked-upstream regression
suite pass, but the iteration exit gate remains open until a disposable real
OpenAI credential succeeds through the running stack. Migration/Compose,
encrypted-route failure, restart durability, redaction, and log-safety checks
now pass; live OpenAI success is the sole remaining acceptance gap.

## Active

- [Product charter](product.md): problem, users, MVP boundaries, and invariants
- [Architecture](architecture.md): current implementation, target components, and contract decisions
- [Setup](setup.md): lifecycle controllers, local development, Compose, migrations, and systemd
- [Testing](testing.md): dual-adapter regression evidence, infrastructure checks, manual smoke flow, and known gaps
- [Implementation plan](../TAILER_Project_Implementation_Plan.md): ordered delivery slices
- [Task board](../tasks.md): next executable work
- [Agent guide](../AGENTS.md): repository rules and source-of-truth order
- [systemd operator guide](../deploy/systemd/README.md): install and operate the Linux Compose service

## Historical

Files under [archive](archive/README.md) record earlier agent sessions, status snapshots, and plans. They are preserved for provenance and may contradict current code. Do not use them as implementation truth.
