# MOVA

MOVA is an India-first travel discovery and intelligent trip-planning platform.

## Project structure

```text
mova/
├── index.html
├── pages/                         # Website pages
├── css/                           # Global + page styles
├── js/                            # Frontend logic + API adapter
├── data/                          # Frontend discovery/catalog data
├── assets/                        # MOVA visual assets
├── backend/
│   └── mova_travel_engine/        # FastAPI + planning engine
├── start_mova_backend.ps1         # Windows PowerShell backend launcher
├── start_mova_backend.bat         # Windows CMD backend launcher
├── start_mova_frontend.bat        # Simple local frontend server
└── start_mova_all.bat             # Starts backend + frontend
```

## Website

The frontend includes:

- Home
- Discover
- Community
- My Plans
- Create Plan
- Region Details
- Place Details
- Profile
- Light/dark appearance
- Local plan persistence
- Live geographic discovery with cache/retry fallbacks
- FastAPI planning-engine integration
- Real road-routing integration through OSRM when available
- Deterministic travel-method recommendation with explicit live/estimated/not-integrated status
- Multi-destination route legs

## Planning engine

The backend includes:

- Recommendation engine
- Travel-time and travel-cost services
- Constraint engine
- Deterministic itinerary optimizer
- Plan modification and re-optimization
- Itinerary validation
- FastAPI endpoints for generate / optimize / modify / validate
- `/api/capabilities` for reporting the currently configured planner dataset

The backend test suite currently passes **466 tests**.

## Run MOVA locally

### 1. Start the backend

From the MOVA root folder on Windows, run:

```powershell
.\start_mova_backend.ps1
```

or:

```text
start_mova_backend.bat
```

The API runs at:

`http://127.0.0.1:8000`

The launcher creates a local Python virtual environment when needed and installs the backend requirements.

### 2. Start the frontend

Easiest Windows option: run:

```text
start_mova_frontend.bat
```

Then open:

`http://127.0.0.1:5500`

You can also use VS Code Live Server on `index.html`.

For the fastest setup, run `start_mova_all.bat`; it starts the backend, starts a local frontend server, and opens the browser.

The frontend expects the API at:

`http://127.0.0.1:8000`

The API URL can be overridden with:

1. `?api=https://your-api.example.com`
2. `window.MOVA_CONFIG.apiBaseUrl`
3. `<meta name="mova-api-base" content="...">`
4. `localStorage.movaApiBaseUrl`

## Development data

The bundled planner dataset is development/synthetic data and is surfaced as such by the API. It must not be presented as live tourism facts or used to claim production model accuracy.

If a production dataset is not configured, the backend automatically uses the first complete bundled development dataset available under `backend/mova_travel_engine/data/dev/`.

When local planner records are unavailable for a destination, the backend can fall back to live OpenStreetMap/Nominatim/Overpass discovery when internet access is available. OSM-derived planning estimates are explicitly labelled as estimates.

Create Plan no longer blocks destinations that are outside the bundled planner dataset; it lets the backend attempt live discovery instead. If live discovery is unavailable, the user gets an explicit error rather than fabricated data.

## Before public deployment

- Replace development data with production-quality data.
- Add live provider adapters behind the backend.
- Add persistent database storage.
- Add authentication and cloud user accounts.
- Train production ML models using sufficient real/user-generated/external data.
- Deploy frontend and API behind stable HTTPS endpoints.


