# CortexViral — Product Requirements

## Original Problem Statement
Pixel-perfect clone of `agent.enrichlabs.ai/marketing` rebuilt and rebranded twice (Automatex → CortexViral) as an **all-in-one AI marketing platform**:
- AI marketing agents (Nova, Sam, Kai, Angela)
- Multi-platform social content publishing (38+ channels in catalog)
- AI Content Studio (newsletter, blog post, multi-platform post, video script, product update)
- SEO Review + Site Scan with auto-generated post drafts
- Admin panel (user management, audit log, broadcasts, ticket inbox)
- Help Center with AI chatbot (CortexBot) + Help Articles + Tickets

## Tech Stack
- **Frontend**: React 18 + Tailwind + Shadcn UI + Lucide icons + Axios
- **Backend**: FastAPI + Motor (async MongoDB) + emergentintegrations
- **Auth**: Emergent-managed Google Auth (cookie `session_token`, samesite=none, secure=True)
- **LLM**: gpt-5 via Emergent LLM Key
- **Admin**: hardcoded email allow-list (currently `williams342@gmail.com`)

## Architecture
```
/app
├── backend/
│   ├── server.py                (FastAPI app — single-file, ~1485 lines)
│   ├── tests/test_scheduling_and_optimal.py
│   └── requirements.txt
├── frontend/src/
│   ├── pages/
│   │   ├── Marketing.jsx        (Landing)
│   │   ├── dashboard/           (Overview, Main, Performance, MarketingCalendar, Studio, SeoReview, SiteScan, Compose, Channels, Posts, Leads, Insights, Help)
│   │   └── admin/               (Overview, Users, Tickets, Audit, Broadcasts)
│   ├── components/              (DashboardLayout, ProtectedRoute, BroadcastBanner, ImpersonateBanner, ui/*)
│   ├── context/AuthContext.jsx
│   └── App.js
└── memory/                      (PRD.md, test_credentials.md)
```

## Implemented (cumulative)
- 2026-02-28 (part 42) **🏟️ Convene — Multi-step team orchestrator**
  - **What it is**: One brief runs sequentially through N specialists (each one sees the prior agents' answers as context), then Atlas synthesizes a single ranked executive summary with next-3-actions. The team behaves like a Slack huddle: builds on each other rather than firing N independent answers.
  - **Backend** (`routes/agent_chat.py`):
    - Two new endpoints — `POST /api/ai/agent/convene` (sync, returns full JSON) and `POST /api/ai/agent/convene/stream` (SSE).
    - SSE event vocabulary: `started`, `agent_started`, `agent_done`, `summarizing`, `complete`, `error` — keepalive comments interleaved while LLM calls are in-flight (same pattern as `chat/stream`, prevents ingress timeouts on 60-90s chains).
    - Strict validator `_resolve_convene()` — distinguishes `agents=None` (use default chain) from `agents=[]` (explicit error → 422), dedupes repeated agents, max 5 per convene, accepts display-name aliases (`iris`/`atlas`).
    - Default chain: Research → SEO → Copy → Atlas synthesizes (configurable via `agents` and `summarizer` fields).
    - Each chain agent gets a system-prompt suffix with the full prior-team transcript + "build on what's there, don't repeat, ≤350 words" guardrail.
    - Synthesizer always runs on `deep` task type unless overridden — highest leverage step of the chain, worth the extra cost.
    - Spend tracking integrated: each chain agent + the synthesizer write rows to `llm_usage`, so the admin spend card surfaces convene costs alongside regular chats.
    - Persists a `convene_summary` memory row after every successful run — future agent_chats can recall the team's prior verdict via the existing memory retrieval layer.
  - **Frontend** (`pages/dashboard/AITeam.jsx::ConveneModal`):
    - "Convene the team" CTA card on the AI Team page (next to "Ask Atlas").
    - Modal with brief textarea + specialist multi-select chips (Iris/Sam/Nova/Kai/Angela; default 3 selected).
    - **Live SSE progress UI**: each picked agent gets a row that transitions ⌛ pending → 🔄 running (violet spinner) → ✓ done (green check, expanded markdown answer in a card). Atlas's synthesis row appears below with its own status line.
    - **Executive summary panel** renders below the chain with a violet `Sparkles` accent — the final synthesized output.
    - Fetch + ReadableStream pattern (same as `/agent/chat/stream`).
  - **8 new pytest cases** (`tests/test_convene.py`):
    - `TestConveneValidation` (5): auth · unknown agent → 422 · empty chain `[]` → 422 (NOT silent fallback to default) · >5 agents → 422 via pydantic `max_length` · repeated agents silently deduped (verified via the first SSE `started` event).
    - `TestConveneHappyPath` (3): full sync chain produces ordered transcript + non-trivial summary, FUPS/HANDOFF markers stripped from chain outputs; SSE event order invariant (`started → agent_started → agent_done → summarizing → complete`); convene persists exactly one `convene_summary` memory row.
    - Tests gracefully skip with a clear message when the Emergent LLM key budget is exhausted (encountered during this session — was temporarily at $38.40 / $38.40 cap).
  - **All 59 agent-stack tests pass** (test_agent_chat + test_agent_handoff + test_model_router + test_agent_stream + test_ai_team_and_spend + test_convene).
  - **Live UI screenshot-verified**: Convene modal with stubbed SSE shows the full flow — brief input, 3 selected specialists, 3 progress rows each with their own output card, Atlas status line, and the violet "Executive Summary" panel below with the ranked ideas + next-3-actions.
  - **Live curl-verified**: real chain (Iris → Sam → Nova → Atlas) on "Launch plan for AI marketing SaaS targeting indie creators" produced a clean executive summary with three named "strongest ideas" attributed to the right specialists and three ranked actions.


- 2026-02-28 (part 41) **💰 LLM spend dashboard + 🧠 Persisted mode prefs + 🏛️ Unified AI Team page**
  - **Per-agent mode persistence** (`routes/agent_chat.py`):
    - New endpoints `GET /api/ai/agent/prefs` (returns `{prefs: {agent_id: mode}}`) and `PUT /api/ai/agent/prefs` body `{agent_id, mode}`. Strictly validated: unknown agent_id or mode → 422 (so a typo'd frontend can never silently write junk).
    - Persisted on the user doc as `agent_prefs.{agent_id}` (single-doc update — no separate collection).
    - Frontend `AgentWorkspace.jsx` loads prefs on mount, hydrates the mode chip when the active agent changes, and PUTs on every chip click (best-effort — a failed write doesn't block the UI).
  - **LLM spend tracking + Admin Overview card** (new `routes/llm_spend.py`):
    - Every successful agent_chat turn fires `record_llm_call(user_id, agent_id, mode, model)` which writes one row to a new `llm_usage` collection with an *estimated* per-call USD cost. Per-call costs hardcoded from published 2026 pricing (Opus $0.045, Sonnet $0.012, Haiku $0.0012, Gemini 2.5 Pro $0.008, GPT-5 $0.020). Prefix-matches family names so future minor versions inherit the right rate without code changes. Unknown models fall back to a $0.01 default so admins still see *something*.
    - Handoff sub-agent calls also tracked separately (`agent_id` = the sub-agent).
    - New `GET /api/admin/llm-spend?days=30` endpoint runs a single `$facet` aggregation returning totals + by_mode + by_agent + by_model + top_users (10) + biggest_driver (the single highest `(model, agent)` pair). `days` clamped 1..365; `days=0` falls back to default 30.
    - **Admin Overview card** (`AdminOverview.jsx::LlmSpendCard`):
      • Estimated USD total + call count, with "Approximated from per-call cost averages — accuracy ±20%" disclaimer.
      • Period toggle (7d / 30d / 90d).
      • Violet "Biggest cost driver" callout — appears when one (model, agent) pair eats ≥20% of spend: *"50% of spend is `claude-haiku-4-5-20251001` from Kai"*. At ≥60% adds "Nudge users toward Auto/Fast mode to lower bills."
      • 3-column breakdown: By Mode (with gradient progress bars + %), By Agent (top 6), Top Spenders (top 5 with hydrated email).
  - **Unified AI Team dashboard** (`/dashboard/team`, new `pages/dashboard/AITeam.jsx`):
    - "Ask Atlas" hero with one-line input; submitting routes to `/dashboard/agent/strategy?q=<prompt>` and AgentWorkspace auto-prefills the composer.
    - **4-panel 2×2 grid** with count badges + "Open" CTA on each:
      • **Active Conversations** (`GET /api/ai/agent/conversations/recent`) — derived from `agent_summary` memory rows via Mongo `$group`; one row per agent_id with the most-recent prompt preview + relative timestamp + color-coded agent badge.
      • **Pending Approvals** (`GET /api/approvals`) — first 4 posts with platform pills, scheduled date, content preview.
      • **Recent Memories** (`GET /api/memory/list`) — first 5 with kind badges.
      • **Trend Signals** (`GET /api/trends/recent`) — first 5 with Reddit/GTrends color-coded source pills, clickable through to permalinks.
    - Friendly empty states on each panel so a new user sees a guided onboarding view instead of 4 blank cards.
    - Added "AI Team" link as the **first** sidebar item (uses `Users2` icon from lucide).
  - **13 new pytest cases** (`tests/test_ai_team_and_spend.py`):
    - `TestAgentPrefs` (5): auth required · default empty prefs · set→get round-trip with two different agents · 422 on unknown agent_id · 422 on unknown mode.
    - `TestCostLookup` (2): known model lookups (Opus > Sonnet > Haiku ordering verified) · prefix-match for future versions · unknown models fall back to default cost.
    - `TestLLMSpendEndpoint` (4): admin auth · empty window → zeros not 404 · LIVE chat call actually writes a row that surfaces in the aggregate · `days` param clamped to 1..365.
    - `TestRecentConversations` (2): auth · dedupe per-agent (3 chats with Nova → 1 conversation row, latest preview).
  - **All 51 agent-stack tests pass** (`test_agent_chat.py` + `test_agent_handoff.py` + `test_model_router.py` + `test_agent_stream.py` + `test_ai_team_and_spend.py`).
  - **Live UI screenshot-verified**: AI Team page renders all 4 panels + Ask Atlas hero correctly. Admin Overview renders the LLM spend card with the "50% of spend is claude-haiku from Kai" insight callout exactly as designed.


- 2026-02-28 (part 40) **🔀 SSE streaming + 🤝 Universal agent handoff**
  - **Why**: A handoff (Atlas → Iris) is two sequential LLM calls (~30-50s combined) and was hitting Cloudflare's ~100s ingress idle timeout from the browser even though the backend ran fine. The fix is server-sent events with periodic keepalive pings, AND it lets us show the user *what's happening* during the wait.
  - **Universal handoff**: flipped `can_handoff = True` for every agent (was Atlas-only). Now Sam can ask Iris for keyword trends, Angela can ask Nova for positioning, Kai can ask Sam for SEO context, etc. Single delegation per turn (no chains). Server-side self-handoff guard rejects an agent delegating to itself — would just waste an LLM call in an ephemeral session.
  - **New endpoint `POST /api/ai/agent/chat/stream`** (`routes/agent_chat.py`):
    - Returns `text/event-stream` (SSE) with the following event vocabulary:
      • `started`   `{agent_id, agent_name, mode, model}` — immediate, so the UI can render "Thinking · deep mode" instantly.
      • `memories`  `{memories_used: [...]}` — after the vector-memory fetch.
      • `thinking`  `{phase: "primary"|"handoff", agent: "Iris"}` — right before each LLM call.
      • `handoff`   `{agent_id, agent_name, question}` — only when a delegation actually fired.
      • `keepalive` (sent as a `: keepalive` comment) — every ~10s while the LLM is busy.
      • `complete`  `{answer, follow_ups, memories_used, handoff, mode, model}` — final payload, same shape as the non-streaming endpoint.
      • `error`     `{message}` — graceful error frame instead of a torn connection.
    - Refactored shared orchestration into `_orchestrate(user, agent, payload)` — an async generator yielding `(event_name, data)` tuples. Both the streaming endpoint and the original `POST /api/ai/agent/chat` consume it, so we only ship orchestration logic once.
    - `_keepalive_while(task, every=10)` helper interleaves `keepalive` events while a synchronous LLM call is in progress. Uses `asyncio.shield` so the timeout doesn't cancel the underlying coroutine.
    - Response headers set `Cache-Control: no-cache` and `X-Accel-Buffering: no` (the latter required for nginx-style proxies to flush each chunk instead of buffering the whole response).
  - **Backwards compatible**: the original `POST /api/ai/agent/chat` still exists and returns the same JSON shape — handy for batch scripts / external API consumers / pytest. It just consumes the same generator under the hood and assembles the final dict.
  - **Frontend (`AgentWorkspace.jsx`)**:
    - Replaced the axios POST with a `fetch()` + `ReadableStream` reader. Parses each SSE record, updates a live `busyText` state ("Connecting…" → "Thinking · deep mode" → "Recalling 3 memories…" → "Delegating to Iris…" → "Iris is researching…" → final answer rendered).
    - Typing indicator now reads `<spinner> Iris is researching…` instead of the previous static "Atlas is thinking…" — feels alive even on slow handoffs.
    - 402 / cap-reached / network errors all still surface as toasts; user message rolls back so they don't lose what they typed.
  - **5 new pytest cases** (`tests/test_agent_stream.py`):
    - `TestStreamAuth` (2): 401 anon · 404 unknown agent.
    - `TestStreamHappyPath` (2): event ordering invariant (`started → memories → thinking → complete`), `complete` payload mirrors the non-streaming shape with `mode="fast"` + Haiku model id.
    - `started` event carries `{agent_id, agent_name, mode, model}` immediately.
  - **Updated handoff tests** (`test_agent_handoff.py`): replaced the "only Atlas can handoff" test with `test_self_handoff_rejected` (delegating to self → handoff filtered to None) and `test_any_agent_can_handoff` (Sam → Iris works).
  - **All 38 agent tests green** (`test_agent_chat.py` + `test_agent_handoff.py` + `test_model_router.py` + `test_agent_stream.py`).
  - **Live UI screenshot-verified**: Atlas → Iris handoff via SSE renders the cyan delegation pill, grey "deep" mode pill, memory chip, and spliced "Iris reports:" block all correctly.


- 2026-02-28 (part 39) **🎛️ Model routing layer — per-task user override**
  - **What changed**: Previously the LLM family was hard-coded per agent (Atlas → Opus, Iris → Gemini, others → Sonnet). Now the user can override on a per-turn basis via a compact "Mode" selector above the chat composer.
  - **Backend (`routes/model_router.py`)**:
    - New `USER_MODES` catalogue — 4 entries (`auto`, `fast`, `deep`, `creative`) each with `{id, label, blurb}`. `USER_MODE_IDS` exposed for fast validation.
    - New `resolve_user_mode(mode, agent_id) -> (provider, model, task)` — auto / None / unknown all gracefully fall back to the agent's natural task; `fast` routes to Haiku, `deep` to Opus, `creative` to Sonnet, etc. Returns the resolved task name so the API surfaces it in the response (handy for UI labels + debugging).
  - **Backend (`routes/agent_chat.py`)**:
    - `_ChatRequest` gains an optional `mode: str` field (validated as `<=24` chars; unknown values are silently treated as `auto` — never 422 the user).
    - Response payload now includes `mode` (resolved task name) and `model` (actual model id used) so the UI can show "Reply produced via Haiku" without a follow-up call.
    - New `GET /api/ai/agent/modes` endpoint returns the public `USER_MODES` list for the chip selector.
  - **Frontend (`AgentWorkspace.jsx`)**:
    - Loads `/ai/agent/modes` on mount; renders a `MODE  Auto · Fast · Deep · Creative` chip row above the textarea (`data-testid="agent-mode-selector"` + per-chip `agent-mode-{id}`). Active chip = violet pill.
    - Posts `{agent_id, message, mode}` to `/ai/agent/chat`.
    - Each agent reply now shows a tiny grey mode pill next to the agent name (`data-testid="agent-mode-pill"`) — hover reveals the actual model id (`claude-haiku-4-5-20251001`).
  - **13 new pytest cases** (`tests/test_model_router.py`):
    - `TestRouterUnit` (7): known task lookups · unknown falls back to default · `for_agent` returns per-persona defaults · explicit user mode beats agent default · `auto` / `None` / unknown silently fall back.
    - `TestModesEndpoint` (2): auth required · returns canonical set with full `{id, label, blurb}` shape.
    - `TestAgentChatRespectsMode` (4): default mode preserves agent's natural task (Nova → Sonnet) · `mode=fast` on Atlas re-routes from Opus → Haiku (live LLM call asserts `model` string contains "haiku" + NOT "opus") · `auto` is a no-op · garbage strings silently fall back.
  - **All 33 agent-related tests green** (`test_agent_chat.py` + `test_agent_handoff.py` + `test_model_router.py`).
  - **Live UI screenshot-verified**: clicking "Fast" chip → sending message → Atlas reply renders with grey `fast` pill next to her name.


- 2026-02-28 (part 38) **🤝 Multi-agent collaboration — handoff bug fix + UI verification**
  - **Root cause**: Atlas (Strategy/Claude Opus) was correctly emitting `<<HANDOFF>>iris: <question><<END>>` markers in her replies, but the server's `_extract_handoff()` was rejecting every single one with `agent_id not in AGENTS`. Reason: the system prompt instructs the LLM to delegate by **display name** (`iris`, `sam`, `kai`, `nova`, `angela`), but `AGENTS` is keyed by **internal id** (`research`, `sam`, `kai`, `nova`, `angela`). `iris` was never in the dict → handoff silently dropped, raw marker leaked into the answer, `handoff: null` returned to the UI.
  - **Fix** in `routes/agent_chat.py`:
    - Built `_AGENT_LOOKUP: dict[str, str]` mapping both lowercased display names AND internal ids to the canonical agent id. (`"iris" → "research"`, `"atlas" → "strategy"`, etc.)
    - `_extract_handoff()` now resolves the captured token through this lookup, so either name OR id works. Unknown tokens (typos) still safely reject, leaving the marker in the cleaned text for debugging instead of silently swallowing it.
  - **Verified live**: Curl test with Atlas → "fetch the top 3 rising AI marketing TikTok trends via Iris" now returns the full `handoff: {agent_id:"research", agent_name:"Iris", question:..., answer:...}` object plus the spliced `Iris reports: …` block in the main answer. Backend log shows two sequential LiteLLM calls: `claude-opus-4-7` (Atlas) → `gemini-2.5-pro` (Iris).
  - **Frontend UI verified** via Playwright: the cyan `↪ asked Iris` delegation pill (`data-testid="agent-handoff-pill"`) renders next to Atlas's name in the message bubble whenever `message.handoff` is non-null. Screenshot-confirmed on `/dashboard/agent/strategy`.
  - **11 new pytest cases** (`tests/test_agent_handoff.py`):
    - `TestExtractHandoffParser` (9): no-marker → None · parses by display name (`iris`→`research`) · parses by internal id · case-insensitive · rejects unknown agent (leaves marker for debug) · rejects empty question · truncates 600-char question to 300 · only first handoff extracted per turn · all 6 agent names resolve to correct ids.
    - `TestHandoffEndpointShape` (2): live Atlas→Iris round-trip validates the full `handoff` object shape + asserts `<<HANDOFF>>` marker never leaks into the user-facing answer + `"Iris reports"` block appears · sub-agents (Nova) can never produce a `handoff` even if their reply contains the marker (only Atlas has `can_handoff`).
  - **All 20 agent-chat tests green** (`test_agent_chat.py` + `test_agent_handoff.py`).
  - **Known infrastructure quirk**: a handoff is two sequential LLM calls (~30-50s combined). When called from the browser via the public ingress, the request can hit a Cloudflare/proxy 100s timeout. Backend itself returns 200 with the full payload. If this becomes a UX issue we'll switch to streaming SSE (already on the roadmap).


- 2026-02-28 (part 37) **📡 Reddit OAuth + Trend Ingestion unblocked**
  - **Root cause of the 403**: Reddit blocks anonymous `www.reddit.com/r/*.json` requests from datacenter IPs (AWS/GCP/Emergent infra) at the network layer regardless of User-Agent. Verified: `Mozilla/5.0`, `CortexViralBot/1.0`, even `old.reddit.com` → all 403.
  - **Fix in `routes/trends_engine.py`**: switched Reddit ingestion to the official **OAuth 2.0 application-only** flow (`client_credentials` grant on `https://www.reddit.com/api/v1/access_token` → `https://oauth.reddit.com/r/{sub}/hot`). Free, no user-context required, ~600 req / 10min limit.
  - **Token cache**: in-process bearer-token cache with 50-min TTL so we hit Reddit's auth endpoint at most ~1× per hour per worker. Auto-flushes on 401 so a mid-flight token expiry self-recovers on the next ingest tick.
  - **Graceful degradation**: when `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` are blank, the ingest short-circuits with `reddit: 0, reddit_configured: false` — Google Trends still runs, no 500/403 noise in logs.
  - **New env vars** (added to `/app/backend/.env`, blank by default): `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` (already pre-filled with a compliant value).
  - **New endpoint `GET /api/trends/status`** — reports per-source `{configured, note}` so the UI can render a setup hint when Reddit is offline.
  - **Frontend (`Trends.jsx`)**:
    - Amber `Reddit ingestion is offline` banner with inline link to `reddit.com/prefs/apps` + the exact env var names to paste.
    - Ingest toast now reads `"Google Trends: N · Reddit skipped (not configured)"` when Reddit is unavailable, instead of misleadingly counting "Reddit: 0".
    - Adds `Info` lucide icon import; `data-testid="trends-reddit-unconfigured-banner"`.
  - **11 new pytest cases** (`tests/test_trends_engine.py`):
    - `TestTrendsStatus` (2): auth required · per-source shape with `configured`/`note` keys, gtrends always true.
    - `TestTrendsSeeds` (2): auth required · default-niche fallback returns non-empty subs list.
    - `TestTrendsIngest` (3): auth required · ingest succeeds without 500/403 when Reddit unconfigured (asserts `reddit_configured: false` + `reddit: 0`) · watch-list (subreddits/keywords) persisted on the user doc.
    - `TestTrendsRecent` (2): auth required · `/recent` surfaces freshly-ingested gtrends rows.
    - `TestRedditOAuthScaffolding` (2): `_reddit_configured()` returns False when env blank · `_reddit_app_token()` short-circuits with `None` (no network call) when unconfigured.
  - **Existing tests still pass**: `test_trends_and_ablab.py` (10) + `test_memory.py` (10) → **31/31 trends-related tests green**.
  - **What you need to do to enable Reddit**: register a "script" app at https://www.reddit.com/prefs/apps (redirect URI can be anything — we don't use it for app-only flow), paste the `client_id` (the short string under the app name) into `REDDIT_CLIENT_ID` and the `secret` into `REDDIT_CLIENT_SECRET` in `/app/backend/.env`, restart backend. The banner disappears and `/trends/ingest` starts pulling hot posts from each watched subreddit.


- 2026-02-26 (part 36) **🔐 Sign-out-everywhere + ⏸️ Pause account + 📧 Password-changed email**
  - **Sessions management** — three new endpoints on `routes/account.py`:
    - `GET /api/account/sessions` returns `{total, others, current:{created_at,expires_at}}` so the dashboard can show "You're signed in on N other devices".
    - `POST /api/account/sessions/revoke-others` deletes every `user_sessions` doc for the user EXCEPT the one matching the calling cookie/bearer — keeps the current device alive after a stolen-laptop scare.
    - `POST /api/account/sessions/revoke-all` deletes all sessions including the caller's and clears the cookie. SPA redirects to `/` on success.
  - **Pause account (soft-delete)** — `POST /api/account/pause` body `{reason?}`:
    - Sets `users.status = "paused"` + persists `paused_at` and (optional) `pause_reason`. **No data is deleted.**
    - Deletes every active session for the user → all devices are signed out.
    - Fires `send_account_paused_email` (fire-and-forget) explaining "sign in any time to come back".
    - **Auto-reactivation** wired into all three login paths (`routes/auth.create_session`, `routes/password_auth.password_login`, `routes/magic_link.claim_magic_link`): if `status == "paused"` at login time, we flip it back to `"active"`, persist `reactivated_at`, and `$unset` the pause fields. The password-login response includes `reactivated: true` so the frontend can show a "Welcome back" toast.
    - `suspended` status remains a hard block (admin action) — only `paused` self-reactivates.
  - **Password-changed security email** — new `send_password_changed_email` template:
    - Fired from `_notify_password_changed()` after **every** successful `password/change` or `password/set-initial` call (NOT on `request-reset` since that flow already emails the new temp password).
    - Includes the timestamp, IP, and truncated User-Agent so the user can verify it was them.
    - Bold orange callout: *"If this wasn't you, your account may be compromised — reset your password immediately."*
    - CTA → `/dashboard/settings/account` for a quick lockdown.
  - **Frontend (`AccountSettings.jsx`)**:
    - New **Active sessions** card under Password — cyan monitor icon, dynamic "N active session" label, "Sign out other devices" (disabled when others=0) + "Sign out everywhere" rose button (with a `window.confirm` since it logs out the current tab).
    - New **Pause my account** amber card in Danger zone, above Delete account — opens `ConfirmPauseModal` with optional reason textarea. On confirm: pause API call → toast → redirect to `/`.
  - **8 new pytest cases** (`test_account_sessions_and_pause.py`):
    - `TestSessionsManagement` (4): auth required · list returns counts · revoke-others kills only extras + keeps current · revoke-all kills every session.
    - `TestPauseAccount` (3): auth required · pause flips status + clears sessions + preserves data · password login auto-reactivates a paused user (sets `reactivated: true` flag, clears `paused_at`).
    - `TestPasswordChangedEmail` (1): full change-password roundtrip writes a `password_changed`-tagged row into `email_log`.
  - **All 35 related-area tests still pass** (password_auth, account_delete, magic_link).
  - Screenshot-verified end-to-end on `/dashboard/settings/account`.

- 2026-02-26 (part 35) **📘 Facebook + 📸 Instagram OAuth scaffold (shared Meta app)**
  - **New `routes/oauth_meta.py`** — single module handling BOTH providers because they share the same Meta developer app and the same `/dialog/oauth` authorize endpoint. Only the scope set differs.
    - **Facebook scopes**: `public_profile`, `email`, `pages_show_list`, `pages_manage_posts`, `pages_read_engagement` — minimum to publish to a user's Facebook Page feed.
    - **Instagram scopes**: `public_profile`, `pages_show_list`, `pages_read_engagement`, `instagram_basic`, `instagram_content_publish` — IG Business publishing layered on Facebook Login (Meta's recommended modern flow, not the old `api.instagram.com/oauth/authorize` basic-display flow).
  - **8 new endpoints** matching the existing TikTok/LinkedIn shape (4 per provider): `/api/oauth/{facebook|instagram}/{start,callback,status}` + `DELETE /api/oauth/{facebook|instagram}`.
  - **Token cascade** (callback flow):
    1. Short-lived user token via `GET /oauth/access_token?code=...`
    2. Long-lived user token (~60d) via `grant_type=fb_exchange_token`
    3. List of Pages the user manages via `GET /me/accounts` — each Page has its own non-expiring Page access token.
    4. **Instagram only**: for each Page, query `instagram_business_account{id,username}` to resolve the linked IG professional account. If none found → redirect with `instagram=no_business_account` + friendly toast explaining how to convert their personal IG to a Business/Creator account.
  - **MongoDB collections**: `facebook_connections` (user_token + pages[]) and `instagram_connections` (user_token + pages[] + ig_accounts[]). Both mirror into the existing `channels` collection so the dashboard "connected" badge works for free.
  - **Reachability probe**: `/callback` accepts `HEAD` and returns 200 — required for Meta's "Verify Redirect URI" check during app review.
  - **HTTP-level error handling**: friendly redirects on `error=access_denied` (user cancelled), 503 on missing `META_APP_ID`/`META_APP_SECRET`, 400 on missing/invalid state, never leaks tokens.
  - **Channels page** auto-routes Connect clicks for Facebook/Instagram to the OAuth flow when `configured=true`, otherwise falls through to the existing mocked `/channels/connect` (so we keep a working demo until creds are pasted). Query-string toasts wired for all four success/denied paths + the IG no-business-account edge case.
  - **16 new pytest cases** (`test_oauth_meta.py`):
    - Status endpoints: anon → 401, authed → `{configured:false, connected:false}`.
    - `/start` 503s loudly when unconfigured (so users don't hit Meta with a broken `client_id`); if configured, validates URL shape + scope contents.
    - Callback HEAD probe returns 200 (Meta app-review prerequisite).
    - Callback with `error=access_denied` redirects with friendly query, not 500.
    - Callback without code/state → 400. Invalid state → 400.
    - Disconnect is idempotent (200 even with no existing connection).
    - **Scope-minimality assertions** that fail if anyone adds excess permissions (Meta reviewers reject apps requesting more than needed).
    - Redirect URI shape regression test.
  - **App-review compliance** now complete: `/privacy`, `/terms`, `/data-deletion` all live; both callback URLs return 200 on Meta's reachability probe; only minimal scopes requested.

  **URLs to paste into the Meta developer portal**:
  - Valid OAuth redirect URIs (paste both):
    - `https://cortexviral.com/api/oauth/facebook/callback`
    - `https://cortexviral.com/api/oauth/instagram/callback`
  - Privacy Policy URL: `https://cortexviral.com/privacy`
  - Terms of Service URL: `https://cortexviral.com/terms`
  - Data Deletion URL: `https://cortexviral.com/data-deletion`
  - App Domains: `cortexviral.com`

  **Pending — what we need from the user to go live**:
  - `META_APP_ID` (from Meta developer portal)
  - `META_APP_SECRET`
  - Once added to `/app/backend/.env` and the user redeploys to production, both Connect buttons flip from mocked → real OAuth automatically. **No code change needed.**
  - **Publishing endpoints** (POST to FB Page feed / IG container+publish) not yet implemented — those are a separate ~30-min job after OAuth is live and tested with real credentials.

- 2026-02-26 (part 33) **⚙️ Admin system settings — signup pause + per-platform kill-switches**
  - **New `routes/admin_settings.py`** — single-doc settings collection `system_settings` with two switches:
    - `signups_enabled: bool` (default True) — when False, brand-new Google signups return 503 from `/api/auth/session` so the marketing landing's "Start Growing" CTA stops creating accounts. Existing users + email-allowlisted admins always log in (so the admin can never lock themselves out of the panel). Admin-create + lead-form auto-create both bypass the pause so warm leads aren't lost.
    - `disabled_platforms: list[str]` (default []) — `/api/channels/connect` rejects with 403 when the requested platform is in the list, *including reconnects* (so an admin can yank a misbehaving integration immediately). Existing connections are NOT auto-disconnected — scheduled posts that already reference the platform continue to dispatch.
  - **Endpoints**:
    - `GET /api/admin/settings` (admin) — current settings.
    - `PATCH /api/admin/settings` (admin) — partial update; dedupe + sort platforms; audit-logged.
    - `GET /api/system/settings` (public) — exposes only user-safe fields. Channels page polls this on load to dim & lock disabled platforms.
  - **In-process 5s-TTL cache** on `get_settings()` so the hot paths (every `/auth/session`, every `/channels/connect`) avoid hitting Mongo. PATCH calls invalidate the cache so admin toggles propagate near-instantly.
  - **Frontend `/admin/settings` page** (`AdminSettings.jsx`):
    - "Accept new users" card: large emerald/rose icon, status copy that adapts to the toggle state ("Anyone with a Google account can sign up" vs "Brand-new signups paused"), a rose `SIGNUPS PAUSED` badge when off.
    - "Integration kill-switches" card: 3-column grid of platform rows (Instagram, TikTok, X, Facebook, LinkedIn, YouTube, Pinterest, Threads, Reddit) — each with platform icon, name, live status (`Enabled`/`Disabled`), and a custom emerald/grey toggle switch. Disabled rows turn rose.
    - **Dirty-state sticky action bar** at the bottom shows "Unsaved changes" + Discard / Save buttons. Bar only appears when local state ≠ server state.
    - New `Settings` icon item in the admin sidebar.
  - **Channels page** (`Channels.jsx`) — fetches `/api/system/settings` alongside the catalog and:
    - Adds a rose `DISABLED` pill next to the platform label.
    - Status line reads "Off — by admin" instead of "Not connected".
    - Connect button is disabled + greyed out + tooltipped ("This integration has been temporarily disabled by the admin").
    - Already-connected users can still hit Disconnect to clean up — they're not forced to keep a stale connection.
  - **10 new pytest cases** (`test_admin_settings.py`):
    - Public read returns defaults · admin auth required · GET shape · PATCH signups toggle persists & is visible publicly · PATCH platforms dedupes + sorts + ignores blanks · partial patch preserves untouched field · connect to disabled platform → 403 · connect to non-disabled platform succeeds · reconnect of a previously-connected disabled platform → 403 · admin-create bypasses signup pause.
  - **Bug found+fixed during testing**: pytest runs in a separate process from the live backend, so directly deleting the settings doc from a test wouldn't invalidate the backend's in-process cache → test order leakage. Reworked `_reset_settings()` to call `PATCH /api/admin/settings` instead so the cache is busted server-side. Saves future cache-related flake.
  - **Live screenshot-verified** end-to-end: toggling signups off → "SIGNUPS PAUSED" badge appears → toggling Pinterest off → save → /dashboard/channels shows Pinterest with the rose DISABLED pill and locked Connect button. Reset back to defaults verified.

- 2026-02-26 (part 32) **🔁 Series-aware cancel + Shift+drag series shift**
  - **Backend** (`routes/channels.py`):
    - `DELETE /api/posts/scheduled/{id}?scope=only|future|all` — new optional `scope` query param. `only` (default) preserves the old behavior. `future` deletes every still-scheduled post in the same `recurrence_group_id` whose `scheduled_at` ≥ this one (past instances kept). `all` deletes the entire series. Non-recurring posts always downgrade to `only`. Returns `{ok, deleted, scope}`.
    - `PATCH /api/posts/series/{group_id}` body `{delta_days, anchor_post_id?}` — shifts every still-scheduled post in the series by ±N days. With `anchor_post_id`, only the anchor + future are shifted. Rejects 0 delta as no-op, |delta| > 365 as 400, unknown group as 404.
  - **Frontend** (`MarketingCalendar.jsx`):
    - **`RecurrenceCancelModal`** — opens whenever a user clicks the X on a recurring chip (week view) OR the Cancel button on a recurring entry in the day-detail drawer (month view). Three lettered options as styled buttons: "Just this one" / "This + all upcoming" / "The entire series" (the destructive one shown in rose with the total count). Bypassed for non-recurring posts.
    - **Shift+drag series shift** — when a user holds Shift while dragging a 🔁 weekly chip to a different day, the drop opens **`SeriesShiftPromptModal`** asking whether to move just the instance, shift this + upcoming, or shift the entire series by the date delta they just dragged. Non-recurring posts and Alt+drag (duplicate) bypass this flow. Cursor / dropEffect updates while dragging.
    - Footer hint line updated to teach the new shortcuts: `Alt`+drag to duplicate · `Shift`+drag a 🔁 weekly post to shift the series.
  - **10 new pytest cases** (`test_series_ops.py`):
    - `TestSeriesCancel` (5): default scope deletes one, `scope=future` keeps past, `scope=all` deletes everything, unknown scope → 400, non-recurring posts downgrade to `only`.
    - `TestSeriesShift` (5): full-series shift verified by recomputing the delta on every member, anchored shift skips past members, zero delta is a no-op, unknown group → 404, |delta| > 365 → 400.
  - Cleaner mental model than per-row edit menus: same drag/click affordances the user already knows, recurrence options surface only when they're meaningful (= the post is part of a series).

- 2026-02-26 (part 31) **🔁 Repeat-weekly + 📅 Month grid + 🖱️ Alt-drag duplicate + 🪄 Lead-form auto-account**
  - **Repeat weekly toggle** (Compose & Publish):
    - New `repeat_weeks: Optional[int]` field on `PublishRequest` (2–12 enforced by Pydantic `ge`/`le`).
    - Backend `/api/channels/publish` — when `repeat_weeks` is set AND the post is scheduled into the future, materialises N posts at +0w, +1w, …, +(N-1)w. Each shares a `recurrence_group_id` (uuid4) + `recurrence_index` + `recurrence_total` for future series-aware operations. Returns `{ok, ids, recurrence_group_id, repeat_weeks}` instead of the single-post shape.
    - Frontend `Compose.jsx` — violet "Repeat weekly" panel appears underneath the schedule input the moment a date is picked. Toggle + number input (2–12, default 4) + helper copy.
  - **Month view — single row per day with stacked dots** (`MarketingCalendar.jsx`):
    - When `view === 'month'`, the range pads to full weeks (back to previous Sunday, forward to next Saturday) so the grid is always 7×N (typically 7×5 or 7×6).
    - New `<MonthGrid>` component: 7-col day grid, each cell shows date number + 2 compact post chips (time + truncated content) + per-platform colored dots (max 3 + "+N" overflow) + total post count pill.
    - Posts within a cell are draggable (same logic as week view) so rescheduling works from either view.
    - Out-of-month dates dimmed; today highlighted with emerald ring; past days greyed out.
    - Click any cell → opens a right-anchored side drawer (`<DayDetailDrawer>`) listing every post that day with full content, platform pills, recurrence badge (🔁 weekly · N/M), and inline cancel button.
  - **Alt+drag duplicate** (week + month view):
    - `onDragStart` / `onDragOver` / `onDrop` now check `e.altKey`. When held, cursor switches to `copy` and the drop POSTs a new scheduled post instead of PATCHing the existing one. Toast distinguishes "Duplicated" vs "Rescheduled". Lets a user clone the same Monday post to Wednesday and Friday in two drags.
  - **Lead-form auto-account + magic link**:
    - `routes/leads.py` already detects an anonymous lead, auto-creates a `user` doc (plan: free, `created_via: lead_form`), issues a magic link via `routes/magic_link.issue_magic_link`, and passes it to `send_lead_auto_reply` so the agent's auto-reply email includes a one-click sign-in button. Idempotent: if the email already has an account, we reuse it and just issue a fresh link.
    - **End-to-end verified**: POSTing a lead now creates the user, persists a `magic_links` row tagged `purpose=lead_claim`, and the auto-reply email body includes the sign-in CTA. Duplicate-email lead does NOT create a second user (verified by test).
  - **12 new pytest cases** (`test_recurrence_and_lead_claim.py`):
    - `TestRepeatWeekly` (5): N-instance creation, immediate-post bypass when not scheduled, 422 on `repeat_weeks<2`, 422 on `>12`, 12-week max accepted.
    - `TestLeadAutoCreate` (2): user + magic link created from anonymous lead, duplicate-email lead is idempotent.
    - Combined with the existing magic-link suite (12 cases), the new admin-create + magic-link + recurrence + lead-auto-create feature set has **19 dedicated tests** with full coverage. **All affected existing suites still pass.**

- 2026-02-26 (part 30) **🔐 Admin-create user + magic-link auth**
  - **New `routes/magic_link.py`** — `secrets.token_urlsafe(32)` tokens persisted in `magic_links` collection with a 7-day TTL index (Mongo auto-purges). **`GET /api/auth/claim?token=...`** validates the token (single-use, expiry, suspended-account checks), mints a fresh `session_token` and sets the same cookie shape Emergent Google Auth produces — so the rest of the app (deps.get_current_user, ProtectedRoute, billing, etc.) sees zero difference between Google-auth users and magic-link users.
  - **`POST /api/admin/users/create`** — body `{email, name, plan, comped, send_email, brand_name?, website?, niche?}`. Idempotent: if the email already exists, we update the doc and re-issue a fresh link instead of erroring (so admins can recover from "did the email get lost?" without manual DB ops). Returns `{user_id, magic_link, email_sent, new_user}` — admin can copy the link directly if email delivery fails.
  - **`POST /api/admin/users/{id}/resend-invite`** — generates a fresh magic-link token for an existing user and re-emails it. Useful when the original 7-day link expired or the user lost the email.
  - **Existing `send_account_invite_email` template** in `routes/email.py` provides the on-brand HTML with a styled CTA button + plain-text fallback URL + "expires in 7 days" notice — routes via the standard Mailtrap → Mailgun chain.
  - **Frontend `/auth/claim` page** (`AuthClaim.jsx`) — already-built dark-glass card with loader / success / error states; calls `/api/auth/claim`, then `refresh()` from AuthContext, then bounces to `/dashboard` (which itself bounces to `/onboarding` if not done).
  - **Admin UI**: `AdminUsers.jsx` "Create user" button → modal with email / name / plan / comped toggle / "send email" checkbox. Submitting shows a success card with the generated magic link in a read-only field + a "Copy" button (in case email delivery silently failed). Each user row also gets a new envelope-icon button (`admin-resend-invite-{user_id}`) that issues a fresh link and re-sends the email with one click.
  - **Bug found+fixed during testing**: `claim_magic_link` was comparing a naive datetime (returned from Mongo) against a tz-aware `datetime.now(timezone.utc)`, raising `TypeError: can't compare offset-naive and offset-aware datetimes` → 500 on every claim. Fixed by normalising `expires` to UTC-aware before the comparison.
  - **12 new pytest cases** (`test_magic_link.py`): admin-only on create/resend, idempotency on existing email, plan validation, full create→claim→/auth/me round-trip with cookie persistence, single-use token enforcement, resend issues a distinct token, 404 on unknown user. **All 158 backend tests pass.**

- 2026-02-26 (part 29) **🎯 Niche-aware AI personalization**
  - **New `_user_context_block(user_id)`** in `routes/ai.py` — reads the onboarding profile from the user doc and builds a compact system-prompt preamble: BRAND / NICHE / GOALS / PRIMARY PLATFORMS / STATED CHALLENGE. Includes an explicit instruction *"tailor your output to them. Don't restate the context back to them — just make the output reflect it. Avoid generic platitudes."* Empty profile → empty block (zero-cost fallback).
  - **New `_llm_for_user()` helper** wraps the existing `_llm()` factory and injects the context block transparently. All 9 user-facing AI call-sites in `routes/ai.py` (`generate-post`, `generate-video-script`, `seo-audit`, `viral-ideas`, `email-campaign`, `caption`, `comment`, `seo-keyword-research`, `multipost`) switched over by a regex pass. The A/B Hook Lab (`routes/ab_lab.py`) also wired through it.
  - **Trends Engine deliberately left untouched** — it serves a globally-cached daily feed, so injecting one user's context would poison it for everyone else.
  - **Live verified**: with a Fitness brand profile (`Iron Pulse Coaching`, niche `Fitness`, goal `Generate leads`, platform `TikTok`), the same generic prompt *"a hook about discipline"* now produces output referencing **"Iron Pulse Drill"** with hashtags `#IronPulseCoaching #GymTok #FitnessTips` and a CTA mentioning *"coaching link in bio"*. No tuning of the user prompt — just the context preamble.
  - **4 new pytest cases** (`test_personalization.py`): empty profile returns empty block, full profile renders all fields, long challenge truncated to 280 chars, end-to-end LLM call surfaces Fitness-niche signals. **145 backend tests pass.**

- 2026-02-26 (part 28) **🚀 New-user onboarding flow**
  - **New `/onboarding` page** — dark-gradient hero, "Welcome {first_name}" badge, "Let's tailor CortexViral to your brand" headline, 6 fields total (2 required text + 1 required pill-pick + 2 optional pill-pick + 1 optional textarea). Submitting writes to the user doc, marks `onboarding_completed_at`, and fires an admin notification email.
  - **Auto-redirect**: `ProtectedRoute.jsx` now checks `user.onboarding_required` and routes to `/onboarding` on first dashboard visit. Admins bypass the redirect; users who click "Skip for now" set a session flag (`onboarding_skipped`) so the redirect doesn't keep firing on every nav within that browser tab.
  - **Reminder banner** on `/dashboard/overview` — gradient violet→cyan strip with "Finish setting up your account · ~2 minutes" + arrow CTA. Persists across sessions for skippers until they complete.
  - **Backend**: new `routes/onboarding.py` exposing `GET /onboarding/options`, `GET /onboarding/me`, `POST /onboarding`. `/auth/me` now augmented with `onboarding_required: bool` so the SPA can route synchronously without an extra round-trip. Website URLs auto-normalised to add `https://` when user types a bare domain. Goal + platform values validated against the canonical lists (returns 400 on unknown values).
  - **Admin notification template** — `send_onboarding_admin_notification` fires only on FIRST completion (re-edits don't re-spam admins). Emails the addresses in `LEADS_NOTIFY_EMAILS` with a styled table: name, email, website (clickable), brand, niche, goals, platforms, optional challenge in italics. Gives the support team enough context to reach out with niche-specific playbooks.
  - **AdminUsers page** now shows `brand_name • website • niche` directly under each user's email, with clickable website link in violet. Backend `/admin/users` injects these fields with sensible defaults.
  - **AuthContext** exposes a new `refresh()` alias (= `checkAuth`) so the onboarding page can repopulate the user object post-submission.
  - **10 new pytest cases** in `test_onboarding.py` covering: auth, options shape, `required` flag, full submit roundtrip, invalid niche/goal rejection, `first_completion` semantics, AdminUsers profile fields, admin notification wiring. **141 backend tests pass.**

- 2026-02-26 (part 27) **📨 Lead-form email notifications**
  - **Bug fixed**: when a visitor submitted the "Choose Your Specialist" form (Nova/Sam/Kai/Angela), the lead was persisted but **no one got an email** — yet the UI toast said "X will reach out within 24 hours". Misleading + caused real leads to never receive a reply.
  - **New env var** `LEADS_NOTIFY_EMAILS` — comma-separated list of admin emails. Preview is set to `williams342@gmail.com,team@cortexviral.com`. **Production deploy must mirror this** in Emergent's environment variables panel or the admin won't get pinged.
  - **Two new templates in `routes/email.py`**:
    - `send_lead_admin_notification(lead, recipients)` — to every address in `LEADS_NOTIFY_EMAILS`. Subject `🔥 New lead for {agent}: {name} ({email})`. Body has a styled `<table>` with all form fields. CTA → `/admin/users`.
    - `send_lead_auto_reply(lead)` — to the lead's own address, written in the chosen agent's voice (Nova/Sam/Kai/Angela), quotes their pain-point if provided, sets the 24h expectation, gives them a CTA to sign in. Quietly skipped if the lead has no email.
  - **`routes/leads.py::create_lead`** now persists the lead first, then fires both emails fire-and-forget via the existing `fire()` helper. Try/except wraps the scheduling so an email outage can never block lead capture.
  - **Live verified**: POSTing a sample lead resulted in 3 `email_log` rows all `status: sent` — 2 admin notifications + 1 auto-reply, all via Mailtrap.
  - **3 new pytest cases**: full fan-out + auto-reply, missing-email edge case, lead always persists. **131 total backend tests pass.**

- 2026-02-26 (part 26) **📣 Email blast for admin broadcasts**
  - `POST /api/admin/broadcasts/{id}/email` body `{plans?: string[], include_comped: bool, dry_run: bool}` — sends an email version of the broadcast to all matching users via Mailtrap. Throttled 50ms between sends to stay polite. Dry-run mode counts recipients without sending so admin can confirm reach before firing.
  - `send_broadcast_email()` template — colour-coded severity badge (📣 info / ⚠️ warning / 🚨 critical / 🎉 success), styled blockquote, "Open dashboard" CTA. Wrapped in the same brand layout as welcome/gift/etc.
  - Broadcast doc now persists `emailed_at`, `emailed_by`, `emailed_recipients`, `emailed_sent`, `emailed_failed`, `emailed_filter` after a send — surfaced as a purple "Emailed N/M" pill on the broadcast row in AdminBroadcasts.
  - **Frontend modal** (`/admin/broadcasts`): purple "Email blast" button on each broadcast row → opens a modal with plan-filter chips (Free/Starter/Growth/Agency multi-select), an "Include comped users" switch, a "Preview" button that runs the dry-run and shows "N users match the filter", and a "Send to N" CTA that's disabled until preview has been run AND matched > 0 users. Confirmation prompt before send. Toast on success with sent/failed counts.
  - **Side bug fixed**: `BroadcastBanner.jsx` was crashing with "Cannot read properties of null (reading 'filter')" because `GET /api/broadcasts/active` was accidentally returning `null` after my edit to add the email-blast endpoint (the function body was severed). Restored the body + added defensive `Array.isArray()` guard on the client.
  - **6 new pytest cases** including a live Mailtrap-send roundtrip that verifies `emailed_sent / emailed_recipients` are persisted correctly. **128 backend tests pass.**

- 2026-02-26 (part 25) **✉️ Mailtrap integration (Mailgun → fallback)**
  - **Mailtrap** is now the primary transactional-email provider. Endpoint: `https://send.api.mailtrap.io/api/send`. Sender verified at `hello@cortexviral.com` (DKIM/DMARC/CNAME all pass; account `team@cortexviral.com`).
  - **Provider chain in `routes/email.py`**: tries `_send_via_mailtrap` first → falls back to `_send_via_mailgun` ONLY when Mailtrap is unconfigured or returns a 5xx/network error. 4xx responses (bad sender, invalid payload, etc.) deliberately don't trigger fallback because Mailgun would reject the same payload. `email_log` rows now carry a `provider` field and (when fallback fired) `fallback_from` + `primary_error` so admins can see exactly which path delivered.
  - **`/admin/email/health` card** label updated from "Mailgun delivery" → "Transactional email" so it's provider-agnostic now that two providers are in play.
  - **`_parse_from()`** helper splits `"Name <email@host>"` into Mailtrap's required `{name, email}` shape; also handles bare addresses and empty strings.
  - **4 live test sends to williams342@gmail.com** — Welcome / Gift / Trial / Past-due all returned `{sent: true, provider: "mailtrap", id: <uuid>}` ✅ Real email delivered through Mailtrap's verified `cortexviral.com` domain.
  - **Test added** (`TestProviderRouting::test_parse_from_with_display_name`). Existing helper tests updated to clear BOTH provider tokens. **11/11 email tests pass, 122 total backend tests.**
  - **Diagnostics done**: Mailtrap's first 401 was caused by `hello@demomailtrap.com` not being authorised for this account — Mailtrap requires the sender's domain to match a verified domain on the account. After swapping to `hello@cortexviral.com` (which has full DKIM+DMARC+CNAME pass), sends succeed.

- 2026-02-26 (part 24) **🪝 Admin "Webhook Events" page**
  - New `GET /api/admin/webhook-events?limit=50` reads the `stripe_events` collection. Returns `{total, items[], top_event_types[]}` — items include `event_id`, `type`, `received_at`, and a new `redeliveries` counter.
  - **Stripe webhook upgrade**: when a duplicate `event_id` hits the receiver, instead of silently short-circuiting we now `$inc redeliveries` and `$set last_redelivery_at` on the existing row — gives admins visibility into how often Stripe is re-delivering each event (signals downstream processing issues or network flakes).
  - **`/admin/webhook-events` page**: stats card with total + Refresh button, "By Event Type" pill row with top 8 types + counts, sortable table showing the last 50 events with green "Processed" / amber "+N Repeat" status pills. Empty-state copy ("No Stripe events received yet…") guides setup. New "Webhook Events" link in admin sidebar with `Webhook` icon.
  - **4 new pytest cases** covering admin auth, full payload shape, redelivery counter (verified to bump to 2 after 3 deliveries), `limit` clamping. **122 backend tests pass.**

- 2026-02-26 (part 23) **📬 Email Health card + cookie@1 resolution**
  - New `GET /api/admin/email/health?hours=24` aggregates `email_log` by status: `{total, sent, rejected, errored, skipped, delivery_rate, last_problem}`. `last_problem` surfaces the most recent non-success row with reason + Mailgun HTTP status so an admin can diagnose without opening MongoDB. `hours` is clamped 1–720.
  - **AdminOverview card** — sits between Funnel and AI analytics. Color-coded "Mailgun delivery" pill (Healthy ≥95% / Degraded ≥70% / Failing) with delivery-rate + total-sends sub-line, 4 tile counts (Sent / Rejected / Errored / Skipped — coloured red when non-zero), and an amber "Most recent issue" expandable line showing the status + subject + raw reason. Right now it correctly shows `Failing` + the Mailgun "Account disabled" 403, which is exactly what you'd need to debug deliverability.
  - **Fixed CRA build error** caused by the part-20 react-snap install: `puppeteer@1.20` pulled in `cookie@0.3.1` which clashed with `react-router@7`'s required `cookie@^1.0.1`. Added a yarn `"resolutions": {"cookie": "^1.0.1"}` pin in `package.json` — installs now resolve to `cookie@1.1.1` cleanly. Frontend compiles error-free.
  - **4 new pytest cases** in `test_email.py`: auth required, full response shape, `hours` clamped, `last_problem` correctly surfaces the most recent non-sent row. **118 backend tests pass.**

- 2026-02-26 (part 22) **🔒 Stripe webhook hardening**
  - **Signature enforcement** — new env flag `STRIPE_WEBHOOK_STRICT` (default `true` for safety). When strict + no secret → returns `503 "Webhook signature verification is required"`. When strict + secret → signatures verified as before (400 on tampered events). When `false` + no secret → falls back to the dev-mode parser (with a loud log warning). The preview environment uses `STRIPE_WEBHOOK_STRICT=false` so local testing without `stripe listen` continues to work; production should leave it at the default and supply `STRIPE_WEBHOOK_SECRET` from the Stripe dashboard.
  - **Idempotency** — every Stripe event has a stable `event.id` (e.g. `evt_abc`). Stripe retries delivery until it gets a 2xx, so duplicate deliveries are common in real traffic. We now insert every event_id into a new `stripe_events` collection with a unique index. Duplicates short-circuit with `{"received": true, "duplicate": true, "event_id": ...}` and **never re-apply plan changes** — avoiding the race where two `customer.subscription.updated` events flip a comped user's plan back and forth.
  - **4 new pytest cases** (`tests/test_stripe_webhook.py`): strict-mode rejection, idempotent dedupe of identical event_id, distinct event_ids both processed, bad-signature fallback. Verified live via curl: 503 when strict, 200 first time, 200 + `duplicate:true` on replay. **114 backend tests pass.**

- 2026-02-26 (part 21) **📧 Mailgun transactional emails**
  - `routes/email.py` — `send_email()` async helper using httpx + Mailgun HTTP API. Failures never raise — they log to a new `email_log` collection and return a structured `{sent, error/skipped, status?}` dict so callers can decide whether to retry.
  - **Lifecycle templates** (all use a shared dark-gradient header / light body brand layout):
    - **Welcome** — fired from `/api/auth/session` when a user is first created. CTA → `/dashboard/studio`.
    - **Gift plan** — fired from `/api/admin/users/{id}/plan` when admin comps a user to a paid tier. Includes the admin's `reason` quote when provided. CTA → `/dashboard`.
    - **Trial ending** — fired from Stripe webhook `customer.subscription.trial_will_end` (~3 days before charge). CTA → `/dashboard`.
    - **Past-due** — fired from Stripe webhook `invoice.payment_failed`. Suppressed for comped users (they're not on Stripe). CTA → `/dashboard`.
  - All sends are **fire-and-forget** via a small `fire(coro)` helper — never blocks the user's request.
  - `POST /api/admin/email/test` — admin-only debug endpoint to send any of the 4 templates to any address (great for QA + design previews).
  - **Bug found+fixed**: httpx 0.28 rejects `data=<list-of-tuples>` from `AsyncClient` with a cryptic `"Attempted to send an sync request"` error. Worked around by URL-encoding the form manually (`urlencode(payload)`) and POSTing as `content=` + explicit `Content-Type` header. Documented in the code comment for future grep-ability.
  - **6 new pytest cases** (`tests/test_email.py`): admin auth required, all 4 template kinds reachable, email_log persists, structured response shape, helpers gracefully skip when key isn't configured. **110 tests pass.**
  - **Sandbox status**: API key is wired and the integration works end-to-end. Mailgun is currently returning `403 "Account disabled"` — you'll need to either re-enable the sandbox in Mailgun (Dashboard → check account status / verify your sandbox recipients) or verify a real domain (e.g. `cortexviral.com`) and swap `MAILGUN_DOMAIN` in `.env`. Zero code changes needed once that's done.

- 2026-02-26 (part 20) **📊 Conversion funnel + 🚀 react-snap SEO prerender**
  - **Funnel** (P2):
    - New `routes/funnel.py`: `POST /api/track/visit` (anonymous, bot-filtered, IPs hashed before persistence) + `GET /api/admin/funnel?days=N` (admin only, 4 stages: Visitors → Signups → Activated → Paid + conversion rates between each step + comped tally).
    - `VisitTracker.jsx` mounts at App root, fires `/api/track/visit` on every public-route change (skips `/dashboard`, `/admin`, `/auth-callback`). Failures are swallowed — analytics never breaks the page.
    - Pageviews stored in new `pageviews` collection; unique visitors = distinct `(ip_hash, day)` tuples.
    - **AdminOverview** new "Conversion Funnel" widget — 4 stacked bars width-scaled to the largest stage, color-coded icons, per-stage conversion %, 7d/30d/90d filter pills, "Overall X% of visitors become paid" summary line.
    - **7 new pytest cases** (`test_funnel.py`): anonymous tracking, bot UA skipped, IPs hashed (never persisted raw), admin auth required, `days` param clamped 1-365, dedupes same-IP-same-day, full response shape validation. **104 tests pass.**
  - **SEO prerender** (P3):
    - Installed `react-snap` (~1.23, dev-dep). Configured to use the host's existing `/usr/bin/google-chrome` (no Chromium download, no extra MB).
    - New script: `yarn build:seo` = `craco build && react-snap`. **Default `yarn build` is unchanged** so the existing prod-deploy pipeline never accidentally runs the prerender.
    - 63 routes prerendered per pass: home, /pricing, /agents, /blog, /privacy, /terms, /sitemap, 5 AI-tool landings, 32 niche `/tools/:slug` programmatic pages, 12 blog posts, 200.html, 404.html.
    - Each route saves as `<path>/index.html` containing full rendered DOM, `<h1>`, `<title>`, JSON-LD blocks — Googlebot + AI bots see content on first byte, no hydration wait.
    - `skipThirdPartyRequests: true` blocks `/api/track/visit` and other backend calls during render so output is deterministic + bot-safe.
    - `inlineCss: false` (react-snap's CSS inlining crashes with cross-origin `Failed to fetch`; CSS-in-bundle works fine).
    - **`/app/frontend/SEO_PRERENDER.md`** documents the setup, route list, how to enable it for prod deploys, and the trade-offs (vs. Next.js).
    - To turn on for production: change the Emergent deploy build command from `yarn build` → `yarn build:seo`.

- 2026-02-26 (part 19) **🔥 Real Trend Engine + A/B Hook Lab backends**
  - **Trend Engine** (existing `routes/trends.py` enhanced):
    - First tries `_scrape_tiktok_creative_center()` for live TikTok Creative Center data.
    - When scrape fails (blocked / shape change), new `_llm_synthesise_trends()` asks GPT-4o-mini for 6 fresh viral-velocity hooks — keeps the feed feeling alive instead of falling back to the static seed pool.
    - 1-hour cache in `trend_cache` collection so we don't hammer LLMs/scrapes.
    - Frontend already wired to `GET /api/ai/trends` + `POST /api/ai/trends/refresh`. Source badge (`tiktok_creative_center` / `ai_synthesised` / `fallback`) drives the "Live feed" vs "Curated baseline" pill in the UI.
  - **A/B Hook Lab** (new `routes/ab_lab.py`):
    - `POST /api/ai/ab-variations` body `{seed, platform, count}` → returns 5 hook variants, each with `text`, `score` (0-100), and a structured `breakdown` across 5 viral-hook axes (curiosity_gap / specificity / pattern_interrupt / emotional_charge / brevity, each 0-20). Plus a 1-sentence `why` explaining the score.
    - LLM does scoring in the same call as generation — so the score is the model's honest assessment, not a fake client-side hash. Sorted high→low.
    - Counts against the user's monthly AI cap. Gated to Growth+ via new `assert_has_feature` helper (returns 402 `feature_not_in_plan` for Free/Starter).
  - **Frontend (`Studio.jsx` A/B Lab tab)**: now POSTs to `/api/ai/ab-variations`, renders the breakdown as colored pills under each variant + the LLM's reasoning in italic. Layout switched from horizontal to vertical to fit the new metadata.
  - **`assert_has_feature()`** helper added to `routes/plans.py` — single source of truth for feature-flag gating, returns the same 402 structured error shape as the AI cap so the existing `usePaywallHandler` frontend hook handles it for free.
  - **10 new pytest cases** (`tests/test_trends_and_ablab.py`): auth-required, Free/Starter blocked with 402 + `feature_locked` code, Growth returns trends, cache persists between calls, A/B Lab returns 5 variants with full breakdown, sorted by score, increments AI quota counter, rejects empty seeds. Suite: **97/97 pass** (one flake under load due to LLM rate-limit, passes in isolation).

- 2026-02-26 (part 18) **🎁 Comped-user ribbon on dashboard**
  - When `usage.comped === true` (set via the new admin plan endpoint), the Overview billing strip now shows:
    - Gift icon (emerald) instead of `CreditCard`/`CheckCircle2`.
    - Inline pill **"✦ Comped by CortexViral"** next to the plan label (`data-testid="comped-ribbon"`).
    - Friendly subtitle: *"Gifted by the CortexViral team — enjoy! No card on file, no renewal."*
    - Right-side CTA is replaced with passive *"No action needed ✨"* (no Upgrade / Manage-billing buttons that would confuse the user).
    - Annual-upsell banner is suppressed for comped users (they're not on Stripe).
    - Trial / Past-due pills are also suppressed when comped (irrelevant).
  - Reduces support-ticket noise ("why am I on Growth?"), and builds goodwill — comped creators tend to publicly thank the brand, which is organic marketing.
  - P3 Next.js migration **deferred** per user direction. Current `react-helmet-async` + JSON-LD is good enough until there's evidence of indexing problems; revisit later with `react-snap` if needed.

- 2026-02-26 (part 17) **🛡️ Admin plan-tier override + comped users**
  - **Admin login verified** — `GET /api/admin/me` returns `is_admin: true` for the allow-listed email. `ADMIN_EMAILS=williams342@gmail.com` is the source of truth; promote/demote also flips the flag at runtime.
  - **New endpoint `POST /api/admin/users/{user_id}/plan`** — body `{plan, comped, reason}`. Validates plan against `ENTITLEMENTS`, persists `plan`, `comped`, `comped_by`, `comped_reason`, `comped_at`, and writes an audit-log entry (`action: "set_user_plan"`).
  - **Comped immunity**:
    - `routes/plans.py::_get_plan` no longer downgrades comped users to free when `subscription_status == "past_due"`.
    - `routes/billing.py::_apply_plan_to_user` (used by Stripe webhook + checkout-status poll) writes everything **except** `plan` for comped users — so a customer-portal cancellation or a `customer.subscription.updated` event can't yank entitlements away from a manually-comped influencer.
  - **Frontend (`AdminUsers.jsx`)**: new "Plan" column with an inline tier `<select>` (Free / Starter / Growth / Agency, plus a legacy `pro`/`scale` option that shows automatically when a user is on the old tier) and a pill-style "Comped / Not Comped" toggle with a `Gift` icon. Both wired to the same endpoint. Toast confirms each change. Plan + comped status are now returned by `GET /api/admin/users`.
  - **`GET /api/billing/usage`** now includes a `comped: bool` field — useful for future frontend badging ("Plan: Growth · Comped").
  - **8 new pytest cases** (`tests/test_admin_plan_override.py`): auth required, unknown plan rejected (422 via `Literal`), 404 on unknown user, full set+verify+entitlements roundtrip, un-comp clears metadata, audit-log entry recorded, comped+past_due keeps plan, uncomped+past_due falls back to free. Suite: **87/87 pass.**

- 2026-02-26 (part 16) **🔘 Navbar CTA fix — auth-aware fallback**
  - **Root cause**: `Privacy.jsx`, `Terms.jsx`, and `Sitemap.jsx` were each mounting `CVNavbar` with `onGetStarted={() => {}}` (an empty no-op), so the prominent **"Start Growing"** CTA in the top-right navbar was dead on those three pages — visitors clicking it saw no feedback at all. The literal "Login" text button on the same pages worked, but `Start Growing` is the dominant CTA and users tend to click that.
  - **Fix** (`components/cv/CVNavbar.jsx`): `onGetStarted` is now optional. New `handleCTA()` falls back to `user ? navigate('/dashboard') : login()` when the prop is missing or non-function. The desktop CTA `onClick` was rewired from `onGetStarted` → `handleCTA`. Mobile menu was already correct (uses inline `login()` call).
  - Removed the no-op `onGetStarted={() => {}}` from Privacy / Terms / Sitemap so the new fallback kicks in.
  - **Verified via Playwright**: `/privacy`, `/terms`, `/sitemap` all now redirect "Start Growing" to `https://auth.emergentagent.com/?redirect=...`. Regression-tested: landing-page "Login" still routes to auth, landing-page "Start Growing" still opens the "Choose Your Specialist" modal. 5/5 scenarios pass.

- 2026-02-26 (this session — part 15) **✨ Price anchor + Per-feature gating UI**
  - **Growth price anchor**: `Pricing.jsx` Growth tier now shows `~~$59~~ $39` (monthly) and `~~$49~~ $33` (annual /mo billed annually) with an inline `✦ Early creator price` emerald badge. Anchor scales with the billing toggle. Subtle scarcity framing without lying about a sale.
  - **`FeatureLock` component** (`components/FeatureLock.jsx`): wraps any feature surface. When locked, renders the underlying UI blurred + grayscale behind a glassmorphic "UNLOCKS ON `<TIER>`" card with feature name, blurb, and direct "Upgrade to Growth →" CTA pointing at `/pricing`.
  - **Two new Studio tabs** gated to Growth+:
    - **Trend Engine** — live viral-velocity feed across TikTok/Reels/Shorts. Shows 6 trending hashtags with velocity scores (92/88/84/79/76/71), platform badges, sample hooks, copy-to-clipboard buttons. Visible-when-unlocked, blur-overlaid-when-locked.
    - **A/B Hook Lab** — drop a hook idea, generates 5 scored variations (95→70), ship the highest-stopping version. Uses existing `/api/ai/generate-post` endpoint (counts against monthly cap), client-side scores the variants.
  - Tab pills show 🔒 lock icon when the user lacks the feature (`requiresFeature` config).
  - Studio polls `/billing/usage` and stores `features` dict (trend_engine, ab_variations, batch_generation, api_access, multi_workspace) — refreshes after each generation so unlocking after upgrade is instant.

- 2026-02-26 (part 14) **🎯 4-Tier Pricing Rework + Admin Analytics + Next.js Plan**
  - **Backend plan catalogue** completely restructured. `PLANS` now holds:
    - **Starter** — $15/mo or $150/yr — 30 generations/month, 2 channels.
    - **Growth** — $39/mo or $390/yr — unlimited generations, unlimited channels, trend engine + A/B variations enabled.
    - **Agency** — $99/mo or $990/yr — everything in Growth + batch generation + multi-workspace + API access.
    - Free tier (no Stripe product) — 20 generations/month (≈5/week), 1 channel (TikTok only).
    - Legacy `pro`/`scale` entitlements kept for backwards-compat (any existing subscribers continue working).
  - **Stripe**: 3 new products + 6 new prices auto-provisioned on startup (cached in `stripe_products` collection). Old `pro`/`scale` products remain in Stripe (no impact).
  - **Entitlements** include feature-flag dict (`trend_engine`, `ab_variations`, `batch_generation`, `api_access`, `multi_workspace`) exposed via `/billing/usage` so frontend can gate features per-tier.
  - **Full Pricing page rewrite** (`Pricing.jsx`):
    - **Hero**: "Create Viral Content That Actually Grows Your Audience" + Start Free / View Plans dual CTA + trust micro.
    - **Value strip**: 4 ✓ statements ("Built for virality, not generic AI writing", etc.) in a glass card.
    - **4-tier pricing cards** with billing toggle (Monthly / Annual + "2 mo free" badge). Each card has icon, name, blurb, price, CTA (live Stripe Checkout), micro-copy, feature list, and Free tier shows exclusions in red strikethrough.
    - **Feature comparison table** — 11 features × 4 tiers, with Growth column highlighted.
    - **"Why Free Isn't Enough" section** — bold reality check with 4 growth requirements.
    - **Conversion section** with Wand2 icon + Start Free Today CTA.
    - **FAQ** — 7 SEO-friendly questions covering free tier, trial, cancellation, virality, audience.
    - **Final CTA** — large branded closing section with dual CTAs.
  - **Overview banner** updated: dynamic plan label (Starter/Growth/Agency/Pro/Scale), correct annual savings per tier ($30 / $78 / $198), Free description updated.
  - **Admin AI-usage analytics** (P2):
    - New `GET /api/admin/ai-usage?months=6&limit=20` — returns global_by_month sparkline, top_users (current month), breakdown_by_kind, totals (this month + last N months).
    - `/admin/stats` now includes subscription distribution: `users_free`, `users_starter`, `users_growth`, `users_agency`, `users_legacy`, `trialing_subs`, `past_due_subs`.
    - `AdminOverview.jsx` now renders: subscription distribution row (4 tiles + 3 secondary), AI-usage card with **6-month bar chart sparkline**, breakdown-by-kind list, top-users table.
  - **Next.js migration (P3)** deferred — see Roadmap below for the concrete plan.
  - **12 new/updated pytest cases** (`test_billing.py` updated to new tiers, `test_plans.py` updated to Free=1 channel, `test_admin_ai_usage.py` new). Suite: **79/79 pass.**

- 2026-02-26 (part 13) **🛡️ Plan-gating + Annual upsell + Login fix**
  - **Plan-gating** (P1):
    - New `routes/plans.py` (130 lines) — single source of truth for entitlements (`ENTITLEMENTS` dict: Free=20 AI/mo+2 channels, Pro=unlimited+10 channels, Scale=unlimited+unlimited).
    - Usage counters stored per-month on `users.usage.YYYY-MM.ai_generations` — auto-resets on the 1st of each month with no cron needed.
    - `assert_can_generate_ai()` → raises **HTTP 402 Payment Required** with structured `{code, message, plan, used, limit}` when cap hit.
    - `assert_can_connect_channel()` → same pattern for channels.
    - `record_ai_generation(user_id, kind)` — `$inc` counter atomically.
    - Past-due subscribers auto-downgrade to free until Stripe recovers.
    - Wired into all **9 AI generation endpoints** (`/ai/generate-post`, `/seo-review`, `/site-scan`, `/insights`, `/generate-newsletter`, `/generate-content`, `/generate-update`, `/generate-video-script`, `/multi-post`) — single shared `_gated_user(request)` helper does auth + cap-check in one call.
    - Wired into `POST /api/channels/connect` — but with reconnect-bypass: if the channel was previously connected, reconnecting it doesn't count against the cap.
    - New `GET /api/billing/usage` (lightweight, frontend polls this often).
    - `/billing/me` now embeds the full usage block.
  - **Frontend**:
    - New `components/UsageMeter.jsx` — progress bar that turns amber at 80% and red at 100%, with inline "Upgrade" CTA. Two modes: full card or compact strip. Shows "Pro · Unlimited" badge for paid plans.
    - New `hooks/use-paywall.js` — `usePaywallHandler()` returns a function that detects 402 responses, shows the appropriate toast, and redirects to `/pricing` after 1.2s.
    - Wired into all 5 Studio tabs (Newsletter / Blog / Update / Video / Multi) and Channels page. Each tab also calls `onGenerated()` after success to live-refresh the meter.
    - Overview page now has a `<UsageMeter />` strip below the stat tiles.
  - **Annual upsell banner** (P2):
    - Renders on Overview ONLY for monthly subscribers (`billing_interval === 'month'`) on Pro or Scale (not on past-due).
    - Shows specific savings: "$58/yr saved" for Pro, "$198/yr saved" for Scale.
    - "Switch to annual" button opens the Stripe Customer Portal where users can swap their subscription's price ID.
    - `data-testid="annual-upsell-banner"`.
  - **Login button fix**:
    - `CVNavbar` now imports `useAuth` and calls `login()` instead of `navigate('/dashboard')`. Clicking Login redirects to `https://auth.emergentagent.com/?redirect=...` (the proper Emergent Google Auth flow).
    - When logged in, the button auto-swaps to "Dashboard" with a `LayoutDashboard` icon.
    - Mobile menu mirrors the same logic.
  - **7 new pytest cases** (`tests/test_plans.py`) — usage endpoint, AI cap blocking, channel cap blocking, reconnect-bypass, Pro plan bypasses caps. Suite: **74/74 pass.**

- 2026-02-26 (part 12) **💳 Stripe subscription billing (test mode)**
  - New `routes/billing.py` (450 lines):
    - **Server-side `PLANS` catalogue** — Pro $29/mo or $290/yr, Scale $99/mo or $990/yr, 14-day trial on both. Frontend can't manipulate prices.
    - **Auto-provisioning**: `ensure_stripe_products()` runs on startup and creates Stripe Products + monthly+annual recurring Prices if missing. Caches `price_id`s in `stripe_products` collection so we never recreate. Successfully created in user's Stripe account: `prod_UZtnNi…` (Pro), `prod_UZto1u…` (Scale) + 4 price IDs.
    - **`POST /api/billing/checkout-session`** — body `{plan, interval, origin_url}` → returns live Stripe Checkout URL (`https://checkout.stripe.com/c/pay/cs_test_...`). Mode `subscription`, 14-day trial, promotion codes enabled. Sets `client_reference_id = user_id` + metadata for webhook reconciliation.
    - **`POST /api/billing/portal-session`** — returns Stripe Customer Portal URL for cancel/upgrade/update-card.
    - **`POST /api/webhook/stripe`** — registered on `@app.post` (not `@api`) for clean `/api/webhook/stripe` path. Verifies signature when `STRIPE_WEBHOOK_SECRET` is set; warns loudly in dev. Handles: `checkout.session.completed`, `customer.subscription.created/updated/deleted`, `invoice.payment_failed`.
    - **`GET /api/billing/me`** — current user's plan, subscription_status, current_period_end, billing_interval, publishable_key.
    - **`GET /api/billing/checkout/status/{session_id}`** — polled from frontend after checkout return; idempotently flips user's plan if Stripe says paid.
    - **`GET /api/billing/config`** — public endpoint with publishable key + plan price metadata (safe to expose).
  - **`_apply_plan_to_user()`** helper — updates users collection with `plan`, `billing_interval`, `subscription_id`, `subscription_status`, `current_period_end`. Called from both webhook and status-poll for idempotent dual-write.
  - **MongoDB collections added**: `stripe_products` (cached price IDs), `payment_transactions` (audit log of every checkout session).
  - **Frontend (`Pricing.jsx`)**:
    - CTAs now POST to `/api/billing/checkout-session` and redirect to Stripe Checkout.
    - Monthly/Annual toggle controls the `interval` param. Pro: $29/$24/mo; Scale: $99/$83/mo (annual = $290/$990 ÷ 12).
    - Loading state per-tier (only for paid plans — Free goes straight to `/dashboard`).
    - 401 → toast "Please sign in first" + redirect.
  - **Frontend (`Overview.jsx`)**:
    - Billing strip at top showing current plan + Trial / Past-due badge + "Upgrade" or "Manage billing" CTA.
    - Post-Stripe-return handler — when `?billing=success&session_id=...` is on the URL, polls `/billing/checkout/status/{id}` up to 8 × 1.5s; flips UI to new plan + shows "Welcome to Pro!" toast.
  - **`.env`** — `STRIPE_SECRET_KEY` + `STRIPE_PUBLISHABLE_KEY` (user-provided test keys), `STRIPE_WEBHOOK_SECRET` (empty — user must add after creating webhook endpoint in Stripe Dashboard). Frontend gets `REACT_APP_STRIPE_PUBLISHABLE_KEY`.
  - **9 new pytest cases** (`tests/test_billing.py`) — `config` public, `me` auth-required, plan/interval validation, real Stripe URL generation, webhook empty-body handling. Suite: **67/67 pass.**
  - **Verified live**: a real `cs_test_b1NA…` Checkout Session was created end-to-end against user's Stripe account. Live `checkout.stripe.com` URL responds with the proper Pro $29/mo Checkout page.
  - **What you still need to do** (one-time setup in Stripe Dashboard):
    1. **Webhook**: Dashboard → Developers → Webhooks → Add endpoint `https://cortexviral.com/api/webhook/stripe` → select events: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed` → copy signing secret → paste into `STRIPE_WEBHOOK_SECRET` in `/app/backend/.env`.
    2. **Customer Portal**: Dashboard → Settings → Billing → Customer portal → activate it (one-click).
    3. **Switch to live mode keys** when ready for production: replace `sk_test_…` and `pk_test_…` with the live versions in `.env` + frontend `.env`.

- 2026-02-26 (part 11) **🎵 TikTok OAuth + Content Posting scaffold**
  - New `routes/oauth_tiktok.py` mirroring the LinkedIn pattern with TikTok-specific quirks:
    - `GET /api/oauth/tiktok/status` (configured/connected check)
    - `GET /api/oauth/tiktok/start` (returns TikTok **v2** authorize URL with random state, comma-separated scopes)
    - `GET /api/oauth/tiktok/callback` (exchanges code → access_token + refresh_token + open_id, persists `tiktok_connections` doc, redirects to `/dashboard/channels?tiktok=connected`)
    - `DELETE /api/oauth/tiktok` (best-effort token revoke + local cleanup)
    - `GET /api/oauth/tiktok/publish-status?publish_id=...` (Content Posting API status poll)
    - `_refresh_tiktok_token()` (auto-refreshes when access token < 2 min from expiry)
    - `publish_to_tiktok(user_id, text, media_url)` — Direct-Post via Content Posting API using **PULL_FROM_URL** (TikTok requires video; returns `tiktok_requires_video_media_url` reason if `media_url` is absent)
  - **Scheduler hook**: `_publish_due_posts_now()` now dispatches to TikTok for any post with `tiktok` in platforms.
  - **Immediate-publish hook**: `POST /api/channels/publish` also dispatches to TikTok when not scheduled.
  - **Frontend** (Channels page): adds TikTok status fetch, real-OAuth toggle when `tiktokOAuth.configured`, `data-testid="tiktok-live-oauth-badge"`, and `?tiktok=connected|denied` query handler. Multi-platform live OAuth label adapts.
  - **`.env` scaffolding** — `TIKTOK_CLIENT_KEY` + `TIKTOK_CLIENT_SECRET` keys added (blank values). NOTE: TikTok uses `client_key`, not `client_id`.
  - **9 new pytest cases** (`tests/test_tiktok_oauth.py`) — unconfigured 503, missing-code 400, denied-error 302 redirect, bad-state rejection, auth-required, no-side-effects on non-TikTok publish, graceful failure when not connected. Suite: **58/58 pass.**
  - **Ready for credentials**: register a TikTok Developer app at https://developers.tiktok.com/apps → add **Login Kit** + **Content Posting API** products → request `user.info.basic` + `video.publish` scopes → redirect URI `https://cortexviral.com/api/oauth/tiktok/callback` → verify URL prefix of any media-hosting domain → paste client_key + client_secret into `/app/backend/.env`.

- 2026-02-26 (part 10) **🔗 SEO Phase 2 (internal linking + video sitemap)**
  - **`CVBreadcrumbs.jsx`** — reusable breadcrumb component (`data-testid="cv-breadcrumbs"`, home icon link, current-page aria attr).
  - **`buildBreadcrumbSchema()`** helper added to `CVSeo.jsx`; `<CVSeo schema>` now accepts an array of schemas (multi-script JSON-LD).
  - Breadcrumbs + `BreadcrumbList` JSON-LD wired into: `/privacy`, `/terms`, `/pricing`, `/sitemap`, `/blog`, `/blog/:slug`, `/tools/:slug`, all 5 keyword landing pages.
  - **`CVLegalLayout.jsx`** — new 2-column legal page layout with sticky TOC sidebar. Privacy (10 sections) and Terms (12 sections) rewritten to use it; anchor-link jumping works via `scroll-mt-28`.
  - **Cross-linking** for topical authority:
    - Programmatic niche pages now show "Deep dives on `<cluster>`" — 3 blog cards from the mapped cluster (`data-testid="cv-niche-related-posts"`).
    - Landing pages now show "Try it for your niche" — 8 cross-links to programmatic combos (`data-testid="cv-landing-by-niche"`, via `PATH_TO_PROG_TOOL` map in `CVLandingPage.jsx`).
  - **Video sitemap infrastructure** (backend `routes/seo.py`):
    - Added `xmlns:video="http://www.google.com/schemas/sitemap-video/1.1"` namespace to `<urlset>`.
    - New `BLOG_VIDEOS` registry (empty by default — populated when real videos are embedded).
    - `_video_xml_block()` helper safely escapes title/description and emits `<video:thumbnail_loc>`, `<video:player_loc allow_embed="yes">`, `<video:duration>`, etc.
    - Blog post page now iframe-embeds `post.videos[*].player_loc` when populated.
  - **5 new pytest cases** (`tests/test_seo_v3.py`) — video namespace assertion, empty-by-default invariant, `_video_xml_block` rendering, legal-route sitemap presence, well-formed `<url>` XML. Suite: **49/49 pass.**
  - **Bugfix during testing**: Pricing.jsx originally referenced `buildBreadcrumbSchema` + `CVBreadcrumbs` without importing them, crashing `/pricing` with a runtime overlay. Both imports added; verified rendering.
  - BlogIndex was missing breadcrumbs after first pass — fixed in this iteration.

- 2026-02-25 (part 9) **🔗 LinkedIn OAuth scaffold**
  - New `routes/oauth_linkedin.py` — full OAuth 2.0 + posting integration:
    - `GET /api/oauth/linkedin/status` (configured/connected check)
    - `GET /api/oauth/linkedin/start` (returns LinkedIn authorize URL with random state)
    - `GET /api/oauth/linkedin/callback` (exchanges code → access_token, fetches OIDC userinfo, persists `linkedin_connections` document, redirects to `/dashboard/channels?linkedin=connected`)
    - `DELETE /api/oauth/linkedin` (disconnect)
    - `publish_to_linkedin(user_id, text)` helper for live posting via `POST /rest/posts` with LinkedIn-Version header
  - **Scheduler hook**: `_publish_due_posts_now()` now dispatches to LinkedIn for any post with `linkedin` in platforms and writes the dispatch result to `posts.dispatch.linkedin`.
  - **Immediate-publish hook**: `POST /api/channels/publish` also dispatches to LinkedIn when not scheduled.
  - **Frontend** (Channels page): conditionally switches the LinkedIn toggle to real OAuth when configured (calls `/oauth/linkedin/start` → window.location.assign authorize URL → redirected back with `?linkedin=connected`). Shows a "LinkedIn live OAuth" pulse badge when credentials are set.
  - **`.env` scaffolding** — `LINKEDIN_CLIENT_ID` + `LINKEDIN_CLIENT_SECRET` keys added (blank values). Public site URL set to `https://cortexviral.com`.
  - **6 new pytest cases** (`test_linkedin_oauth.py`) — unconfigured 503, missing-code 400, bad-state rejection, auth-required, non-LinkedIn publish unaffected.
  - Ready for credentials: user just needs to register a LinkedIn Developer app, request "Sign in with LinkedIn using OpenID Connect" + "Share on LinkedIn" products, add redirect URI `https://cortexviral.com/api/oauth/linkedin/callback`, and paste Client ID + Client Secret into `/app/backend/.env`.

- 2026-02-25 (this session — part 8) **🧹 Routes cleanup**
  - All 13 `routes/*.py` files refreshed: per-module **docstring**, **minimal imports** (each file imports only what it uses).
  - `ai.py` PEP-8 fixed (httpx/re/json on separate lines).
  - `activity.py` E741 fix (renamed `l` → `lead`).
  - Cross-module imports explicit (`channels.py` ← `routes.ai._llm`, `health.py` ← `routes.scheduler._publish_due_posts_now`).
  - Backend now **lint-clean**: `ruff` reports 0 errors across `core.py`, `models.py`, `deps.py`, `server.py`, all of `routes/*`, all of `tests/*`.
  - Pytest still **38/38 pass**.

- 2026-02-25 (this session — part 7) **🧱 Backend refactor + 📚 Blog expansion**
  - **Refactored `server.py`**: 1701 → **49 lines** (97% reduction). Logic split into:
    - `core.py` (Mongo client, env, logger, FastAPI app + router) — 33 lines
    - `models.py` (all Pydantic models) — 162 lines
    - `deps.py` (auth, admin, audit log dependencies) — 71 lines
    - `routes/` (13 domain modules: `auth`, `leads`, `ai`, `channels`, `performance`, `activity`, `dashboard`, `support`, `admin`, `broadcasts`, `scheduler`, `health`, `seo`)
  - **Cross-module reuse**: `channels.py` imports `_llm` + `LlmChat`/`UserMessage` from `ai.py` (single LLM client init).
  - **Blog cluster expanded from 3 → 15 posts** across 3 keyword clusters:
    - **Viral content** (6 posts): What Makes Content Go Viral, Viral TikTok Hooks, Instagram Captions That Convert, TikTok Algorithm 2026, Short-Form Video Scripts, Going Viral as a Small Account.
    - **AI marketing tools** (5 posts): AI Tools for Viral Content, Best AI Tools for Creators 2026, How AI Is Changing Content Marketing, Automating Social Media Growth, AI Content Platforms vs ChatGPT.
    - **Social media growth** (4 posts): Best Time to Post on Instagram, Grow on LinkedIn as a Founder, Content Calendar Template, Skincare Brand 0-to-100K Case Study.
  - **Blog index** now has a cluster-filter pill row + per-cluster post counts; "Keep reading" prefers same-cluster posts for stronger topical authority signals.
  - **Sitemap grew 44 → 56 URLs** (12 core + 32 programmatic + 12 new blog).
  - **2 new pytest files** (`test_blog_seo.py` — 2 cases). Full suite: **38/38 pass.**
  - Performance.py `range` → `period` shadowing fix preserved in refactor.

- 2026-02-25 (this session — part 6) **📈 Pricing + Programmatic SEO + LCP**
  - **New `/pricing` page** with 3 tiers (Free / Pro $29 / Scale $99), Pro highlighted with violet glow, monthly/annual billing toggle (10/12 multiplier with rounding), pricing-specific FAQ, JSON-LD SoftwareApplication + FAQPage schema.
  - **Programmatic SEO route `/tools/:slug`** — 4 tools × 8 niches = **32 long-tail landing pages** auto-generated from `/app/frontend/src/pages/programmatic/data.js`. Each page renders niche-tailored H1, pain points, sample hook, AI-agent CTA, and 6 internal links (3 related-niche + 3 cross-sell). Invalid slugs `<Navigate>` to /.
  - **Sitemap expanded to 44 URLs** (12 core + 32 programmatic), now uses production domain `cortexviral.com`, adds `xmlns:image` extension with logo `<image:image>` per URL.
  - **robots.txt** updated to production domain + dual `Sitemap:` directives (root + /api/seo/sitemap.xml).
  - **LCP optimisations**: preload `/cortex-logo.png` with `fetchpriority=high` in `<head>`, preload Space Grotesk + Inter critical weights, dns-prefetch backend, `fetchPriority`/`loading` props on CVLogo for hero vs below-the-fold variants.
  - **Index.html static title** keyword-optimised to match Helmet output (SEO consistency).
  - **CVSeo SITE constant** migrated to `https://cortexviral.com` (production deploy live as of this session).
  - **Pytest**: 8 new SEO-v2 cases (`test_seo_v2.py`). Full suite **36/36 pass**.
  - **Frontend testing agent: 100% pass** after self-fixed React `fetchPriority` casing.

- 2026-02-25 (this session — part 5) **🔍 SEO Phase-1 overhaul**
  - **Keyword strategy locked**: primary "AI viral content generator" + secondary "viral marketing automation tool" / "AI content growth platform".
  - **Homepage SEO**: title → `AI Viral Content Generator for Fast Social Media Growth | CortexViral`, H1 → `Create Viral Content Using AI in Minutes.`, 5 keyword-mapped H2s, hero copy bolds primary keyword, meta-description optimised.
  - **5 dedicated SEO landing pages** (one keyword intent each):
    - `/ai-tiktok-post-generator`
    - `/viral-content-ideas-generator`
    - `/instagram-caption-ai-generator`
    - `/short-form-video-ideas-ai`
    - `/content-automation-tool`
  - **JSON-LD schema**: Organization + SoftwareApplication + FAQPage emitted as a single ld+json array on homepage; per-page schema on each landing; Article schema per blog post.
  - **Blog skeleton at `/blog`** with 3 starter articles (What Makes Content Go Viral, Viral TikTok Hooks That Work, Best AI Tools for Viral Content). Internal links flow Blog ↔ Landing pages.
  - **`react-helmet-async`** wired at App root; `CVSeo` component handles per-route title/meta/canonical/og/twitter/JSON-LD.
  - **Backend**: `/sitemap.xml`, `/robots.txt` and `/api/seo/*` aliases. Sitemap covers homepage + 5 landings + agents + blog index + 3 posts (11 URLs). Robots disallows /api, /dashboard, /admin, /auth.
  - **Rebuilt CVFooter** with 4-column nav: AI tools (5 landing links) / Company (Agents, Blog, Dashboard) / Legal — strong internal-linking graph.
  - **Homepage FAQ** with 6 question pairs and a11y-compliant `aria-expanded` toggles.
  - **Pytest**: 15 new SEO regression cases (`test_seo.py`) — total 28/28 pass.
  - **Frontend testing agent: 100% pass** after testing-agent's own `&amp;` entity fix in short-form H1.
  - Rebuilt `DashboardLayout.jsx` with dark glass sidebar, gradient-active nav items, ambient aurora backdrop, wordmark "Cortex**Viral**" with gradient on "Viral", glow under active items, and dark user-profile footer.
  - Added ~80 lines of scoped CSS in `index.css` under `.cv-dash-scope { … }` that re-skin existing legacy markup (`bg-white`, `border-neutral-200/70`, `text-neutral-*`, `bg-neutral-*`, pastel `from-*-100` gradients, `bg-#1B7BFF` brand classes, `input/textarea/combobox`) to dark glass — meaning ALL 14 dashboard pages + admin pages got the new look with **zero per-page edits**.
  - Verified across Overview, Marketing Calendar, Content Studio, Compose, Posts, AI Insights, SEO, Site Scan, Help, Admin Overview, and landing untouched. **100% frontend pass.**

- 2026-02-25 (this session — part 3) **🎨 Landing & /agents brand overhaul**
  - Full neural dark landing rebuild (CVHero, CVNeuralEngine, CVPipeline, CVResults, CVCTAFooter, CVFooter, CVNavbar, CVBackdrop, CVLogo).
  - New `/agents` sub-page with 4 AI agent cards (Nova/Sam/Kai/Angela) — direct chat.
  - New logo asset `/cortex-logo.png` used as favicon + nav.
  - Framer Motion + CSS keyframe animations (no Three.js).

- 2026-02-25 (this session — part 2) **Background scheduler**
  - APScheduler in-process AsyncIOScheduler with Mongo TTL lock (`scheduler_locks`), promotes `scheduled → published` every 60s.
  - Admin debug endpoint `POST /api/admin/scheduler/run-once`.
  - `DISABLE_SCHEDULER=true` kill-switch.
  - 4 new pytest cases in `/app/backend/tests/test_scheduler.py` (total 13/13 pass).
- 2026-02-24 (this session — part 1)
  - **AI optimal time button on Compose** — visible only when exactly one channel checkbox is selected; auto-fills datetime-local and shows violet meta line, cleared on manual edit.
  - **Bulk lasso multi-select on Marketing Calendar** — toggle "Bulk select" → drag rectangle (Shift adds), floating bottom action bar with **−1w / −1d / +1d / +1w / Cancel / Clear**, runs PATCH/DELETE in parallel.
  - Backend cleanup: `performance/*` endpoints now use `period: str = Query("24h", alias="range")` (no more builtin shadowing) — public URL signature unchanged.
  - Backend regression suite added: `/app/backend/tests/test_scheduling_and_optimal.py` (9 tests, all pass).
- Prior sessions
  - Pixel-perfect landing-page clone, rebranded Automatex → CortexViral
  - Emergent Google Auth
  - AI Content Studio (5 generators) + SEO Review + Site Scan
  - Channels catalog (38+ platforms, MOCKED OAuth)
  - Compose & Publish (single + scheduled post via `scheduled_at`)
  - Marketing Calendar week/month view + per-post drag-to-reschedule + AI optimal slot badges
  - Activity feed (`/api/activity`) and Performance analytics (mocked synthetic data)
  - Admin: stats, users (search/promote/demote/suspend/unsuspend/impersonate/delete), audit log, broadcasts, support tickets
  - Help Center with AI chat, FAQ, ticket flow

## Mocked features (explicitly)
- Social-media OAuth connect/disconnect (fake handle)
- `POST /api/channels/publish` writes locally only — does NOT post to live external APIs
- `/api/performance/*` uses synthetic data via seeded RNG

## Roadmap

### P0 — none open

### P1 — **Real OAuth + live publishing** (blocked: needs user-supplied developer credentials)
Pipeline: when a post is promoted to `published` by the scheduler (or by the immediate publish path), iterate its `platforms[]` and dispatch to each platform's OAuth-authenticated API. Per-platform handler files should live in `/app/backend/integrations/{linkedin,x,instagram,facebook,tiktok}.py`. Token storage collection `{platform}_connections` keyed by `user_id`.
- **LinkedIn FIRST** — playbook obtained 2026-02-25; needs `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, redirect URIs registered. Uses `w_member_social` + OIDC scopes. UGC Post API + Images API.
- X / Twitter — basic tier ~$100/mo, OAuth 2.0 PKCE.
- Meta (Facebook + Instagram) — slowest review.
- TikTok — manual approval.
- Threads — via Meta Graph.

### P1 — Per-post analytics
Strictly depends on OAuth per platform. Each platform has its own metrics endpoint (LinkedIn UGC, X v2 tweet metrics, Meta Insights, TikTok Insights). Implement per platform as OAuth lands.

### P2
- Refactor `server.py` (~1500 lines) into `/app/backend/routes/` and `/app/backend/models/`
- Drag from one post to multiple cells (multi-day duplicate)
- Calendar month view: collapse all platforms into a single row-per-day with stacked dots
- Email digest for admin broadcasts (Resend integration)
- Stripe billing (Pro tier unlocks live posting + higher AI quotas)
- "Repeat weekly" toggle when scheduling

## Key API endpoints
- `GET /api/auth/me` · `POST /api/auth/logout`
- `POST /api/ai/{generate-post, generate-newsletter, generate-content, generate-update, generate-video-script, multi-post, optimal-times, seo-review, site-scan, insights}`
- `POST /api/channels/publish` (accepts optional `scheduled_at` ISO datetime)
- `GET /api/posts/scheduled?start=&end=` · `PATCH /api/posts/scheduled/{id}` · `DELETE /api/posts/scheduled/{id}`
- `GET /api/performance/{overview,sources,pages}?range=24h|48h|7d|30d|60d|90d|year|lastyear`
- `GET /api/activity?limit=30`
- `GET /api/channels` · `POST /api/channels/connect` · `DELETE /api/channels/{platform}`
- Admin: `/api/admin/{stats,users,broadcasts,audit-log,tickets,...}`
- Support: `/api/support/{faq,chat,tickets}`

## Important Constants
- Admin allow-list email: `williams342@gmail.com`
- Test user: `test@automatex.dev` (Bearer `test_session_1779636592168`) — see `/app/memory/test_credentials.md`
- LLM model: `gpt-5` via `EMERGENT_LLM_KEY`
