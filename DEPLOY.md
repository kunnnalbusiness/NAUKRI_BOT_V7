# 🚀 Deployment Guide: Deploy to Render (Docker)

This guide walks you through deploying the **Naukri & LinkedIn Autonomous Apply Bot** with its Web Dashboard on Render in a single Docker container with persistent disk storage.

---

## 📋 Architecture Overview

- **One Web Service:** Combines the FastAPI control dashboard, background automation engines (Naukri Radar & Sweep + LinkedIn Easy Apply), and interactive CDP remote login screencaster.
- **Persistent Disk:** Mounted at `/data` (via `DATA_DIR=/data`) to preserve your cookies/sessions (`/data/sessions`), deduplication cache (`/data/cache`), and encrypted runtime settings (`/data/config/runtime.json`) across redeploys.
- **Remote Browser Login:** Uses Chrome DevTools Protocol (CDP) screencasting streamed directly over WebSocket to the dashboard, allowing you to log in with OTP/CAPTCHA without VNC or open ports.

---

## 🛠️ Step 1: Push Code to GitHub

Ensure your latest changes are pushed to your private GitHub repository:

```bash
git add .
git commit -m "Add Dockerfile, Render config, and Web Dashboard"
git push origin main
```

---

## ☁️ Step 2: Deploy on Render

### Option A: Using Render Blueprints (Recommended)
1. Log in to your [Render Dashboard](https://dashboard.render.com/).
2. Click **Blueprints** ➔ **New Blueprint Instance**.
3. Select your GitHub repository.
4. Render will detect `render.yaml` automatically.
5. In the environment variables prompt, enter:
   - `DASHBOARD_PASSWORD`: Choose a secure password to access your web dashboard.
   - `SECRET_KEY`: A random 32+ character string (used to sign session cookies and encrypt stored keys).
   - `MONGODB_URI`: (Optional) MongoDB Atlas connection string (`mongodb+srv://...`) for multi-user accounts, profiles & resume metadata. If left blank, falls back to local disk storage (`/data/users_store.json`).
   - `GEMINI_API_KEY`: (Optional initial key) Your Google Gemini API key.
   - `GROQ_API_KEY`: (Optional initial key) Your Groq API key.
   - `GOOGLE_SHEET_WEBHOOK_URL`: (Optional) Apps Script webhook URL for live job tracking.
   - `GOOGLE_SHEET_URL`: (Optional) Your Google Sheet link.
6. Click **Apply**.

---

### Option B: Manual Web Service Setup
1. On Render, click **New +** ➔ **Web Service**.
2. Connect your Git repository.
3. Configure the service:
   - **Name:** `naukri-apply-ai`
   - **Environment:** `Docker`
   - **Instance Type:** Starter (at least 512MB RAM recommended, 1GB ideal for Chromium).
   - **Health Check Path:** `/healthz`
4. Add Persistent Disk:
   - Go to **Disks** tab in service settings.
   - Click **Add Disk**:
     - **Name:** `bot-data`
     - **Mount Path:** `/data`
     - **Size:** `1 GB`
5. Configure Environment Variables:
   - `DATA_DIR` = `/data`
   - `HEADLESS` = `true`
   - `DASHBOARD_PASSWORD` = `<your-password>`
   - `SECRET_KEY` = `<your-random-secret>`
   - `MONGODB_URI` = `<your-mongo-uri>` (optional)
   - `GEMINI_API_KEY` = `<your-gemini-key>` (optional)
   - `GROQ_API_KEY` = `<your-groq-key>` (optional)
   - `GOOGLE_SHEET_WEBHOOK_URL` = `<your-apps-script-url>` (optional)
6. Click **Create Web Service**.

---

## 🔑 Step 3: Access Dashboard & Complete First-Time Setup

1. Open your Render Web Service URL (e.g., `https://naukri-apply-ai.onrender.com`).
2. Log in with your `DASHBOARD_PASSWORD`.
3. **Capture Login Sessions:**
   - Under **Auth Sessions**, click **Add / Replace** for Naukri or LinkedIn.
   - An interactive browser window will stream onto your screen.
   - Enter your email, password, and OTP.
   - Once your profile homepage loads, the system automatically saves your session, closes the browser, and marks the session as **Valid**.
4. **Configure API Keys:**
   - Click **+ Add Key** under AI Provider API Keys to add Gemini or Groq keys.
   - Click **Test** on any key to confirm it responds.
5. **Start Engines:**
   - Click **Start** on **Naukri (Radar + Sweep)** or **LinkedIn Easy Apply**.
   - The status updates live to **Running** and streams applications directly to your Google Sheet!
