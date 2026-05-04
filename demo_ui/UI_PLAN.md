# VerdeAI Demo UI — Implementation Plan

## Tech Stack
- **Vite** (build tool + dev server)
- **React 18** (UI framework)
- **Tailwind CSS v3** (utility-first styling)
- **React Router v6** (client-side routing)
- **JavaScript** (no TypeScript)

No external component library — build with Tailwind primitives only.

---

## Backend Prerequisites (must do before UI works)

### Add CORS middleware to api-gateway and chat-rag

**`services/api-gateway/app/main.py`** — add before other middleware:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**`services/chat-rag/app/main.py`** — same block.

Rebuild both: `sudo docker compose up -d --build api-gateway chat-rag`

---

## Project Layout

```
demo_ui/
├── index.html
├── vite.config.js
├── package.json
├── tailwind.config.js
├── postcss.config.js
├── .env                        # VITE_API_URL, VITE_CHAT_URL, VITE_KC_URL
├── UI_PLAN.md
└── src/
    ├── main.jsx
    ├── App.jsx                 # Router + AuthContext provider
    ├── api/
    │   ├── client.js           # fetch wrapper — injects Authorization header, handles 401
    │   ├── auth.js             # login(), register()
    │   ├── documents.js        # upload(), list(), get(), remove()
    │   ├── analyses.js         # create(), list(), get(), pause(), resume(),
    │   │                       #   results(), recommendations(), missingRequirements()
    │   ├── orgProfile.js       # getProfile(), updateProfile(), completeness(),
    │   │                       #   clauses(), getClause(), updateClause()
    │   └── chat.js             # createSession(), streamChat() → EventSource helper
    ├── context/
    │   └── AuthContext.jsx     # access_token, tenant_id, login(), logout()
    ├── hooks/
    │   ├── useJobProgress.js   # WS ticket → WebSocket → progress events
    │   └── useChatStream.js    # SSE streaming for chat
    ├── components/
    │   ├── Layout.jsx          # top nav + sidebar shell
    │   ├── Sidebar.jsx         # nav links with active highlight
    │   ├── ProtectedRoute.jsx  # redirect to /login if not authed
    │   ├── Badge.jsx           # status pill (pending/running/complete/failed/paused)
    │   ├── ProgressToast.jsx   # floating WS progress overlay
    │   └── Spinner.jsx
    └── pages/
        ├── Login.jsx
        ├── Register.jsx
        ├── Dashboard.jsx
        ├── Documents.jsx
        ├── OrgProfilePage.jsx
        ├── AnalysisListPage.jsx
        ├── AnalysisDetailPage.jsx
        └── ChatPage.jsx
```

---

## Environment Variables (`.env`)

```env
VITE_API_URL=http://localhost:8000
VITE_CHAT_URL=http://localhost:8001
VITE_KC_URL=http://localhost:8080
VITE_KC_REALM=verdeai
VITE_KC_CLIENT_ID=verdeai-frontend
```

---

## API Layer (`src/api/`)

### `client.js`
- Base `apiFetch(path, options)` wrapper around `fetch`
- Reads token from `localStorage.getItem("access_token")`
- Adds `Authorization: Bearer <token>` header automatically
- On 401 → clears storage → redirects to `/login`
- Exports `apiGet`, `apiPost`, `apiPut`, `apiDelete`, `apiPostForm` (multipart)

### `auth.js`
```js
login(email, password)
  POST /auth/login → { access_token, refresh_token, expires_in }
  Stores access_token + refresh_token in localStorage

register(email, password, firstName, lastName, organisationName)
  POST /auth/register → { user_id, tenant_id }
```

### `documents.js`
```js
uploadDocument(file)          POST /documents (multipart)
listDocuments()               GET  /documents
getDocument(id)               GET  /documents/{id}
deleteDocument(id)            DELETE /documents/{id}
```

### `analyses.js`
```js
createAnalysis(scope="full")  POST /analyses
listAnalyses()                GET  /analyses
getAnalysis(id)               GET  /analyses/{id}
pauseAnalysis(id)             POST /analyses/{id}/pause
resumeAnalysis(id)            POST /analyses/{id}/resume
getResults(id)                GET  /analyses/{id}/results
getRecommendations(id)        GET  /analyses/{id}/recommendations
getMissingRequirements(id)    GET  /analyses/{id}/missing-requirements
```

### `orgProfile.js`
```js
getProfile()                  GET  /org-profile
updateProfile(fields)         PUT  /org-profile
getCompleteness()             GET  /org-profile/completeness
listClauses()                 GET  /org-profile/clauses
getClause(clauseId)           GET  /org-profile/clauses/{clauseId}
updateClause(clauseId, data)  PUT  /org-profile/clauses/{clauseId}
```

### `chat.js`
```js
createSession()               POST http://localhost:8001/chat/session → { session_id }

streamChat(question, sessionId, onToken, onCitations, onDone, onError)
  POST http://localhost:8001/chat  (SSE via fetch + ReadableStream)
  Parses SSE frames: token → onToken(content), citations → onCitations([...]),
  done → onDone(), error → onError(msg)
```

---

## WebSocket Hook (`hooks/useJobProgress.js`)

```js
// Usage: const { messages, status } = useJobProgress(jobId)
// 1. POST /ws/ticket → ticket
// 2. new WebSocket(`ws://localhost:8000/ws/jobs/${jobId}?ticket=${ticket}`)
// 3. Accumulate messages, detect terminal status (done/failed/deduped)
// 4. Auto-close on terminal event
```

---

## Pages

### 1. `Login.jsx`
- Email + password form
- Calls `auth.login()` → stores tokens → navigates to `/dashboard`
- Link to `/register`

### 2. `Register.jsx`
- Email, password, first name, last name, organisation name
- Calls `auth.register()` → auto-login → navigates to `/dashboard`

### 3. `Dashboard.jsx`
- **Org Profile Completeness card** — circular progress % + "Complete your profile" CTA
- **Latest Analysis card** — status badge + gap count + "View Results" link
- **Documents card** — count of processed docs + "Upload" CTA
- **Quick Actions** — Start Analysis button (disabled if one already running)

### 4. `Documents.jsx`
- **Upload zone** — drag-and-drop or file picker, calls `uploadDocument()`
- After upload → opens WS via `useJobProgress(document_id)` → live progress toast:
  - Stages: `extract → chunk → embed → index → done`
- **Document table** — filename, status badge, pages, uploaded date, delete button
- Status badge colours: queued=gray, processing=blue, complete=green, failed=red

### 5. `OrgProfilePage.jsx`

**Tab 1 — Organisation Info:**
- Form with 6 fields (name, industry, size, location, primary activities, leadership roles)
- `PUT /org-profile` on save

**Tab 2 — Clause Fields:**
- Left panel: list of 32 clauses with mini progress bar (filled/total)
- Right panel: selected clause fields — each field rendered as:
  - `text` → `<input type="text">`
  - `textarea` → `<textarea>`
  - `boolean` → toggle switch
  - `select` → `<select>` (options from `default` field if array)
- Save button → `PUT /org-profile/clauses/{clause_id}` with `{field_path: value}` map

**Overall completeness banner** at top — progress bar + percentage.

### 6. `AnalysisListPage.jsx`
- **Start Analysis button** — calls `createAnalysis("full")` → redirects to detail page
  - Disabled + tooltip if analysis already running
- **Analysis history table** — analysis_id (short), status badge, gap count, scope, date
- Click row → `/analyses/{id}`

### 7. `AnalysisDetailPage.jsx`
URL: `/analyses/:id`

**Header:** analysis ID, status badge, created date, Pause/Resume button

**Live progress panel** (visible when status = running/pending):
- Auto-opens WebSocket via `useJobProgress(analysis_id)`
- Shows scrolling log of clause progress messages
- Progress bar: clauses completed / 32

**Tab 1 — Gap Results** (visible when complete):
- Table of 32 clauses: clause_id, title, decision badge, confidence %, reasoning (truncated)
- Decision badge colours: Met=green, Partially Met=yellow, Not Met=red, Insufficient Evidence=gray
- Click row → expand inline: full reasoning + citations + missing evidence list

**Tab 2 — Recommendations:**
- Cards grouped by clause: clause title header + list of recommendations
- Each recommendation: text, cost pill (1–5 stars), effort (N weeks), impact pill (1–5 stars)

**Tab 3 — Missing Requirements:**
- Cards grouped by clause: field_path label + request_text block
- Copy-to-clipboard button per request

### 8. `ChatPage.jsx`
- **Session management** — auto-creates session on mount via `createSession()`
- **Message list** — user bubbles (right, green) + assistant bubbles (left, white)
- **Streaming** — assistant bubble renders tokens as they arrive (typewriter effect)
- **Citations panel** — after response, collapsible "Sources" section with filename + page
- **Input bar** — textarea + send button (disabled while streaming)
- **New Chat button** — creates new session, clears messages
- Auto-scroll to bottom on new tokens

---

## Routing (`App.jsx`)

```
/              → redirect to /dashboard
/login         → Login (public)
/register      → Register (public)
/dashboard     → Dashboard (protected)
/documents     → Documents (protected)
/org-profile   → OrgProfilePage (protected)
/analyses      → AnalysisListPage (protected)
/analyses/:id  → AnalysisDetailPage (protected)
/chat          → ChatPage (protected)
```

---

## Sidebar Navigation

```
🌿 VerdeAI  (logo/brand)
────────────
Dashboard
Documents
Org Profile
Analysis
Chat
────────────
[logout]
```

Active link highlighted with green left border + light green background.

---

## Status Badge Component

| Status | Colour |
|---|---|
| pending | gray |
| running | blue (animated pulse) |
| paused | yellow |
| complete | green |
| failed | red |
| deduped | purple |
| Met | green |
| Partially Met | yellow |
| Not Met | red |
| Insufficient Evidence | gray |

---

## Key Implementation Notes

### Auth token storage
- Store `access_token` in `localStorage` — sufficient for a demo
- On app load, check token exists → if not, redirect `/login`

### SSE streaming (Chat)
- Use `fetch()` with `ReadableStream` (not `EventSource`) since we need POST + auth header
- Parse SSE frames manually: split on `\n\n`, extract `data:` lines, JSON.parse

### WebSocket auth
- Ticket is single-use with 30s TTL — request ticket immediately before connecting
- Reconnect logic: if WS closes before terminal event, re-fetch ticket + reconnect (max 3 retries)

### Analysis auto-poll fallback
- If WS is unavailable, poll `GET /analyses/{id}` every 5s while status is pending/running

### Tailwind colour scheme
- Primary: `green-600` / `green-700` (ISO environmental theme)
- Accent: `emerald-500`
- Background: `gray-50`
- Cards: `white` with `shadow-sm` and `rounded-xl`

---

## Implementation Order

1. **Project scaffold** — `npm create vite@latest`, install deps, Tailwind config
2. **API layer** — `src/api/` modules + `client.js`
3. **AuthContext** + Login + Register pages
4. **Layout** + Sidebar + ProtectedRoute
5. **Dashboard** page (wires up multiple API calls)
6. **Documents** page + `useJobProgress` hook
7. **OrgProfile** page (form heavy)
8. **AnalysisListPage** + **AnalysisDetailPage** (tabs + WS progress)
9. **ChatPage** + `useChatStream` hook (SSE)
10. **Polish** — badges, error states, loading skeletons, empty states

---

## Backend CORS Fix (Required)

Without CORS headers the browser will block all API calls. Add to **both** services:

**`services/api-gateway/app/main.py`** and **`services/chat-rag/app/main.py`**:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Then: `sudo docker compose up -d --build api-gateway chat-rag`
