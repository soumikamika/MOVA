import json
from datetime import timezone

import httpx

from app.providers.osm import OSMProvider, OSMProviderConfig
from app.schemas.common import DataSource, PlaceCategory


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": "MOVA-test/1.0"})


def test_nominatim_resolves_indian_destination():
    def handler(request):
        assert request.url.params["countrycodes"] == "in"
        return httpx.Response(200, json=[{
            "osm_type": "relation", "osm_id": 123,
            "name": "Hyderabad", "type": "city", "lat": "17.3850", "lon": "78.4867",
            "display_name": "Hyderabad, Telangana, India",
            "address": {"city": "Hyderabad", "state": "Telangana", "country": "India"},
        }])

    provider = OSMProvider(OSMProviderConfig(min_nominatim_interval_seconds=0), mock_client(handler))
    destination = provider.resolve_destination("Hyderabad")
    assert destination is not None
    assert destination.source == DataSource.EXTERNAL_API
    assert destination.name == "Hyderabad"
    assert destination.center.latitude == 17.385
    assert destination.state == "Telangana"


def test_overpass_records_keep_osm_facts_and_use_explicit_planning_estimates():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"elements": [
                {"type": "node", "id": 10, "lat": 17.4, "lon": 78.5,
                 "tags": {"name": "Example Museum", "tourism": "museum", "wikidata": "Q1"}},
                {"type": "way", "id": 11, "center": {"lat": 17.41, "lon": 78.51},
                 "tags": {"name": "Example Fort", "historic": "castle", "fee": "₹100"}},
            ]})
        return httpx.Response(500)

    provider = OSMProvider(OSMProviderConfig(min_nominatim_interval_seconds=0, planner_visit_minutes=75, planner_intensity=2), mock_client(handler))
    from app.schemas.place import Destination, GeoPoint
    destination = Destination(id="osm:relation:1", name="Hyderabad", center=GeoPoint(latitude=17.385, longitude=78.4867), source=DataSource.EXTERNAL_API)
    places = provider.discover_places(destination)
    assert len(places) == 2
    assert places[0].category == PlaceCategory.MUSEUM
    assert places[1].category == PlaceCategory.HISTORICAL
    assert places[1].entry_fee_inr == 100
    assert all(p.source == DataSource.EXTERNAL_API for p in places)
    assert all(p.avg_visit_minutes == 75 for p in places)
    assert all(p.intensity == 2 for p in places)
    assert "wikidata" in places[0].tags



def test_overpass_falls_back_when_primary_endpoint_is_unavailable():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if "overpass-api.de" in str(request.url):
            return httpx.Response(503, text="temporarily unavailable")
        return httpx.Response(200, json={"elements": [
            {"type": "node", "id": 99, "lat": 17.4, "lon": 78.5,
             "tags": {"name": "Fallback Fort", "historic": "fort"}}
        ]})

    provider = OSMProvider(
        OSMProviderConfig(
            min_nominatim_interval_seconds=0,
            overpass_fallback_urls=("https://overpass.kumi.systems/api/interpreter",),
        ),
        mock_client(handler),
    )
    from app.schemas.place import Destination, GeoPoint
    destination = Destination(
        id="osm:relation:1", name="Hyderabad",
        center=GeoPoint(latitude=17.385, longitude=78.4867),
        source=DataSource.EXTERNAL_API,
    )
    places = provider.discover_places(destination)
    assert len(places) == 1
    assert places[0].name == "Fallback Fort"
    assert len(calls) == 2


def test_overpass_error_reports_each_failed_endpoint():
    def handler(request):
        return httpx.Response(503, text="busy")

    provider = OSMProvider(
        OSMProviderConfig(
            min_nominatim_interval_seconds=0,
            overpass_fallback_urls=("https://overpass.kumi.systems/api/interpreter",),
        ),
        mock_client(handler),
    )
    from app.core.exceptions import ProviderError
    from app.schemas.place import GeoPoint
    import pytest
    with pytest.raises(ProviderError) as error:
        provider._overpass(GeoPoint(latitude=17.385, longitude=78.4867))
    assert len(error.value.details["attempts"]) == 2
    assert all(item["status"] == 503 for item in error.value.details["attempts"])


def test_wikipedia_geosearch_is_used_when_all_overpass_servers_fail():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.host))
        if request.method == "POST":
            return httpx.Response(503, text="Overpass busy")
        assert request.url.host == "en.wikipedia.org"
        return httpx.Response(200, json={"query": {"pages": [{
            "pageid": 1234,
            "title": "Charminar",
            "description": "Monument in Hyderabad, India",
            "fullurl": "https://en.wikipedia.org/wiki/Charminar",
            "coordinates": [{"lat": 17.3616, "lon": 78.4747}],
        }]}})

    provider = OSMProvider(
        OSMProviderConfig(
            min_nominatim_interval_seconds=0,
            overpass_fallback_urls=("https://overpass.kumi.systems/api/interpreter",),
        ),
        mock_client(handler),
    )
    from app.schemas.place import Destination, GeoPoint
    destination = Destination(
        id="osm:relation:1", name="Hyderabad",
        center=GeoPoint(latitude=17.385, longitude=78.4867),
        source=DataSource.EXTERNAL_API,
    )
    places = provider.discover_places(destination)
    assert len(places) == 1
    assert places[0].name == "Charminar"
    assert places[0].source == DataSource.EXTERNAL_API
    assert places[0].category == PlaceCategory.CULTURAL
    assert places[0].location.latitude == 17.3616
    assert "wikipedia" in places[0].tags
    assert len(calls) == 3


def test_wikipedia_geosearch_reports_http_failure():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(503, text="Overpass busy")
        return httpx.Response(429, text="rate limited")

    provider = OSMProvider(
        OSMProviderConfig(
            min_nominatim_interval_seconds=0,
            overpass_fallback_urls=("https://overpass.kumi.systems/api/interpreter",),
        ),
        mock_client(handler),
    )
    from app.core.exceptions import ProviderError
    from app.schemas.place import Destination, GeoPoint
    import pytest
    destination = Destination(
        id="osm:relation:1", name="Hyderabad",
        center=GeoPoint(latitude=17.385, longitude=78.4867),
        source=DataSource.EXTERNAL_API,
    )
    with pytest.raises(ProviderError) as error:
        provider.discover_places(destination)
    assert error.value.details["wikipedia"]["status"] == 429
