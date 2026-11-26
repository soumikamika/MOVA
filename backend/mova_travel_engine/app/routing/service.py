"""Routing service with provider isolation and small in-memory caching."""
from __future__ import annotations

import time
from dataclasses import dataclass

from app.core.exceptions import ProviderError
from app.providers.osrm import OSRMProvider
from app.schemas.routing import RouteResult


@dataclass(frozen=True)
class RoutingServiceConfig:
    cache_ttl_seconds: int = 3600


class RoutingService:
    def __init__(
        self,
        provider: OSRMProvider | None = None,
        config: RoutingServiceConfig | None = None,
    ):
        self.provider = provider or OSRMProvider()
        self.config = config or RoutingServiceConfig()
        self._cache: dict[tuple[float, float, float, float], tuple[float, RouteResult]] = {}

    def route(
        self,
        *,
        origin_latitude: float,
        origin_longitude: float,
        destination_latitude: float,
        destination_longitude: float,
        origin_name: str,
        destination_name: str,
    ) -> RouteResult:
        key = (
            round(origin_latitude, 6),
            round(origin_longitude, 6),
            round(destination_latitude, 6),
            round(destination_longitude, 6),
        )
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < self.config.cache_ttl_seconds:
            return cached[1].model_copy(update={"notes": ["Returned from routing cache."]})

        try:
            result = self.provider.route(
                origin_latitude=origin_latitude,
                origin_longitude=origin_longitude,
                destination_latitude=destination_latitude,
                destination_longitude=destination_longitude,
                origin_name=origin_name,
                destination_name=destination_name,
            )
        except ProviderError as exc:
            return RouteResult(
                origin=origin_name,
                destination=destination_name,
                status="unavailable",
                source="OSRM",
                notes=[exc.message],
            )

        self._cache[key] = (time.monotonic(), result)
        return result
