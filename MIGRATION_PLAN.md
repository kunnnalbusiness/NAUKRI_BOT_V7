# MIGRATION PLAN: Full-Stack Architecture (FastAPI + React)

## Executive Summary
This document outlines the complete architectural migration of the **Autonomous Job Apply Bot** from a legacy single-tier Python + Jinja2/HTML templates application into a modern, production-grade full-stack monorepo:
- **Backend:** FastAPI (Python 3.11+) with clean architectural layers (`api`, `core`, `models`, `services`, `db`), bcrypt authentication, role-based authorization, rate limiting, and MongoDB with encrypted session storage.
- **Frontend:** Vite + React + TypeScript + TailwindCSS + Shadcn Tokens + React Query + Lucide Icons + Sonner, mirroring the high-end dark-first reference design (pure black `#000000`, emerald/rose/amber/purple accents, dual mobile/desktop layouts, remote CDP screencast, responsive stat strips, export tools).

---

## 1. Inventory of Current Codebase

### Current Routes & Templates
| Path / Endpoint | Method | Current Location | Purpose |
|-----------------|--------|------------------|---------|
| `/` | GET | `web/app.py` -> `web/templates/index.html` | Legacy server-rendered monolithic dashboard with multiple modals (Sessions, Profile, Keys, Sheet, Admin, Screencast). |
| `/login` | GET | `web/app.py` -> `web/templates/login.html` | Legacy server-rendered login page. |
| `/healthz` | GET | `web/app.py` | Health check for Render container. |
| `/api/login` | POST | `web/app.py` | Authenticate user, issue signed HMAC session cookie. |
| `/api/logout` | POST | `web/app.py` | Clear session cookie. |
| `/api/status` | GET | `web/app.py` | Aggregated engine, session, quota, user settings, activity. |
| `/api/activity` | GET | `web/app.py` | Return application log items and engine state. |
| `/api/activity/clear` | POST | `web/app.py` | Clear activity feed. |
| `/api/engine/{site}/start` | POST | `web/app.py` | Start Naukri or LinkedIn worker thread. |
| `/api/engine/{site}/stop` | POST | `web/app.py` | Stop worker thread. |
| `/api/engine/reset-limit` | POST | `web/app.py` | Reset daily limit flags. |
| `/api/user/settings` | GET/POST | `web/app.py` | Get/update user custom delay (min 2s) & sheet config. |
| `/api/profile` | GET/POST | `web/app.py` | Get/update user job application profile (5 sections). |
| `/api/profile/resume` | POST | `web/app.py` | Upload PDF resume (max 5MB). |
| `/api/profile/resume/download` | GET | `web/app.py` | Stream/download uploaded resume PDF. |
| `/api/admin/users` | GET/POST | `web/app.py` | Admin-only: list users or create user. |
| `/api/admin/users/{username}` | DELETE | `web/app.py` | Admin-only: delete user. |
| `/api/keys` | GET/POST | `web/app.py` | Masked AI keys list & add key. |
| `/api/keys/{key_id}` | PUT/DELETE | `web/app.py` | Enable/disable or delete AI key. |
| `/api/keys/{key_id}/test` | POST | `web/app.py` | Verify AI key. |
| `/api/sheet` | POST | `web/app.py` | Update Google Sheet URLs. |
| `/api/sheet/test` | POST | `web/app.py` | Send test row to sheet. |
| `/api/sessions` | GET | `web/app.py` | Get Naukri/LinkedIn session status. |
| `/api/sessions/{site}/check` | POST | `web/app.py` | Headless session verification. |
| `/api/sessions/{site}` | DELETE | `web/app.py` | Remove session file. |
| `/api/sessions/cancel` | POST | `web/app.py` | Cancel active CDP screencast session. |
| `/ws/session/{site}` | WebSocket | `web/app.py` | CDP screencast stream and mouse/keyboard event forwarding. |

---

## 2. React UI Equivalents & Page Architecture

In the new React application (`frontend/src`), all modals and fragmented views are restructured into clean, accessible pages and components following the reference design:

| Legacy HTML / Modal | React Page / Component | Route | Access |
|---------------------|------------------------|-------|--------|
| `login.html` | `pages/Login.tsx` | `/login` | Public |
| `index.html` (Main View & Metric Cards) | `pages/Dashboard.tsx` | `/` | Authenticated |
| `index.html` (Live Activity Table) | `pages/LiveActivity.tsx` | `/activity` | Authenticated |
| `index.html` (`#loginModal` Screencast) | `pages/LiveBrowserView.tsx` & `components/screencast/ScreencastModal.tsx` | `/live-view` | Authenticated |
| `index.html` (Sessions Panel) | `pages/Sessions.tsx` | `/sessions` | Authenticated |
| `index.html` (`#profileModal` 5 Tabs) | `pages/MyProfile.tsx` | `/profile` | Authenticated (Non-admin or admin) |
| `index.html` (`#userSettingsModal` & `#addKeyModal` & Sheet Sync) | `pages/Settings.tsx` | `/settings` | Authenticated |
| `index.html` (`#adminUsersModal`) | `pages/AdminUsers.tsx` | `/admin/users` | Admin Only (Guarded) |

### Navigation & Layouts:
- **Desktop (md+):** Fixed topbar (`h-[50px]`) with rounded icon badge, bold title, SolanaTracker/Futures Radar style pill stats strip (`Total Applied`, `Today`, `Win Rate / Applied Rate`), live status beacon pill (`Live Stream`, `Connecting`, `Offline`), IST clock, theme toggle, AI Audit link, and profile/logout menu.
- **Desktop Nav Sidebar / Header Navigation:** Modern tab navigation across Dashboard, Activity, Live View, Sessions, Profile, Settings, and Admin (conditional).
- **Mobile (<md):** Mobile TopBar with sticky header, 4-stat compact KPI strip, AI Quick action buttons (AI Audit, Excel CSV export, PDF report), bottom navigation bar or drawer.

---

## 3. Target Monorepo Structure

```
/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   ├── users.py
│   │   │   ├── profile.py
│   │   │   ├── bot.py
│   │   │   ├── sessions.py
│   │   │   ├── activity.py
│   │   │   ├── admin.py
│   │   │   └── sheets.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   ├── logging.py
│   │   │   └── dependencies.py
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── profile.py
│   │   │   ├── settings.py
│   │   │   ├── activity.py
│   │   │   └── session.py
│   │   ├── services/
│   │   │   ├── bot_service.py
│   │   │   ├── session_manager.py
│   │   │   ├── sheets_sync.py
│   │   │   └── resume_service.py
│   │   ├── db/
│   │   │   └── mongo.py
│   │   └── main.py
│   ├── common/                  # Preserved automation engines & helper algorithms
│   ├── tests/
│   │   ├── test_auth.py
│   │   ├── test_roles.py
│   │   ├── test_isolation.py
│   │   └── test_skip_logic.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── assets/
│   │   ├── components/
│   │   │   ├── dashboard/
│   │   │   ├── layout/
│   │   │   ├── screencast/
│   │   │   └── ui/
│   │   ├── hooks/
│   │   ├── lib/
│   │   │   ├── api.ts
│   │   │   ├── utils.ts
│   │   │   └── types.ts
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── LiveActivity.tsx
│   │   │   ├── LiveBrowserView.tsx
│   │   │   ├── Sessions.tsx
│   │   │   ├── MyProfile.tsx
│   │   │   ├── Settings.tsx
│   │   │   └── AdminUsers.tsx
│   │   ├── App.tsx
│   │   ├── index.css
│   │   └── main.tsx
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── .env.example
├── render.yaml
├── Dockerfile
├── docker-entrypoint.sh
├── AGENTS.md
├── .coderabbit.yaml
├── .github/
│   └── workflows/
│       └── ci.yml
└── README.md
```

---

## 4. Key Risks & Mitigation Strategy

1. **Automation Worker Thread Isolation & State Leaks:**
   - *Risk:* Moving code to `backend/` could break relative imports or dynamic path lookups in `naukri_apply.py` and `linkedin_apply.py`.
   - *Mitigation:* Ensure `common/` paths point dynamically to `DATA_DIR` or project root. Preserve existing engine worker interfaces intact while wrapping them cleanly with `bot_service.py`.

2. **Render Ephemeral Filesystem & Session Loss:**
   - *Risk:* Render restarts web containers periodically. If sessions are only saved on disk, user has to re-login every deploy.
   - *Mitigation:* Save encrypted session cookies/state inside MongoDB collection `sessions` in addition to disk. On startup/browser launch, restore from MongoDB if file is missing.

3. **Render "Access Denied" / 403 / CORS Failures:**
   - *Risk:* Cookies blocked due to cross-site SameSite/Secure mismatch or proxy headers not trusted.
   - *Mitigation:* Enable `uvicorn --proxy-headers --forwarded-allow-ips='*'`, configure CORS origins dynamically from `FRONTEND_URL` / `ALLOWED_ORIGINS`, support Bearer token authorization in header alongside cookies, set SameSite="lax" (or "none" + secure if cross-origin).

4. **LinkedIn Datacenter IP Detection:**
   - *Risk:* LinkedIn detects Render cloud IP ranges and responds with checkpoint/403 or immediate CAPTCHA.
   - *Mitigation:* Provide both in-app CDP screencast and a **Cookie/Session JSON Import** feature allowing users to log in on their local residential IP and securely upload the session to the cloud.

5. **Role Bypass & Multi-Tenant Data Leak:**
   - *Risk:* Normal users accessing `/api/admin/*` or seeing other users' application logs.
   - *Mitigation:* Hard role checks (`require_admin`) enforced on all admin routes; all activity and profile queries strictly scoped to `request.state.user["username"]`.

---

## 5. Execution Steps
- **Step 1:** Set up backend directories and core foundation (FastAPI app, config, security, Mongo connection, logging, models).
- **Step 2:** Port and modularize all API routers and services.
- **Step 3:** Scaffold and build Vite + React + TypeScript frontend with Tailwind, Lucide, Sonner, and React Query.
- **Step 4:** Implement high-precision UI matching the reference design.
- **Step 5:** Implement tests for auth, roles, user isolation, and delay validation.
- **Step 6:** Configure Docker, Render blueprints, `.coderabbit.yaml`, `AGENTS.md`, and CI workflow.
- **Step 7:** Verify and test all endpoints, frontend build, and clean up legacy dead templates.
