---
name: react-feature-component
description: Create a React component or page inside a Sportie frontend feature folder (community-game-ranker or video-analyzer) using Bootstrap and the Sportie theme tokens. Use for any new UI such as game lists, vote buttons, upload forms, or top-down court views.
---

# React feature component

Arguments: `<feature>` (community-game-ranker | video-analyzer) and what the component does.

1. Put the file at `frontend/src/features/<feature>/components/<Name>.jsx`. Use a function
   component with a default export. Read `frontend/src/App.jsx` once to match its style.
2. Data: call the helpers in `frontend/src/features/<feature>/api.js` and never call `fetch`
   inline. Track `loading`, `error`, and `data` with `useState`/`useEffect`, and render all
   three states.
3. Styling:
   - Use Bootstrap 5 classes for layout and components (`container`, `row g-4`, `card`,
     `btn`, `badge`).
   - Colors come from the `--sp-*` tokens in `frontend/src/theme.css`, either through existing
     helper classes (`text-sp-green`, `text-sp-red`, `eyebrow`) or `var(--sp-...)`. Don't
     hardcode hex values.
   - Make it accessible: use semantic elements, add `aria-label` to icon buttons, and keep
     everything reachable by keyboard.
4. Required notices (`.claude/docs/ethics-checklist.md`):
   - Ranker pages that show injuries or scores get the gambling disclaimer.
   - Video upload forms get the consent notice.
5. Feature-only UI stays in its folder. Move a component to a shared location only when both
   features use it.
6. Verify with `cd frontend && npm run build`.
