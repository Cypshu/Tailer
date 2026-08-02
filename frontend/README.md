# TAILER Frontend

Next.js 16 App Router dashboard for the TAILER development prototype.

## Routes

- `/`: landing page
- `/login`: demo login
- `/admin`: admin overview
- `/admin/users`: user creation and listing
- `/admin/keys`: key creation, reveal/copy, and revocation
- `/user/dashboard`: current user's keys and mock-backed usage

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

## Configuration

`NEXT_PUBLIC_API_URL` selects the browser-accessible backend URL and defaults to http://localhost:8000.

`frontend/lib/api.ts` is the shared dashboard client. It reads `access_token` from `localStorage`, injects a bearer header, clears local state on 401, and redirects to `/login`.

The dashboard JWT is not a runtime Sub-API key. Runtime integrations must set their Sub-API key explicitly.

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

- Some UI copy and controls describe future policy/provider work.
- Edit/delete user controls and key rotation are not implemented.
- Raw demo keys are still returned, revealed, and copied.
- Usage labelled “this month” is not yet date-windowed.
- There is no frontend component or end-to-end test suite.

Current feature status is tracked in the root [task board](../tasks.md), not in this README.
