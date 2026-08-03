# TAILER Documentation

The active documentation set is intentionally small.

Current checkpoint (2026-08-02): Iterations 1 and 2 are complete. The 229-case
suite passes in normal and reversed order, and native Gemini Interactions passed
two live encrypted completions across backend restart with durable pricing,
redaction, exact cleanup, and complete stack restoration. Iteration 3 policy
enforcement is next.

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
