# 🚀 Permanent Cloud Deployment Guide

This guide details how to deploy the **Olympic Agentic GraphRAG** project so that:
1. You get a **live, public HTTPS link** that you can submit for the hackathon.
2. **The link remains permanently identical** even when you make changes, fix bugs, or push new commits to GitHub later.
3. Every `git push origin main` triggers an **automatic zero-downtime rebuild and redeployment**.

---

## 🌟 Method 1: Streamlit Community Cloud (Recommended for Dashboard)

Streamlit Community Cloud is 100% free forever, managed by Snowflake/Streamlit, and provides an instant custom subdomain that never changes.

### Step 1: Sign Up / Log In
1. Go to **[share.streamlit.io](https://share.streamlit.io/)**.
2. Click **"Continue with GitHub"** and authorize with the GitHub account hosting `tusharkkp/TigerGraph_GraphRAG-Hackathon`.

### Step 2: Deploy New App
1. Click the blue **"Create app"** button.
2. Select **"I already have an app"**.
3. Fill in the repository settings:
   - **Repository:** `tusharkkp/TigerGraph_GraphRAG-Hackathon`
   - **Branch:** `main`
   - **Main file path:** `src/app/dashboard.py`
   - **App URL (Customize your link):** You can set a custom permanent name, e.g.:
     `tigergraph-agentic-graphrag` &rarr; gives `https://tigergraph-agentic-graphrag.streamlit.app`

### Step 3: Add Your Secrets (Environment Variables)
1. Before clicking Deploy, click **"Advanced settings..."** (or go to App Settings &rarr; Secrets after deploy).
2. Under the **Secrets** text area, paste your credentials in TOML format:

```toml
TG_HOST = "https://your-savanna-domain.i.tgcloud.io"
TG_GRAPHNAME = "GraphRAG"
TG_USERNAME = "tigergraph"
TG_PASSWORD = "your_tg_password"
TG_SECRET = "your_tg_secret"
GEMINI_API_KEY = "your_gemini_api_key"
```

3. Click **"Save"** and **"Deploy!"**.

### Why the Link Never Changes:
- Your link `https://<your-custom-name>.streamlit.app` is bound to your GitHub branch (`main`).
- Whenever you `git push origin main`, Streamlit Cloud detects the webhook, pulls the changes, and updates the live site in ~30 seconds while keeping the exact same URL.

---

## ⚡ Method 2: Render (Recommended for FastAPI Backend & Glassmorphic Web App)

Render provides a free Web Service tier that serves the FastAPI application (`src/app/api.py`) with its interactive glassmorphic UI.

### Step 1: Create a Free Account
1. Go to **[render.com](https://render.com/)** and sign in with GitHub.

### Step 2: Create Web Service
1. In the Render Dashboard, click **"New +"** &rarr; **"Web Service"**.
2. Select your repository: `tusharkkp/TigerGraph_GraphRAG-Hackathon`.
3. Configure the service:
   - **Name:** `tigergraph-agentic-graphrag` (determines your permanent URL: `https://tigergraph-agentic-graphrag.onrender.com`)
   - **Region:** Any (e.g. Oregon, Frankfurt, Singapore)
   - **Branch:** `main`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn src.app.api:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** `Free`

### Step 3: Add Environment Variables
Scroll to **"Environment Variables"** and add:
- `TG_HOST` = `https://your-savanna-domain.i.tgcloud.io`
- `TG_GRAPHNAME` = `GraphRAG`
- `TG_USERNAME` = `tigergraph`
- `TG_PASSWORD` = `your_tg_password`
- `TG_SECRET` = `your_tg_secret`
- `GEMINI_API_KEY` = `your_gemini_api_key`

Click **"Create Web Service"**.

### Why the Link Never Changes:
- Render assigns a permanent URL: `https://tigergraph-agentic-graphrag.onrender.com`.
- **Auto-Deploy** is enabled by default for `main`. Every push to GitHub updates the deployed app automatically.

---

## 🤗 Method 3: Hugging Face Spaces (Alternative Free Option)

1. Go to **[huggingface.co/spaces](https://huggingface.co/spaces)** and click **"Create new Space"**.
2. Space Name: `olympic-agentic-graphrag`
3. License: `mit`
4. Space SDK: **Streamlit** (or **Docker**)
5. In Space Settings &rarr; **Variables and secrets**, add your `TG_HOST`, `TG_PASSWORD`, `GEMINI_API_KEY`, etc.
6. Push code to the Space or set up GitHub Actions sync.
7. Your link is permanently: `https://huggingface.co/spaces/<your-username>/olympic-agentic-graphrag`.

---

## 🔄 Summary of How Continuous Deployment Works

```
 Local Edits ──► git commit ──► git push origin main
                                          │
                                 GitHub Webhook Trigger
                                          ▼
                      ┌───────────────────────────────────────┐
                      │ Cloud Host (Streamlit Cloud / Render) │
                      │ • Pulls latest code                   │
                      │ • Installs updated requirements.txt   │
                      │ • Hot-restarts container              │
                      │ • Retains 100% same permanent URL     │
                      └───────────────────────────────────────┘
```
