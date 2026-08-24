# TAILER Public Task Summary

Detailed task state and private roadmap material are kept in the ignored local
`arch/` control plane. This public summary intentionally contains no private
architecture or product decisions.

The current codebase is a development prototype. Consult the source, tests,
and [public testing guide](docs/testing.md) for verified behavior and remaining
implementation gaps.

Policy enforcement remains partial: model allow lists and optional per-key
output-token ceilings are enforced before provider resolution, while dynamic
rate and aggregate budget enforcement remain incomplete.
