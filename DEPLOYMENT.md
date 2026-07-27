# Hosted deployment: Vercel (frontend) + Render (backend/worker/scheduler)

This is the checklist for the parts I can't do for you -- creating accounts,
connecting the repo, and pasting secrets into each provider's own dashboard.
I built and tested everything on the code side (see `render.yaml`,
`render.Dockerfile`, `frontend/vercel.json`); this is what's left.

Cost reality, upfront: Vercel (frontend) and Render's web service both have
real free tiers. Render's free tier does **not** cover persistent
Background Worker services, and the quick_scan worker genuinely needs one
(it has to sit and wait for jobs, not run on a timer) -- expect Render's
cheapest paid tier for the `medtech-agent-worker` service (and the
`medtech-agent-scheduler` one, unless you'd rather convert that one to a
Render Cron Job later to save the cost -- it's just a 5-minute timer, ask
me if you want that swap). Neon and Upstash's free tiers are enough for
this app's traffic level.

## 1. Push to GitHub

The repo already has a remote (`github.com/wizbubba1/complianceagent`).
Make sure everything's pushed:

```
git push origin main
```

## 2. Neon (Postgres + pgvector) -- free tier

1. Create an account at neon.tech, new project.
2. Open the SQL editor and run: `CREATE EXTENSION IF NOT EXISTS vector;`
3. Copy the **pooled** connection string (Neon's dashboard labels it
   "Pooled connection" -- use this one, not the direct one; it matters
   because both the web process and every Celery task open their own
   short-lived connection).
4. It'll look like `postgresql://user:pass@ep-xxx-pooler.region.aws.neon.tech/dbname?sslmode=require`.
   Change the scheme to `postgresql+psycopg://` (SQLAlchemy's dialect
   prefix) -- keep everything else, including `?sslmode=require`.

## 3. Upstash (Redis) -- free tier

1. Create an account at upstash.com, new Redis database (any region close
   to where you put Render).
2. Copy the connection string starting with `rediss://` (note the double
   `s` -- TLS is required for external connections; the plain `redis://`
   one won't work from outside Upstash).

## 4. Render (backend/worker/scheduler)

1. Create an account at render.com, connect your GitHub account, give it
   access to this repo.
2. New → Blueprint → pick this repo. Render reads `render.yaml` and
   proposes all three services (`medtech-agent-api`, `-worker`,
   `-scheduler`).
3. When it asks for the `sync: false` env vars, fill in:
   - `DATABASE_URL` → the Neon string from step 2 (same value on all
     three services)
   - `REDIS_URL` → the Upstash string from step 3 (same value on all
     three services)
   - `ADDITIONAL_CORS_ORIGINS` on the api service only → leave blank for
     now, you'll come back and fill this in after step 5
4. Deploy. If Render asks you to pick a plan for the worker/scheduler
   services, that's the "not actually free" part flagged above.
5. Once `medtech-agent-api` is live, open its **Shell** tab and run the
   migrations once (this container already has alembic + every migration
   baked in):
   ```
   alembic upgrade head
   ```
   This also runs the settings-table migration (0013) -- since this is a
   brand-new database, there's no local `app_settings.json` for it to seed
   from, so the runtime_settings row starts empty. You'll enter your
   OpenRouter/Brave keys through the hosted Settings page after it's live,
   same as you would locally.

## 5. Vercel (frontend)

1. Create an account at vercel.com, import this GitHub repo.
2. Set the project's **root directory** to `frontend`.
3. Add an environment variable: `VITE_API_BASE_URL` =
   `https://medtech-agent-api.onrender.com/api/v1` (use your actual
   Render web service URL, shown on its dashboard page).
4. Deploy. Vercel auto-detects the Vite build (`npm run build`, output
   `dist`); `frontend/vercel.json` is already there to make client-side
   routes like `/products/:id` work on a hard refresh, not just on
   in-app navigation.

## 6. Close the loop on CORS

Once you have the real Vercel URL, go back to Render → the
`medtech-agent-api` service → Environment → set `ADDITIONAL_CORS_ORIGINS`
to that URL (e.g. `https://your-app.vercel.app`, no trailing slash).
Render redeploys automatically when you save an env var change.

## 7. Verify

Visit the Vercel URL. Settings page should load (all keys will show "not
set" the first time -- that's expected, see step 4.5). Add your
OpenRouter and Brave Search keys there, then try a quick scan end to end.

---

**What still only works locally, on purpose, not fixed here:** the old
project/crawl document-library upload path writes files to local disk
(`STORAGE_ROOT`), which doesn't persist across Render restarts/redeploys
without a paid persistent disk add-on. This doesn't affect the actual
product (the quick_scan composer parses uploads in memory and never
writes them to disk) -- it only matters if you still use the legacy,
nav-hidden project/crawl features.
