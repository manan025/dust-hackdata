# Profiler Console (Svelte + shadcn-style UI)

A Vercel-inspired dashboard built with **SvelteKit** (no Next.js), featuring:

- Dashboard listing projects
- Per-project row actions: graph button + three-dots menu
- Clickable project name to open detail page
- Detail page with graphs, manual profiling trigger, and metrics reload section
- Add-project flow with:
  - GitHub link or source upload mode
  - source file upload to Supabase Storage (returns URL)
  - binary file input
  - architecture selection

## Quick start

```bash
npm install
npm run dev
```

Then open `http://localhost:5173`.

## Supabase setup (required for Upload source)

Create `.env` with:

```bash
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
SUPABASE_SOURCE_BUCKET=project-sources
```

Notes:

- `SUPABASE_SOURCE_BUCKET` is optional (defaults to `project-sources`).
- Make sure the bucket exists in Supabase Storage.
- The upload endpoint is `POST /api/uploads/source` and returns a public URL.

## Verify

```bash
npm run check
npm run test
```

## Notes

- Data is persisted in `localStorage` via `projectStore`.
- This implementation is mock-first and ready to swap to real API calls.
