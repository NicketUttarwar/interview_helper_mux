# Interview Helper Mux — Web GUI

React + TypeScript operator console for the FastAPI backend.

## Stack

- **React 19** + **TypeScript**
- **Vite 6** (build → `../src/interview_mux/web/static/`)

## Commands

```bash
cd frontend
npm ci           # from package-lock.json (see SETUP.md if Rollup arch errors)
npm run dev      # Vite dev server; proxies /api → http://127.0.0.1:8765
npm run build    # Production bundle into src/interview_mux/web/static/
```

From repo root:

```bash
./scripts/build_gui.sh   # build only
./scripts/run.sh         # builds static if missing, then starts server
```

## Source layout

| Path | Role |
|------|------|
| `src/App.tsx` | Shell layout |
| `src/context/AppContext.tsx` | Global state, polling, API consent |
| `src/components/guidance/` | Reuse (`StageReuseSection`, `StageReuseOfferCard`), write approval, hash badges |
| `src/components/gates/TranscriptReviewPanel.tsx` | G0 chunk navigator + bulk edit |
| `src/components/workspace/TranscriptDockViewer.tsx` | Synced karaoke word editor |
| `src/components/workspace/FuzzyReplacePopover.tsx` | Fix similar words panel (80–100% strictness) |
| `src/utils/fuzzyMatch.ts` | Client-side fuzzy word scoring for batch replace |
| `src/hooks/useStageReuseOffers.ts` | Shared reuse-offer fetch (modal only when open; hidden in Stage detail) |
| `src/utils/sourceAudioHash.ts` | Canonical 12-char hash short from run meta |
| `src/api/client.ts` | Fetch wrapper |
| `src/types/` | API TypeScript types |
| `src/styles/app.css` | Operator console styles |

Backend contract: [docs/workflows/api-reference.md](../docs/workflows/api-reference.md).
