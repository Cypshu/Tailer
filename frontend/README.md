# TAILER Frontend

Next.js 16 App Router dashboard for the TAILER development prototype.

## Routes

- `/`: landing page
- `/login`: demo login
- `/admin`: admin overview
- `/admin/users`: user creation and listing
- `/admin/keys`: key creation, one-time reveal/copy, prefix listing, and revocation
- `/user/dashboard`: current user's safe key metadata and durable usage

## Run

~~~bash
npm install
cp .env.example .env.local
npm run dev
~~~

Open http://localhost:3000.

On PowerShell:

~~~powershell
Copy-Item .env.example .env.local
npm run dev
~~~

The complete Docker stack can instead be managed from the repository root with `tailer.cmd` on Windows or `tailer.sh` on Bash systems. See the root [setup guide](../docs/setup.md).

## Configuration

`NEXT_PUBLIC_API_URL` selects the browser-accessible backend URL and defaults to http://localhost:8000.

`frontend/lib/api.ts` is the shared dashboard client. It reads `access_token` from `localStorage`, injects a bearer header, clears local state on 401, and redirects to `/login`.

The dashboard JWT is not a runtime Sub-API key. Runtime integrations must set their Sub-API key explicitly.

`POST /admin/keys` is the only response that contains a newly generated raw Sub-API key. The admin page keeps that creation result in a dismissible one-time panel so it can be copied. List/detail state and the user dashboard contain only `key_prefix` plus metadata; the frontend cannot recover a dismissed bearer from the backend.

The backend now exposes metadata-only `/admin/provider-credentials` and
`/admin/model-configs` APIs, but this frontend does not call or render them. An
operator must use the authenticated API to configure an encrypted OpenAI
credential and public-model alias. Provider plaintext and ciphertext must never
be added to browser state, client types, logs, or rendered responses.

## Structure

~~~text
app/
  admin/
  login/
  user/
  globals.css
  layout.tsx
  page.tsx
components/
lib/
  api.ts
public/
~~~

`frontend/AGENTS.md` requires agents to read the relevant installed Next.js 16 documentation before changing framework code.

## Verify

~~~bash
npm run lint
npm run build
~~~

Both commands passed on 2026-08-02.

## Known gaps

- Some UI copy and controls describe future policy work.
- Edit/delete user controls and key rotation are not implemented.
- There is no recovery flow for a dismissed creation-only key; rotation must be implemented separately.
- Usage labelled "this month" is not yet date-windowed.
- There is no frontend component or browser end-to-end test suite.
- The seeded runtime uses a deterministic mock fallback unless an operator has
  configured a model route. The backend OpenAI adapter passes mocked-upstream
  integration tests, but no disposable live credential has satisfied the exit
  gate yet; successful live OpenAI completion is the sole remaining Iteration 2
  acceptance gap.
- No provider-credential or model-configuration UI exists.
- Rate, token, cost, and per-key maximum-token controls remain descriptive; the
  backend does not enforce them yet.

Current feature status is tracked in the root [task board](../tasks.md), not in this README.
