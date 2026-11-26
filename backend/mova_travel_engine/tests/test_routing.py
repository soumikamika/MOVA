import httpx

from app.providers.osrm import OSRMProvider, OSRMProviderConfig
from app.routing.service import RoutingService
from app.services.travel_method import TravelMethodService
from app.schemas.common import TransportPreference


def test_osrm_provider_parses_route():
    def handler(request):
        return httpx.Response(200, json={
            "code": "Ok",
            "routes": [{
                "distance": 12345,
                "duration": 2345,
                "geometry": {"coordinates": [[78.1, 17.4], [74.1, 15.4]]},
            }],
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OSRMProvider(OSRMProviderConfig(base_url="https://osrm.test"), client=client)
    result = provider.route(
        origin_latitude=17.4, origin_longitude=78.1,
        destination_latitude=15.4, destination_longitude=74.1,
        origin_name="Hyderabad", destination_name="Goa",
    )
    assert result.status == "available"
    assert result.distance_km == 12.35
    assert result.duration_minutes == 39.1
    assert result.source == "OSRM"
    assert result.geometry == [[78.1, 17.4], [74.1, 15.4]]


def test_routing_service_returns_unavailable_on_provider_failure():
    class BrokenProvider:
        def route(self, **kwargs):
            from app.core.exceptions import ProviderError
            raise ProviderError("provider down")

    result = RoutingService(provider=BrokenProvider()).route(
        origin_latitude=17.4, origin_longitude=78.1,
        destination_latitude=15.4, destination_longitude=74.1,
        origin_name="Hyderabad", destination_name="Goa",
    )
    assert result.status == "unavailable"
    assert result.source == "OSRM"


def test_routing_service_caches_successful_result():
    calls = {"count": 0}

    class Provider:
        def route(self, **kwargs):
            calls["count"] += 1
            from app.schemas.routing import RouteResult
            return RouteResult(
                origin="A", destination="B", distance_km=10,
                duration_minutes=20, source="OSRM", status="available",
            )

    service = RoutingService(provider=Provider())
    kwargs = dict(
        origin_latitude=1, origin_longitude=2,
        destination_latitude=3, destination_longitude=4,
        origin_name="A", destination_name="B",
    )
    service.route(**kwargs)
    service.route(**kwargs)
    assert calls["count"] == 1


def test_travel_method_marks_unsupported_modes_without_fabricating():
    from app.schemas.routing import RouteResult
    route = RouteResult(
        origin="Hyderabad", destination="Goa",
        distance_km=600, duration_minutes=720,
        source="OSRM", status="available",
    )
    result = TravelMethodService().recommend(
        distance_km=600, route=route,
        travellers=2,
    )
    assert result.recommended_mode == "car"
    assert next(x for x in result.options if x.mode == "train").status == "NOT_INTEGRATED"
    assert next(x for x in result.options if x.mode == "flight").estimated_cost_inr is None
