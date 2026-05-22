# Deploy Folio — free forever

Stack:

| Component | Provider | Free tier |
|---|---|---|
| Frontend | **Vercel** | unlimited static hosting, custom domain, free forever |
| Backend  | **Render** | 750 web-service hours/month, sleeps after 15 min idle, free forever |
| MongoDB  | **MongoDB Atlas M0** | 512 MB shared cluster, free forever |
| Redis    | **Upstash** | 10,000 commands/day, free forever |

End result: a public URL like `https://folio-rishika.vercel.app` you can share. First request after idle wakes Render in ~30s; subsequent requests are fast.

---

## 0. Prep — push to GitHub

```bash
cd "/Users/rishika/Desktop/Projects/Medical Chatbot"

# Make sure no secrets are committed.
git status
cat .gitignore   # should include .env

# First-time init
git init
git add .
git commit -m "Folio: multimodal medical record with chat + RAG + multi-LLM consensus"

# Create a new repo on github.com (private is fine), then:
git remote add origin git@github.com:<your-username>/folio.git
git branch -M main
git push -u origin main
```

⚠️ Double-check `git diff --cached -- .env.example` before pushing — only placeholders should be in there. Real keys live in `.env` which is gitignored.

---

## 1. MongoDB Atlas (free 512 MB cluster)

1. Sign up: https://www.mongodb.com/cloud/atlas/register
2. **Build a Cluster** → choose **M0 Free**, region close to you (e.g. AWS us-east-1).
3. **Database Access** → **Add new database user** → username `folio`, password (generate + save).
4. **Network Access** → **Add IP Address** → **Allow access from anywhere** (`0.0.0.0/0`). For a single-user demo this is fine.
5. **Database** → **Connect** → **Drivers** → copy the connection string. Looks like:
   ```
   mongodb+srv://folio:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
   Replace `<password>` with the actual one. Save this — you'll paste it into Render as `MONGO_URL`.

---

## 2. Upstash Redis (free)

1. Sign up: https://upstash.com (Google login is fastest).
2. **Redis** → **Create database** → name `folio`, region close to your Render region, **Free** tier.
3. On the database page, copy the **`UPSTASH_REDIS_REST_URL`** is for HTTP — we want the standard **Redis URL** under "Connect → Redis CLI". Looks like:
   ```
   rediss://default:<password>@<host>.upstash.io:6379
   ```
   Note `rediss://` (TLS). Save this for Render as `REDIS_URL`.

---

## 3. Render backend

1. Sign up: https://dashboard.render.com (GitHub login).
2. **New** → **Blueprint** → connect your GitHub → pick the `folio` repo. Render will read `render.yaml` and propose the `folio-backend` service.
3. Click **Apply**. Render builds the Dockerfile in `backend/`. Takes ~5 minutes the first time.
4. Once the service is up, go to its **Environment** tab and fill in:

   | Key | Value |
   |---|---|
   | `MONGO_URL` | the Atlas connection string from step 1 |
   | `REDIS_URL` | the Upstash URL from step 2 |
   | `ANTHROPIC_API_KEY` | your Anthropic key |
   | `OPENAI_API_KEY` | your OpenAI key |
   | `GEMINI_API_KEY` | your Gemini key |
   | `APP_PASSWORD` | **the password you'll type on the /login screen.** Pick something long. |
   | `JWT_SECRET` | Render auto-generates this from `render.yaml`. Leave the generated value. |
   | `CORS_ORIGINS` | leave blank for now — fill in step 5 once you have the Vercel URL |

   Click **Save Changes**. Render redeploys automatically.

   ⚠️ If you skip `APP_PASSWORD`, auth is **disabled** and anyone hitting your URL can read your record. Always set it for a public deploy.

5. Note the service URL — looks like `https://folio-backend.onrender.com`. Test it:
   ```bash
   curl https://folio-backend.onrender.com/api/dev/health
   # → {"mongo": true}
   ```

6. **Do NOT seed the cloud database** for a real personal deployment — you want it to start empty so your actual record builds from scratch. (If you want sample data for a demo screencast only, Render's **Shell** tab on the service can run `python -m app.seed`, but skip this for personal use.)

---

## 4. Vercel frontend

1. Sign up: https://vercel.com (GitHub login).
2. **Add New** → **Project** → import the `folio` repo.
3. **Configure project**:
   - **Root directory**: `frontend`
   - **Framework**: Vite (auto-detected)
   - **Build command**: `npm run build` (auto)
   - **Output directory**: `dist` (auto)
4. **Environment Variables**:
   | Key | Value |
   |---|---|
   | `VITE_API_URL` | `https://folio-backend.onrender.com` (the Render URL from step 3.5) |
5. Click **Deploy**. Takes ~1 minute. Note the assigned URL — looks like `https://folio-rishika.vercel.app`.

---

## 5. Lock CORS to your Vercel origin

Back in Render → **Environment** → set:

```
CORS_ORIGINS=https://folio-rishika.vercel.app,http://localhost:5173
```

Save → Render redeploys. The backend now only accepts browser requests from your Vercel frontend (and your local dev). API curl from the terminal still works — CORS only applies to browsers.

---

## 6. Wake routine for demos

Render free tier sleeps after 15 min idle. Cold start is ~30s while the container boots and hits Mongo/Redis. Before any live demo:

```bash
curl https://folio-backend.onrender.com/api/dev/health
```

Wait ~30s, then load the Vercel URL. Stays warm for 15 min after that.

If you want to keep it always-warm, set up a free cron-style ping every 14 minutes:
- https://cron-job.org → free tier → schedule a GET to `/api/dev/health` every 14 min.

---

## What this costs

Zero, indefinitely. Anthropic/OpenAI/Gemini keys are pay-per-use; expect <$1/month for portfolio-scale traffic with the spend caps you already set in their consoles.

---

## Updates after deploy

`git push` → Render auto-deploys backend, Vercel auto-deploys frontend. No manual redeploy needed.

---

## Troubleshooting

- **"Mongo timeout" on Render**: Atlas Network Access still set to single IP? Switch to `0.0.0.0/0`.
- **CORS error in browser**: `CORS_ORIGINS` doesn't match your actual Vercel URL exactly (no trailing slash). Update and Render will redeploy.
- **Chat returns "no API key"**: env vars not saved on Render. Re-check the **Environment** tab.
- **Render build fails on Pillow / pdf2image**: the Dockerfile already installs `poppler-utils` and `libgl1`; if it still fails, bump the build to **Starter** plan ($7/mo) which has more memory — or split out heavy deps into a smaller requirements file. For demo traffic, free should work.
