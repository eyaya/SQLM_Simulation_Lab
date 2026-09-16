# Deploying SQLM Simulation Lab

Frontend on Vercel, API on Render.

```
                    ┌──────────────────────────┐
   static assets    │  Vercel (frontend/)      │
  ┌────────────────▶│  React bundle on the CDN │
  │                 └──────────────────────────┘
Browser
  │                 ┌──────────────────────────┐
  └────────────────▶│  Render (backend/)       │
     XHR, direct    │  FastAPI + SQLM solver   │
     and CORS'd     └──────────────────────────┘
```

The browser calls Render **directly** rather than being proxied through Vercel.
That is deliberate: a Vercel rewrite to an external origin is capped at
**120 seconds**, after which it fails with `ROUTER_EXTERNAL_TARGET_ERROR`. Study
requests routinely run longer than that, so proxying would cap what the app can
compute. Calling Render directly costs one CORS preflight and removes the ceiling.

## Read this before choosing a plan

A study is a single blocking, CPU-bound computation held open for the whole
HTTP request. There is no job queue. Two consequences:

**Instance CPU maps almost linearly to request duration.** Measured locally on
one full core, the default 7x7 pair study across three nanofluids takes ~11s.
Scaling that by Render's published vCPU allocations:

| Render plan | vCPU | RAM    | Default 7x7 study | 41x41 study  |
| ----------- | ---- | ------ | ----------------- | ------------ |
| Free        | 0.1  | 512 MB | ~110s             | not viable   |
| Starter     | 0.5  | 512 MB | ~22s              | ~25 min      |
| **Standard**| 1.0  | 2 GB   | **~11s**          | ~12 min      |

Estimates outside the first column are linear extrapolations, not measurements —
treat them as the right order of magnitude, not a promise.

**The free instance is not suitable here.** Beyond being ~10x too slow, it has
512 MB of RAM against a numpy + scipy + matplotlib worker set, and it spins down
after 15 minutes of inactivity with a ~1 minute cold start that lands on top of
an already slow request. Start at **Standard**.

**Large grids will exceed any platform request timeout.** Render does not
publish a single fixed number and community reports vary, but nothing survives a
12-minute request reliably. `SQLM_MAX_N` and `SQLM_MAX_MS` in `render.yaml` are
set conservatively for this reason, and `n_points` is capped at 41 by the API
schema. If you need the large grids, the fix is architectural — see
[Scaling past the timeout](#scaling-past-the-timeout).

## 1. Deploy the API to Render

The repo contains a Blueprint at [`render.yaml`](../render.yaml), so Render can
configure the service itself.

1. Push this repository to GitHub.
2. In the Render dashboard: **New +** → **Blueprint** → select the repository.
3. Render reads `render.yaml` and proposes the `sqlm-api` Docker service. Two
   variables are marked `sync: false`, so it will prompt you for them. Leave both
   blank for now — you do not know the Vercel URL yet.
4. Apply. The first build takes a few minutes.
5. Note the service URL, e.g. `https://sqlm-api.onrender.com`. Check it:

   ```bash
   curl https://sqlm-api.onrender.com/health      # {"status":"ok"}
   ```

The Blueprint sets `SQLM_WRITE_FIGURES=false`. Render's filesystem is ephemeral,
so exported PNGs would be discarded on every restart and redeploy, and nothing
serves them anyway — the UI renders its plots client-side from the JSON
response. Skipping the export also saves about 0.5s per request (measured for
the default pair study). If you want the figures, run locally with Docker
Compose, where `./ep_results` is bind-mounted to your machine.

## 2. Deploy the frontend to Vercel

1. In Vercel: **Add New** → **Project** → import the same repository.
2. Set **Root Directory** to `frontend`. This matters — it is what makes Vercel
   pick up [`frontend/vercel.json`](../frontend/vercel.json) and the right
   `package.json`.
3. Framework preset should auto-detect as Vite. Build settings come from
   `vercel.json`.
4. Add an environment variable, ticked for **Production, Preview and
   Development** — see [`frontend/.env.example`](../frontend/.env.example):

   | Name                 | Value                             |
   | -------------------- | --------------------------------- |
   | `VITE_API_BASE_URL`  | `https://sqlm-api.onrender.com`   |

   No trailing slash, no quotes. Vite inlines `VITE_*` at **build time**, so
   changing it requires a rebuild — a restart will not pick it up. When
   redeploying to apply it, untick **"Use existing Build Cache"**, or Vercel may
   reuse the bundle that was built without it.

   If this is missing, the client calls its own origin instead of the API. The
   symptom is `JSON.parse: unexpected character at line 1 column 1` — the app
   is parsing its own `index.html`. The SPA rewrite in `vercel.json` is written
   as `/:path((?!api/|health$).*)` precisely so `/api/*` returns a clean 404
   rather than silently serving HTML with a 200. (`vercel.json` sets
   `additionalProperties: false`, so it cannot carry comments explaining this —
   hence the note here.)

   To confirm the value actually reached the bundle:

   ```bash
   APP=https://your-project.vercel.app
   A=$(curl -s $APP/ | grep -o '/assets/[^"]*\.js' | head -1)
   curl -s "$APP$A" | grep -c 'sqlm-api.onrender.com'   # 0 = not set at build time
   ```
5. Deploy, and note the production URL, e.g.
   `https://sqlm-simulation-lab.vercel.app`.

## 3. Let the two talk (CORS)

The API rejects cross-origin browser calls from origins it does not know, so
this step is required — until you do it, the deployed UI will load but every
request will fail in the browser console.

In the Render dashboard, on `sqlm-api` → **Environment**, set the two
variables that `render.yaml` deliberately leaves blank (`sync: false`). The
full deployed configuration is documented in
[`.env.production.example`](../.env.production.example):

| Variable                  | Value                                                  |
| ------------------------- | ------------------------------------------------------ |
| `SQLM_CORS_ORIGINS`       | `https://sqlm-simulation-lab.vercel.app`               |
| `SQLM_CORS_ORIGIN_REGEX`  | `https://sqlm-simulation-lab-[a-z0-9-]+\.vercel\.app`  |

`SQLM_CORS_ORIGINS` is a comma-separated exact list — put your production domain
(and any custom domain) there.

`SQLM_CORS_ORIGIN_REGEX` is optional and only needed if you want **preview
deployments** to work. Every Vercel preview gets a generated hostname per
branch, so it cannot be listed exactly. Keep the pattern anchored to your own
project prefix — a loose pattern like `https://.*\.vercel\.app` would let any
Vercel-hosted site call your API.

Render restarts the service on save. Verify from the deployed UI, or directly:

```bash
curl -i -X OPTIONS https://sqlm-api.onrender.com/api/config \
  -H "Origin: https://sqlm-simulation-lab.vercel.app" \
  -H "Access-Control-Request-Method: GET"
# expect: access-control-allow-origin: https://sqlm-simulation-lab.vercel.app
```

## Alternative: same-origin via Vercel rewrite

If you would rather avoid CORS entirely, you can have Vercel proxy the API
instead. Leave `VITE_API_BASE_URL` unset (the client then calls its own origin)
and add to `frontend/vercel.json`:

```json
"rewrites": [
  { "source": "/api/(.*)", "destination": "https://sqlm-api.onrender.com/api/$1" },
  { "source": "/(.*)", "destination": "/index.html" }
]
```

Order matters: the SPA catch-all must stay last. The tradeoff is the **120s
proxy ceiling** described above, which becomes a hard cap on study size. Only
worth it if you constrain the app to small grids.

## Scaling past the timeout

Both platforms assume a request finishes in seconds. The app's larger studies do
not, and no amount of configuration changes that. The real fix is to stop
holding the request open:

- `POST /api/studies/*` enqueues work, returns `202 Accepted` with a job id.
- A Render **Background Worker** runs the solve.
- The client polls `GET /api/jobs/{id}` until the result is ready.

That needs a job store (Render Redis or Postgres) and a second service. It is a
meaningful change to both the API and the UI, and it is the only approach that
makes the 41x41 grids work over the public internet.

## Troubleshooting

**CORS error in the browser console.** `SQLM_CORS_ORIGINS` does not match the
origin exactly. Scheme, host and port all count, and there must be no trailing
slash.

**Requests fail only on preview URLs.** Expected without
`SQLM_CORS_ORIGIN_REGEX`; see step 3.

**First request after idle is very slow.** Free and Starter instances spin down
after 15 minutes; the cold start is roughly a minute on top of the request.

**502 or a dropped connection on a big study.** The request outran the platform
timeout. Reduce `n_points`, or move to the async pattern above.

**Frontend builds but calls `localhost`.** `VITE_API_BASE_URL` was missing at
build time. Set it and redeploy — a restart will not pick it up.

**Render build is slow to start.** The repository has `venv/` committed
(~424 MB, 12,503 files) and Render clones it on every deploy. Untracking it
(`git rm -r --cached venv`) speeds up cloning; the `.gitignore` at the repo root
already prevents it coming back.
