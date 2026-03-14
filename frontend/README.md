# Profiler Console (Svelte + shadcn-style UI)

A Vercel-inspired dashboard built with **SvelteKit** (no Next.js), featuring:

- Dashboard listing projects
- Per-project row actions: graph button + three-dots menu
- Clickable project name to open detail page
- Detail page with graphs, manual profiling trigger, and metrics reload section
- Add-project flow with:
  - GitHub link or source upload mode
  - binary file input
  - architecture selection

## Tech

- SvelteKit
- Tailwind CSS
- shadcn-style component patterns in Svelte (`src/lib/components/ui`)

## Quick start

```bash
npm install
npm run dev
```

Then open `http://localhost:5173`.

## Verify

```bash
npm run check
npm run test
```

## Notes

- Data is persisted in `localStorage` via `projectStore`.
- This implementation is mock-first and ready to swap to real API calls.

