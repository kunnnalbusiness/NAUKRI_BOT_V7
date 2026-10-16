# 🤖 AGENTS.md — Engineering & Operational Guidelines for AI Coding Agents

> **MANDATORY NOTICE FOR ALL AI CODING AGENTS (Cursor, Claude, Copilot, Antigravity, Aider, Windsurf, CodeRabbit):**
> Before reading, modifying, or creating any files in this repository, you **MUST** read and adhere to the guidelines, architectural boundaries, and safety constraints specified in this document. Never bypass these rules.

---

## 1. 🏗️ Repository Architecture & Monorepo Layout

This repository is a production-grade full-stack application structured as a clean monorepo:

```text
naukri-job/
├── backend/                   # Python 3.13 / FastAPI service
│   ├── app/
│   │   ├── api/               # FastAPI routers (auth, users, profile, bot, sessions, activity, admin, sheets)
│   │   ├── core/              # Config (pydantic-settings), security (bcrypt/fernet), logging, dependencies
│   │   ├── models/            # Pydantic schemas (user, profile, bot)
│   │   ├── services/          # Business logic: session_manager, resume_service, bot runner
│   │   ├── db/                # MongoDB Atlas client, indexes, fallback local store
│   │   └── main.py            # FastAPI ASGI entrypoint, middleware, SPA static mount
│   ├── tests/                 # Pytest test suite (auth, rbac, isolation, pacing)
│   └── requirements.txt       # Pinned backend dependencies
├── frontend/                  # Vite + React 18 + TypeScript + TailwindCSS + Shadcn Tokens
│   ├── src/
│   │   ├── components/        # Layout (TopBar, AppLayout), ScreencastCanvas, UI widgets
│   │   ├── pages/             # Dashboard, LiveActivity, LiveBrowserView, Sessions, MyProfile, Settings, AdminUsers, Login
│   │   ├── lib/               # API client, authContext, types, utils, useScrollRestoration
│   │   ├── index.css          # Dark-first pure black (#000000) design system tokens
│   │   ├── App.tsx            # Routes, Lazy components, ProtectedRoute, AdminRoute
│   │   └── main.tsx           # React DOM root mount
│   ├── package.json           # Frontend dependencies
│   ├── vite.config.ts         # Vite build configuration with proxy to port 8000
│   └── tailwind.config.js     # Tailwind theme tokens (colors, animations)
├── common/                    # Core automation utilities (key rotator, engine manager, login helper, sheets)
├── data/                      # Local persistent runtime storage (sessions, cache, resumes, store)
├── .github/workflows/ci.yml   # GitHub Actions CI (lint, backend test, frontend build)
├── .coderabbit.yaml           # Automated Code Review configuration
├── render.yaml                # Render cloud deployment specification
├── Dockerfile                 # Multi-stage production container
└── MIGRATION_PLAN.md          # Architectural migration roadmap and endpoint spec
```

---

## 2. 🛡️ Security & Zero-Trust Constraints

1. **NO SECRETS IN CODE OR LOGS:**
   - Never commit API keys, MongoDB URIs, JWT secrets, passwords, or session cookies into Git.
   - All sensitive data must be read from environment variables via `backend/app/core/config.py` (`get_settings()`).
   - Logging uses `backend/app/core/logging.py` which automatically masks passwords, tokens, connection strings, and keys via regex filters.

2. **ROLE-BASED ACCESS CONTROL (RBAC):**
   - Endpoints under `/api/admin/*` must enforce `Depends(require_admin)`. UI hiding alone is NOT sufficient.
   - Standard users must never be able to view, query, or mutate other users' profiles, resumes, settings, sessions, or application activity logs.
   - New users must start with zero counts and empty profiles.

3. **AUTHENTICATION:**
   - Passwords are encrypted with `bcrypt` (work factor 12). Plaintext passwords must never be stored.
   - Authentication supports dual-mode: `Authorization: Bearer <JWT>` header AND `session` HTTP cookie.
   - Cross-origin credentials and proxy headers (`X-Forwarded-Proto`, `X-Forwarded-For`) must be trusted behind reverse proxies (`uvicorn --proxy-headers --forwarded-allow-ips='*'`).

4. **FILE UPLOAD RESTRICTIONS:**
   - Resumes must be validated: PDF only (`application/pdf`), maximum 5 MB.
   - Filenames must be sanitized via `Path(filename).name` and stripped of path traversal characters (`../`).
   - Stored in a directory-contained location (`data/resumes/{username}_resume.pdf`).

---

## 3. 🎨 UI & Design Language Standards

All frontend contributions must adhere to the project's **Dark-First Trading Radar** design language:
- **Backgrounds:** Pure black (`#000000`), card surface (`hsl(0, 0%, 5%)` or `bg-card`), borders (`hsl(0, 0%, 15%)` or `border-border`).
- **Color Accents:** Emerald (`emerald-400`, `emerald-500/20`), Rose for errors/skips (`rose-400`), Amber for warnings/wait (`amber-400`), Purple for admin badges (`purple-400`).
- **Typography:** Sans-serif for titles, Tabular mono (`font-mono`, `.num`) for numerical metrics, timestamps, and codes.
- **Responsiveness:** Distinct Mobile (<768px) and Desktop (>=768px) layouts. Mobile uses sticky `TopBar` + compact stats strip + bottom navigation. Desktop uses a fixed `50px` header + split column layouts.
- **Micro-interactions:** Subtle hover transitions, active press (`app-press`), and a pulsing live beacon (`animate-[beacon_1.6s_ease-in-out_infinite]`) for active automation engines. No excessive blur or CPU-heavy animations.
- **Feedback:** All notifications and mutations must use `sonner` (`toast.success`, `toast.error`).

---

## 4. 🧪 Testing & Quality Assurance Commands

Before submitting or opening any PR, run the full validation suite:

```bash
# 1. Backend Lint & Typecheck
python -m ruff check backend/ common/
python -m black --check backend/ common/

# 2. Backend Unit & Integration Tests
python -m pytest backend/tests -v

# 3. Frontend Typecheck & Production Build
cd frontend
npm run build
```

---

## 5. 🚀 Deployment Principles (Render & Production)

1. **Ephemeral Disk Resilience:**
   - Render free/starter tiers do not persist disk restarts.
   - LinkedIn and Naukri sessions are symmetrically encrypted with Fernet and backed up to MongoDB Atlas in the `sessions` collection. On cold boot, sessions are restored automatically.
2. **Datacenter IP Checkpoints:**
   - If LinkedIn blocks datacenter IPs with 403 or security checkpoints, use `/api/sessions/linkedin/import` to import valid residential session cookies generated on a local machine.
3. **Headless Execution:**
   - Render runs in headless mode. Live browser viewing is provided in-app via the WebSocket Chrome DevTools Protocol (CDP) screencast canvas (`/ws/session/{site}`).
