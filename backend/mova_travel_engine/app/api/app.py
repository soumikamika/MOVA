"""FastAPI adapter for the MOVA planning engine."""
from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.exceptions import MovaError, NotFoundError, ProviderError
from app.core.logging import get_logger
from app.data.repositories.json_repos import load_json_repositories
from app.schemas.modification import PlanModificationRequest, PlanModificationResult
from app.schemas.planner import PlanGenerationRequest, PlanGenerationResult
from app.services.modifications import PlanModificationService
from app.services.planner import PlannerService
from app.providers.osm import OSMProvider, OSMProviderConfig

logger = get_logger(__name__)
settings=get_settings()

def _resolve_dataset_dir() -> Path:
    # Prefer an explicitly configured dataset. For a fresh checkout, fall back
    # to a bundled development dataset instead of silently loading an
    # empty root/data directory. The API exposes its provenance through
    # /api/capabilities so the frontend never presents synthetic data as live.
    configured = Path(settings.data_dir)
    required = ("destinations.json", "places.json")
    if all((configured / name).is_file() for name in required):
        return configured

    development_root = Path(__file__).resolve().parents[2] / "data" / "dev"
    if development_root.is_dir():
        for candidate in sorted(development_root.iterdir()):
            if candidate.is_dir() and all((candidate / name).is_file() for name in required):
                return candidate

    return configured

_LIVE_PROVIDER = None

def _get_live_provider():
    global _LIVE_PROVIDER
    if not settings.osm_enabled:
        return None
    if _LIVE_PROVIDER is None:
        _LIVE_PROVIDER = OSMProvider(OSMProviderConfig(
            cache_ttl_seconds=settings.osm_cache_ttl_seconds,
            search_radius_m=settings.osm_search_radius_m,
            max_places=settings.osm_max_places,
            planner_visit_minutes=settings.osm_planner_visit_minutes,
            planner_intensity=settings.osm_planner_intensity,
        ))
    return _LIVE_PROVIDER

def build_planner() -> PlannerService:
    repos=load_json_repositories(_resolve_dataset_dir(), strict=True, missing_ok=True, persist=False)
    return PlannerService(repos, live_provider=_get_live_provider())

app=FastAPI(title="MOVA Travel Intelligence Engine",version="1.0.0",description="Planning, optimization and constraint validation API for MOVA.")
# Live Server may expose the frontend as localhost, 127.0.0.1, or the machine's
# private LAN address (for example 192.168.0.104:5500). Keep explicit configured
# origins, while allowing local development origins without requiring users to
# edit .env every time their LAN IP changes.
LOCAL_DEV_ORIGIN_REGEX = r"^https?://(?:localhost|127\.0\.0\.1|10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})(?::\d+)?$"
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=LOCAL_DEV_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _error(exc: MovaError):
    status={"not_found":404,"data_unavailable":503,"invalid_trip_request":422,"infeasible_plan":409,"data_load_error":503}.get(exc.code,400)
    return HTTPException(status_code=status,detail={"code":exc.code,"message":exc.message,"details":exc.details})

@app.get("/api/health")
def health():
    return {"status":"ok","service":"mova-travel-engine","version":app.version}

@app.get("/api/regions/discover")
def discover_region(
    name: str = Query(min_length=2, max_length=100),
    scope: str = Query(default="region", pattern="^(city|region)$"),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
    refresh: bool = Query(default=False),
):
    """Discover sourced places server-side so browser CORS/network policies do not block providers."""
    if not settings.osm_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "provider_disabled",
                "message": "Live geographic discovery is disabled in backend settings.",
            },
        )
    if (lat is None) != (lon is None):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_coordinates",
                "message": "Both latitude and longitude must be provided together.",
            },
        )
    provider = _get_live_provider()
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "provider_disabled",
                "message": "Live geographic discovery provider is not configured.",
            },
        )
    try:
        return provider.discover_region_places(
            name=name,
            scope=scope,
            lat=lat,
            lon=lon,
            refresh=refresh,
        )
    except NotFoundError as exc:
        logger.info("Region discovery not found for %r (%s): %s", name, scope, exc.message)
        raise HTTPException(
            status_code=404,
            detail={"code": "region_not_found", "message": exc.message, "details": exc.details},
        ) from exc
    except ProviderError as exc:
        logger.warning("Region discovery provider failure for %r (%s): %s", name, scope, exc.message)
        raise HTTPException(
            status_code=503,
            detail={"code": "provider_unavailable", "message": exc.message, "details": exc.details},
        ) from exc
    except MovaError as exc:
        raise _error(exc) from exc

@app.get("/api/capabilities")
def capabilities():
    planner = build_planner()
    destinations = planner.repositories.destinations.list_all()
    places = planner.repositories.places.list_all()
    development_only = any(
        getattr(record.source, "is_development_only", False)
        for record in [*destinations, *places]
    )
    return {
        "planner": {
            "available": bool(destinations and places),
            "destination_count": len(destinations),
            "place_count": len(places),
            "development_only": development_only,
            "supported_destinations": [
                {
                    "id": item.id,
                    "name": item.name,
                    "source": item.source.value,
                    "development_only": item.source.is_development_only,
                }
                for item in sorted(destinations, key=lambda x: x.name.lower())
            ],
        },
        "providers": {
            "osm": {
                "enabled": settings.osm_enabled,
                "nominatim": "https://nominatim.openstreetmap.org/search",
                "overpass": "https://overpass-api.de/api/interpreter",
                "cache_ttl_seconds": settings.osm_cache_ttl_seconds,
                "search_radius_m": settings.osm_search_radius_m,
            },
            "routing": {
                "enabled": True,
                "provider": "OSRM",
                "profile": "driving",
                "status": "live_when_coordinates_are_available",
            },
        },
        "features": {
            "generate": True,
            "optimize": True,
            "modify": True,
            "validate": True,
            "live_destination_discovery": settings.osm_enabled,
            "live_place_discovery": settings.osm_enabled,
            "live_road_routing": True,
            "travel_method_recommendation": True,
        },
    }

@app.post("/api/plans/generate",response_model=PlanGenerationResult)
def generate(request: PlanGenerationRequest):
    try: return build_planner().generate(request)
    except MovaError as exc: raise _error(exc) from exc

@app.post("/api/plans/optimize",response_model=PlanGenerationResult)
def optimize(request: PlanGenerationRequest):
    try: return build_planner().generate(request)
    except MovaError as exc: raise _error(exc) from exc

@app.post("/api/plans/modify",response_model=PlanModificationResult)
def modify(request: PlanModificationRequest):
    try: return PlanModificationService(build_planner()).apply(request)
    except MovaError as exc: raise _error(exc) from exc

@app.post("/api/plans/validate")
def validate(request: PlanModificationRequest):
    planner=build_planner()
    destination=planner.repositories.destinations.resolve(request.trip.destination)
    if destination is None: raise _error(__import__('app.core.exceptions',fromlist=['NotFoundError']).NotFoundError("destination not found"))
    candidates=planner.repositories.places.list_by_destination(destination.id)
    if not candidates and planner.live_provider is not None:
        try:
            candidates=planner.live_provider.discover_places(destination)
        except Exception:
            candidates=[]
    restaurants=planner.repositories.restaurants.list_by_destination(destination.id)
    result=planner.validate_itinerary(request.trip,request.itinerary,candidates,restaurants)
    return result
