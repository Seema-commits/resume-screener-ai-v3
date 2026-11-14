# TalentLens AI - React frontend

Vite + React 19 + TypeScript (strict) + Tailwind 4, TanStack Query, react-router.
It talks only to the FastAPI backend in `../backend`.

```bash
npm install
npm run dev        # http://localhost:5173, /api forwarded to http://127.0.0.1:8000
npm test           # Vitest
npm run lint       # oxlint
npm run build      # type-check + production build into dist/
```

Run the API alongside it: `COOKIE_SECURE=false uvicorn backend.main:app --reload` from the repo root.

## Layout

- `src/api/` - the only code that calls the API (`client.ts`: cookie + CSRF header;
  `sse.ts`: reads the streamed scan progress; `endpoints.ts`; `types.ts`).
- `src/auth/` - who is signed in (`/api/auth/me`) and route guards. Hiding a page is
  never the only check: the API refuses anything the role can't do.
- `src/pages/` - Login, Change password, Screen resumes, Scan history, Scan detail.
- `src/components/` - shared UI, results tables, the candidate drawer.
- `functions/api/[[path]].ts` - Cloudflare Pages Function that forwards `/api` to Cloud Run.
- `public/_headers` - CSP and security headers on Cloudflare Pages.

## Safety rules

- Resume and AI text is always rendered as React text. `src/test/safety.test.ts` fails if
  `dangerouslySetInnerHTML`, `innerHTML`, `eval`, `new Function`, `document.write` or browser
  storage appears in `src/`.
- Nothing is stored in the browser: the session is an httpOnly cookie, the CSRF token and
  results live in memory only.
- CSV downloads go through `lib/csv.safeCell`, so a cell can't run as a spreadsheet formula.
- Uploads are checked here for type, size and count, and checked again by the API.
