# TAILER Public Repository Guide

This repository is a development-stage TAILER gateway. Keep provider
credentials, local environment files, private architecture/roadmap material,
and generated test artifacts out of Git.

## Before editing

1. Run `git status --short --branch` and preserve unrelated work.
2. Read the relevant source, tests, and public documentation.
3. Keep endpoint behavior compatible unless the task explicitly changes it.
4. Never add provider credentials, raw bearer keys, encryption ciphertext, or
   production secrets.

The private local control plane is under ignored `arch/`. When present, read
`arch/STATE.md` and the active work order before TAILER iteration work. Do not
stage or publish `arch/`.

## Validation baseline

```text
cd frontend && npm run lint && npm run build
cd backend && python -m compileall -q app tests && python -m pytest
docker compose config --quiet
```

Use the setup and testing guides for environment-specific commands. The root
`.gemini_api` file is a disposable local input for the explicit smoke command;
never print, stage, copy, or reuse its value as a production secret.
