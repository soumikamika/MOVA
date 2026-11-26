# MOVA frontend ↔ Travel Intelligence Engine

MOVA's frontend talks to the FastAPI Travel Intelligence Engine over HTTP.

```text
MOVA website (http://127.0.0.1:5500)
        ↓
FastAPI (http://127.0.0.1:8000)
        ↓
Planner → recommendation → routing → constraints → optimizer
```

## Fastest Windows setup

From the MOVA root folder, run:

```text
start_mova_all.bat
```

This starts the backend, starts a local frontend server, and opens the browser.

If you prefer separate terminals:

```text
start_mova_backend.bat
start_mova_frontend.bat
```

Then open:

`http://127.0.0.1:5500`

## Backend health

`http://127.0.0.1:8000/api/health`

## Current planner flow

```text
Create Plan
   ↓
TripRequest
   ↓
Live/local destination + place data
   ↓
Recommendation engine
   ↓
OSRM road routing when coordinates are available
   ↓
Travel-method recommendation
   ↓
Constraint engine
   ↓
Optimizer
   ↓
Edit Plan
   ↓
Confirm
   ↓
Plan Dashboard
```

## Provider limitations

- OpenStreetMap/Nominatim/Overpass provide geographic/place information, not booking availability.
- OSRM provides road routing only.
- Train, bus and flight schedules/fares are currently marked `NOT_INTEGRATED` rather than invented.
- If a live provider is unavailable, MOVA shows an explicit fallback/unavailable state.

## Development data

The bundled Goa planner dataset is synthetic development data. It is clearly marked in planner provenance and should not be presented as real tourism facts.

## Frontend API override

The frontend API URL can be overridden with:

1. `?api=https://your-api.example.com`
2. `window.MOVA_CONFIG.apiBaseUrl`
3. `<meta name="mova-api-base" content="...">`
4. `localStorage.movaApiBaseUrl`
5. default: `http://127.0.0.1:8000`
