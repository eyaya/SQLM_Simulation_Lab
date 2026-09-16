# SQLM Web App

Standalone project directory for the Williamson hybrid nanofluid SQLM solver
and its web app.

## Structure

- `backend/`: FastAPI API with the vendored solver modules needed by the app.
- `frontend/`: React + Vite client for configuring parameters and visualizing results.
- `venv/`: Python virtual environment for local (non-Docker) development.
- `ep_results/`: Figures exported by study runs.

## Run with Docker (recommended)

Requires Docker Engine with the Compose plugin.

```bash
cp .env.example .env     # optional: adjust port, workers, UID/GID
docker compose up --build
```

Open <http://localhost:8080>.

Two containers come up:

| Service    | Image             | Role                                                      |
| ---------- | ----------------- | --------------------------------------------------------- |
| `backend`  | `python:3.12-slim`| FastAPI + solver on port 8000 (internal network only)      |
| `frontend` | `nginx:alpine`    | Serves the built client and reverse-proxies `/api`, `/health` |

Because nginx proxies the API, the browser only ever talks to one origin, so
no CORS configuration is needed in the default setup.

Figures written by study runs land in `./ep_results` on the host through a bind
mount. Set `UID`/`GID` in `.env` to your own (`id -u`, `id -g`) if you are not
uid 1000, so those files stay owned by you.

Useful commands:

```bash
docker compose logs -f backend      # follow API logs
docker compose up -d --build        # rebuild and restart
docker compose down                 # stop and remove containers
FRONTEND_PORT=8090 docker compose up   # if 8080 is taken
```

### Configuration

All variables are optional; defaults are in `.env.example`.

| Variable            | Default | Purpose                                                     |
| ------------------- | ------- | ----------------------------------------------------------- |
| `FRONTEND_PORT`     | `8080`  | Host port for the web UI.                                    |
| `UVICORN_WORKERS`   | `2`     | Concurrent studies. Each worker is a ~250 MB process.        |
| `UID` / `GID`       | `1000`  | Ownership of files written into `./ep_results`.              |
| `SQLM_CORS_ORIGINS` | see below | Comma-separated origins allowed to call the API directly.  |
| `SQLM_OUTPUT_DIR`   | `<project>/ep_results` | Where figures are written.                    |
| `VITE_API_BASE_URL` | empty   | Build-time API base. Empty means same-origin.                |

`SQLM_CORS_ORIGINS` only matters when a browser reaches the API directly rather
than through the nginx proxy; unset, it falls back to the Vite dev-server
origins (`:5173`, `:4173`).

To reach the API directly (for example for the Swagger UI at
`http://localhost:8000/docs`), uncomment the `ports` block on the `backend`
service in `docker-compose.yml`.

### Notes on long-running studies

A study is a blocking, CPU-bound computation: the default 7x7 pair study takes
roughly 11 seconds, while the maximum 41x41 grid across three nanofluids runs
for several minutes. The nginx proxy is configured with a 1800s read timeout to
accommodate this, and `UVICORN_WORKERS` caps how many studies can run at once.

## Run locally without Docker

Backend, from this directory:

```bash
source venv/bin/activate
python -m uvicorn backend.app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

Frontend, in another terminal:

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` requests to the FastAPI server on port `8000`.

## Current API

- `GET /health`
- `GET /api/config`
- `POST /api/studies/pair`
- `POST /api/studies/profile`
- `POST /api/studies/residual`

## Current UI

- editable solver parameters
- editable material properties
- editable nanofluid presets
- pair-study submission
- 3D surface comparison
- combined contour comparison
- summary cards for each nanofluid
- profile and residual studies
