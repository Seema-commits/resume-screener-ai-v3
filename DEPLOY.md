# Deploying TalentLens AI

```
Browser ──► Cloudflare Pages (React app + /api proxy function) ──► Cloud Run (FastAPI) ──► Neon Postgres
                                                                                   └──► LLM providers
```

The browser only ever talks to the Cloudflare site. `frontend/functions/api/[[path]].ts`
forwards `/api/*` to Cloud Run, so the session cookie is first-party (`SameSite=Lax`,
works in Safari), no CORS is needed, and the CSP stays at `connect-src 'self'`.
The Streamlit app keeps running as before and shares the same Neon database.

Both services scale to zero, so for a portfolio this normally stays within the free tiers.

## What you need

- A **Google Cloud** project with billing on (set a budget alert, e.g. $1) and the
  `gcloud` CLI signed in.
- A **Cloudflare** account (free).
- The values already in your Streamlit Secrets: `DATABASE_URL`, `KEY_ENCRYPTION_SECRET`
  (**must be the same** as Streamlit's, or saved org keys can't be read), and optionally
  `ANTHROPIC_API_KEY` / other provider keys and the `LANGFUSE_*` keys.

## Email for "Forgot password?" (Gmail)

1. Turn on **2-Step Verification** for the Gmail account that will send the emails
   (myaccount.google.com → Security).
2. Create an **App Password**: myaccount.google.com/apppasswords → name it `TalentLens` →
   copy the 16-character password. It only works for sending mail and can be revoked any time.
3. Add to **Streamlit Secrets** (and later Cloud Run, below):
   ```toml
   SMTP_USER = "you@gmail.com"
   SMTP_PASSWORD = "the 16-character app password"
   APP_URL = "https://your-app.streamlit.app"     # this front end's own address
   ```
   Reboot the app. On Cloud Run `APP_URL` is the Pages address (`https://talentlens.pages.dev`).

Gmail free accounts send up to about 500 emails a day. Recipients may find the first
emails in spam. Locked out of the Superadmin account? `python -m app.scripts.reset_password`
with `DATABASE_URL` set (no email needed).

## 1. API on Cloud Run

Use the region closest to your Neon database.

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com secretmanager.googleapis.com

# Each secret is typed at a prompt - never put it on the command line or in a file
for name in DATABASE_URL KEY_ENCRYPTION_SECRET ANTHROPIC_API_KEY SMTP_PASSWORD; do
  read -rsp "$name: " value && printf %s "$value" | gcloud secrets create "$name" --data-file=- ; echo
done

# Let Cloud Run read them
PROJECT_NUMBER=$(gcloud projects describe "$(gcloud config get project)" --format='value(projectNumber)')
for name in DATABASE_URL KEY_ENCRYPTION_SECRET ANTHROPIC_API_KEY SMTP_PASSWORD; do
  gcloud secrets add-iam-policy-binding "$name" \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role=roles/secretmanager.secretAccessor
done

# Build (Cloud Build, from the Dockerfile) and deploy
gcloud run deploy talentlens-api --source . --region europe-west1 \
  --allow-unauthenticated --min-instances 0 --max-instances 1 \
  --memory 1Gi --timeout 600 \
  --set-secrets DATABASE_URL=DATABASE_URL:latest,KEY_ENCRYPTION_SECRET=KEY_ENCRYPTION_SECRET:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,SMTP_PASSWORD=SMTP_PASSWORD:latest \
  --set-env-vars COOKIE_SECURE=true,COOKIE_SAMESITE=lax,FRONTEND_ORIGINS=https://talentlens.pages.dev,APP_URL=https://talentlens.pages.dev,SMTP_USER=you@gmail.com
```

- `--max-instances 1` keeps the "only screen new resumes" cache (held in memory) in one place.
- `--timeout 600` lets a large screening finish while it streams progress.
- Add Langfuse later the same way (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` as secrets,
  `LANGFUSE_HOST` as an env var).
- Check: `curl https://<cloud-run-url>/api/health` → `{"ok":true}`.

## 2. Frontend on Cloudflare Pages

Workers & Pages → Create → Pages → Connect to Git → this repository:

| Setting | Value |
|---|---|
| Production branch | `main` |
| Root directory | `frontend` |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Environment variable `NODE_VERSION` | `22` |
| Environment variable `API_ORIGIN` | the Cloud Run URL, e.g. `https://talentlens-api-xxxx.a.run.app` |

Leave `VITE_API_BASE` unset: the app calls `/api` on its own site and the function forwards it.
If the Pages address isn't `talentlens.pages.dev`, update `FRONTEND_ORIGINS` on Cloud Run
to match (`gcloud run services update talentlens-api --update-env-vars FRONTEND_ORIGINS=https://…`).

`frontend/public/_headers` adds the CSP and other security headers to every page.

## 3. After deploying

- Sign in with an existing account (same database as Streamlit).
- Every push to `main` redeploys the frontend automatically; redeploy the API with the
  same `gcloud run deploy` command (or connect Cloud Run to the repo for continuous deployment).
- GitHub Actions (`.github/workflows/ci.yml`) runs the Python tests and the frontend
  lint/tests/build on every pull request.
