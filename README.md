# SQLM Web App

This folder is the standalone SQLM project directory for the Williamson hybrid nanofluid solver and web app.

## Structure

- `backend/`: FastAPI API with the vendored solver modules needed by the app.
- `frontend/`: React + Vite client for configuring parameters and visualizing results.
- `venv/`: Python virtual environment for the SQLM project.
- `ep_results/`: Saved figures exported by study runs.

## Backend

From inside `SQLM/`:

```bash
source venv/bin/activate
python -m uvicorn backend.app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

## Frontend

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

The Vite frontend proxies `/api` requests to the FastAPI server on port `8000`.

## Current API

- `GET /health`
- `GET /api/config`
- `POST /api/studies/pair`

## Current UI

- editable solver parameters
- editable material properties
- editable nanofluid presets
- pair-study submission
- 3D surface comparison
- combined contour comparison
- summary cards for each nanofluid
