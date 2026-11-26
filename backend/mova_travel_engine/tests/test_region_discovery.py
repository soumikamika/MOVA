import importlib
import httpx
import pytest
from fastapi import HTTPException

api_module = importlib.import_module("app.api.app")
from app.core.exceptions import NotFoundError, ProviderError
from app.providers.osm import OSMProvider, OSMProviderConfig


def _mock_client(handler):
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": "MOVA-test/1.0"},
    )


def _provider(handler, **overrides):
    cfg = OSMProviderConfig(
        min_nominatim_interval_seconds=0,
        overpass_fallback_urls=("https://overpass.kumi.systems/api/interpreter",),
        **overrides,
    )
    return OSMProvider(cfg, _mock_client(handler))


def test_region_discovery_valid_region_without_coordinates_and_cache_hit():
    calls = {"nominatim": 0, "overpass": 0, "summary": 0}

    def handler(request):
        url = str(request.url)
        if "nominatim.openstreetmap.org" in url:
            calls["nominatim"] += 1
            return httpx.Response(200, json=[{
                "osm_type": "relation",
                "osm_id": 1997192,
                "name": "Goa",
                "type": "administrative",
                "addresstype": "state",
                "importance": 0.78,
                "lat": "15.3004543",
                "lon": "74.0855134",
                "boundingbox": ["14.89", "15.80", "73.67", "74.34"],
                "display_name": "Goa, India",
                "address": {"state": "Goa", "country": "India"},
            }])
        if request.method == "POST":
            calls["overpass"] += 1
            return httpx.Response(200, json={"elements": [
                {
                    "type": "node",
                    "id": 101,
                    "lat": 15.492,
                    "lon": 73.773,
                    "tags": {
                        "name": "Aguada Fort",
                        "historic": "fort",
                        "wikipedia": "en:Fort Aguada",
                        "website": "https://goatourism.gov.in",
                        "opening_hours": "09:30-18:00",
                    },
                },
                {
                    "type": "way",
                    "id": 102,
                    "center": {"lat": 15.4922, "lon": 73.7732},
                    "tags": {"name": "Aguada Fort", "historic": "fort"},
                },
                {
                    "type": "node",
                    "id": 103,
                    "lat": 15.447,
                    "lon": 73.968,
                    "tags": {"name": "Mangueshi Temple", "amenity": "place_of_worship"},
                },
                {
                    "type": "node",
                    "id": 104,
                    "lat": 15.314,
                    "lon": 74.314,
                    "tags": {"name": "Dudhsagar Falls", "natural": "waterfall"},
                },
                {
                    "type": "node",
                    "id": 105,
                    "lat": 15.512,
                    "lon": 73.762,
                    "tags": {"name": "Example Stay", "tourism": "hotel"},
                },
                {
                    "type": "node",
                    "id": 106,
                    "lat": 16.050,
                    "lon": 74.100,
                    "tags": {"name": "Outer Waterfall", "natural": "waterfall"},
                },
            ]})
        if "/api/rest_v1/page/summary/" in url:
            calls["summary"] += 1
            return httpx.Response(200, json={
                "type": "standard",
                "extract": "Goa is a state on the southwestern coast of India.",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Goa"}},
            })
        return httpx.Response(404)

    provider = _provider(handler)
    first = provider.discover_region_places(name="Goa", scope="region", lat=None, lon=None)
    assert first["status"] == "ok"
    assert first["cache_hit"] is False
    assert first["area"]["name"] == "Goa"
    assert first["area"]["summary"].startswith("Goa is a state")
    names = [p["name"] for p in first["places"]]
    assert "Aguada Fort" in names
    assert "Mangueshi Temple" in names
    assert "Dudhsagar Falls" in names
    # Duplicate way for Aguada Fort and hotel lodging must be excluded.
    assert names.count("Aguada Fort") == 1
    assert "Example Stay" not in names
    fort = next(p for p in first["places"] if p["name"] == "Aguada Fort")
    assert fort["ui_category"] == "heritage"
    assert fort["wikipedia_url"] == "https://en.wikipedia.org/wiki/Fort_Aguada"
    assert fort["source_url"] == "https://www.openstreetmap.org/node/101"
    temple = next(p for p in first["places"] if p["name"] == "Mangueshi Temple")
    assert temple["ui_category"] == "temples"
    assert any(p["name"] == "Outer Waterfall" for p in first["nearby_places"])

    second = provider.discover_region_places(name="Goa", scope="region", lat=None, lon=None)
    assert second["cache_hit"] is True
    assert calls["overpass"] == 1

    refreshed = provider.discover_region_places(name="Goa", scope="region", lat=None, lon=None, refresh=True)
    assert refreshed["cache_hit"] is False
    assert calls["overpass"] == 2


def test_region_discovery_invalid_region_raises_not_found():
    def handler(request):
        if "nominatim.openstreetmap.org" in str(request.url):
            return httpx.Response(200, json=[])
        return httpx.Response(500)

    provider = _provider(handler)
    with pytest.raises(NotFoundError):
        provider.discover_region_places(name="Atlantis Nowhere", scope="region")


def test_region_discovery_empty_overpass_returns_empty_status_not_error():
    def handler(request):
        url = str(request.url)
        if "nominatim.openstreetmap.org" in url:
            return httpx.Response(200, json=[{
                "osm_type": "node",
                "osm_id": 55,
                "name": "Small Village",
                "type": "village",
                "lat": "20.1",
                "lon": "78.1",
                "display_name": "Small Village, India",
                "address": {"village": "Small Village", "country": "India"},
            }])
        if request.method == "POST":
            return httpx.Response(200, json={"elements": []})
        return httpx.Response(404)

    provider = _provider(handler)
    result = provider.discover_region_places(name="Small Village", scope="city")
    assert result["status"] == "empty"
    assert result["places"] == []
    assert result["nearby_places"] == []


def test_region_discovery_overpass_timeout_uses_wikipedia_partial_fallback():
    def handler(request):
        url = str(request.url)
        if "nominatim.openstreetmap.org" in url:
            return httpx.Response(200, json=[{
                "osm_type": "relation",
                "osm_id": 1,
                "name": "Jaipur",
                "type": "city",
                "lat": "26.9124",
                "lon": "75.7873",
                "display_name": "Jaipur, Rajasthan, India",
                "address": {"city": "Jaipur", "state": "Rajasthan", "country": "India"},
            }])
        if request.method == "POST":
            raise httpx.ReadTimeout("timed out")
        if "action=query" in url and "geosearch" in url:
            return httpx.Response(200, json={"query": {"pages": [
                {
                    "pageid": 10,
                    "title": "List of tourist attractions in Jaipur",
                    "coordinates": [{"lat": 26.91, "lon": 75.78}],
                },
                {
                    "pageid": 11,
                    "title": "Hawa Mahal",
                    "description": "Palace in Jaipur, India",
                    "fullurl": "https://en.wikipedia.org/wiki/Hawa_Mahal",
                    "coordinates": [{"lat": 26.9239, "lon": 75.8267}],
                },
            ]}})
        return httpx.Response(404)

    provider = _provider(handler)
    result = provider.discover_region_places(name="Jaipur", scope="city")
    assert result["status"] == "partial"
    assert len(result["warnings"]) == 1
    assert len(result["places"]) == 1
    assert result["places"][0]["name"] == "Hawa Mahal"
    assert result["places"][0]["is_fallback"] is True
    assert result["places"][0]["provider_source"] == "WIKIPEDIA"
    assert result["places"][0]["ui_category"] == "other"


def test_region_discovery_uses_valid_supplied_coordinates_when_nominatim_unavailable():
    def handler(request):
        url = str(request.url)
        if "nominatim.openstreetmap.org" in url:
            return httpx.Response(503, text="Nominatim busy")
        if request.method == "POST":
            return httpx.Response(200, json={"elements": [
                {
                    "type": "node",
                    "id": 77,
                    "lat": 15.30,
                    "lon": 74.08,
                    "tags": {"name": "Supplied Area Museum", "tourism": "museum"},
                }
            ]})
        return httpx.Response(404)

    provider = _provider(handler)
    result = provider.discover_region_places(
        name="Goa", scope="region", lat=15.30, lon=74.08
    )
    assert result["status"] == "partial"
    assert result["area"]["source"] == "supplied_coordinates"
    assert result["places"][0]["name"] == "Supplied Area Museum"
    assert result["places"][0]["ui_category"] == "museum"


def test_region_discovery_all_providers_fail_raises_provider_error():
    def handler(request):
        url = str(request.url)
        if "nominatim.openstreetmap.org" in url:
            return httpx.Response(200, json=[{
                "osm_type": "relation",
                "osm_id": 1,
                "name": "Hampi",
                "type": "city",
                "lat": "15.335",
                "lon": "76.46",
                "display_name": "Hampi, Karnataka, India",
                "address": {"city": "Hampi", "state": "Karnataka", "country": "India"},
            }])
        return httpx.Response(503, text="unavailable")

    provider = _provider(handler)
    with pytest.raises(ProviderError):
        provider.discover_region_places(name="Hampi", scope="city")


def test_api_discover_region_endpoint_maps_errors_and_coordinates(monkeypatch):
    def handler(request):
        url = str(request.url)
        if "nominatim.openstreetmap.org" in url:
            if "UnknownPlace" in url:
                return httpx.Response(200, json=[])
            return httpx.Response(503)
        return httpx.Response(503)

    provider = _provider(handler)
    monkeypatch.setattr(api_module, "_get_live_provider", lambda: provider)

    # Half-specified coordinates return 422.
    with pytest.raises(HTTPException) as bad_coords:
        api_module.discover_region(name="Goa", scope="region", lat=15.3, lon=None, refresh=False)
    assert bad_coords.value.status_code == 422
    assert bad_coords.value.detail["code"] == "invalid_coordinates"

    # Unknown region returns 404.
    with pytest.raises(HTTPException) as not_found:
        api_module.discover_region(name="UnknownPlace", scope="region", lat=None, lon=None, refresh=False)
    assert not_found.value.status_code == 404
    assert not_found.value.detail["code"] == "region_not_found"

    # Unavailable provider returns 503.
    with pytest.raises(HTTPException) as unavailable:
        api_module.discover_region(name="Goa", scope="region", lat=None, lon=None, refresh=False)
    assert unavailable.value.status_code == 503
    assert unavailable.value.detail["code"] == "provider_unavailable"
