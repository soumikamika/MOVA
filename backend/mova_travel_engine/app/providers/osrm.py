"""OSRM routing provider.

The public OSRM demo service is used for development/hackathon routing. The
provider returns only data actually received from OSRM and never invents a
route when the provider fails.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.exceptions import ProviderError
from app.schemas.routing import RouteResult


@dataclass(frozen=True)
class OSRMProviderConfig:
    base_url: str = "https://router.project-osrm.org"
    profile: str = "driving"
    timeout_seconds: float = 20.0


class OSRMProvider:
    def __init__(self, config: OSRMProviderConfig | None = None, client: httpx.Client | None = None):
        self.config = config or OSRMProviderConfig()
        self._client = client or httpx.Client(
            timeout=self.config.timeout_seconds,
            headers={"User-Agent": "MOVA-Travel-Engine/1.0"},
        )

    def close(self) -> None:
        self._client.close()

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
        coordinates = (
            f"{origin_longitude},{origin_latitude};"
            f"{destination_longitude},{destination_latitude}"
        )
        url = f"{self.config.base_url}/route/v1/{self.config.profile}/{coordinates}"
        try:
            response = self._client.get(
                url,
                params={"overview": "full", "geometries": "geojson"},
            )
        except httpx.HTTPError as exc:
            raise ProviderError(
                "OSRM routing request failed",
                details={"error": str(exc)},
            ) from exc

        if response.status_code != 200:
            raise ProviderError(
                "OSRM returned an error",
                details={"status": response.status_code},
            )

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise ProviderError("OSRM returned invalid JSON") from exc

        if payload.get("code") != "Ok" or not payload.get("routes"):
            raise ProviderError(
                "OSRM did not return a route",
                details={"code": payload.get("code")},
            )

        route = payload["routes"][0]
        geometry = ((route.get("geometry") or {}).get("coordinates") or [])
        if not isinstance(geometry, list):
            geometry = []

        return RouteResult(
            origin=origin_name,
            destination=destination_name,
            distance_km=round(float(route["distance"]) / 1000.0, 2),
            duration_minutes=round(float(route["duration"]) / 60.0, 1),
            geometry=[
                [float(point[0]), float(point[1])]
                for point in geometry
                if isinstance(point, (list, tuple)) and len(point) >= 2
            ],
            source="OSRM",
            status="available",
            notes=["Live road route returned by OSRM."],
        )
