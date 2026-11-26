"""Live OpenStreetMap discovery provider for the MOVA planner.

This adapter deliberately keeps provider concerns outside the planner/repository
layers.  Nominatim resolves a destination; Overpass discovers nearby tourism
POIs.  OSM facts are never converted into fake ratings, prices, popularity or
opening hours.

Two planner fields (visit duration and intensity) are not normally supplied by
OSM.  The planner therefore uses explicitly-labelled planning estimates for
those two fields so the deterministic optimizer can schedule live POIs.  These
are assumptions for scheduling, NOT claims about the real place.

The public Nominatim service is rate-limited, so this provider has a small
in-memory TTL cache and enforces a minimum interval between Nominatim calls.
For production, configure a dedicated provider/proxy or self-hosted service.
"""
from __future__ import annotations

import math
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.exceptions import NotFoundError, ProviderError
from app.core.logging import get_logger
from app.schemas.common import DataSource, PlaceCategory
from app.schemas.place import Destination, GeoPoint, Place

logger = get_logger(__name__)

_NON_ATTRACTION_WIKI_PREFIXES = (
    "list of ",
    "index of ",
    "timeline of ",
    "outline of ",
    "history of ",
    "demographics of ",
    "economy of ",
    "geography of ",
    "politics of ",
    "culture of ",
    "category:",
    "template:",
)
_LODGING_TOURISM_VALUES = {"hotel", "hostel", "guest_house", "motel", "apartment", "chalet"}


@dataclass(frozen=True)
class OSMProviderConfig:
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    overpass_fallback_urls: tuple[str, ...] = (
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
    )
    wikipedia_api_url: str = "https://en.wikipedia.org/w/api.php"
    wikipedia_summary_url: str = "https://en.wikipedia.org/api/rest_v1/page/summary/"
    user_agent: str = "MOVA-Travel-Engine/1.0 (https://github.com/mova-travel/mova)"
    cache_ttl_seconds: int = 21600
    min_nominatim_interval_seconds: float = 1.05
    search_radius_m: int = 20000
    max_places: int = 80
    planner_visit_minutes: int = 90
    planner_intensity: int = 2
    timeout_seconds: float = 14.0
    overpass_timeout_seconds: int = 12
    summary_timeout_seconds: float = 4.5


class OSMProvider:
    """Small, testable live-data adapter for Nominatim + Overpass."""

    def __init__(self, config: OSMProviderConfig | None = None, client: httpx.Client | None = None):
        self.config = config or OSMProviderConfig()
        self._client = client or httpx.Client(
            timeout=self.config.timeout_seconds,
            headers={"User-Agent": self.config.user_agent, "Accept": "application/json"},
        )
        self._cache: dict[tuple[str, str], tuple[float, Any]] = {}
        self._last_nominatim = 0.0
        self._lock = threading.Lock()

    def close(self) -> None:
        self._client.close()

    def _cached(self, key: tuple[str, ...]) -> Any | None:
        with self._lock:
            row = self._cache.get(key)
            if row and time.monotonic() - row[0] < self.config.cache_ttl_seconds:
                return row[1]
            return None

    def _put(self, key: tuple[str, ...], value: Any) -> Any:
        with self._lock:
            self._cache[key] = (time.monotonic(), value)
        return value

    def _nominatim_get(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        with self._lock:
            wait = self.config.min_nominatim_interval_seconds - (time.monotonic() - self._last_nominatim)
            if wait > 0:
                time.sleep(wait)
            try:
                response = self._client.get(self.config.nominatim_url, params=params)
                self._last_nominatim = time.monotonic()
            except httpx.HTTPError as exc:
                logger.warning("Nominatim request failed: %s", exc)
                raise ProviderError("Nominatim request failed", details={"error": str(exc)}) from exc
        if response.status_code != 200:
            logger.warning("Nominatim returned HTTP %s", response.status_code)
            raise ProviderError("Nominatim returned an error", details={"status": response.status_code})
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("Nominatim returned invalid JSON") from exc
        if not isinstance(payload, list):
            raise ProviderError("Nominatim returned an unexpected response")
        return payload

    @staticmethod
    def _pick_nominatim_row(results: list[dict[str, Any]], query: str, scope: str = "region") -> dict[str, Any] | None:
        if not results:
            return None
        preferred_types = (
            {"city", "town", "village", "municipality", "suburb", "administrative"}
            if scope == "city"
            else {"state", "administrative", "region", "city", "town", "county"}
        )
        preferred_addresstypes = (
            {"city", "town", "village", "municipality", "suburb"}
            if scope == "city"
            else {"state", "region", "province", "county", "city", "town"}
        )
        norm_query = query.strip().casefold()

        def rank_key(row: dict[str, Any]) -> tuple[int, int, float]:
            row_name = str(row.get("name") or "").strip().casefold()
            display = str(row.get("display_name") or "").strip().casefold()
            exact_match = 0 if (row_name == norm_query or display.startswith(f"{norm_query},") or display == norm_query) else 1
            type_match = 0 if (
                str(row.get("type") or "").lower() in preferred_types
                or str(row.get("addresstype") or "").lower() in preferred_addresstypes
            ) else 1
            try:
                importance = -float(row.get("importance") or 0.0)
            except (TypeError, ValueError):
                importance = 0.0
            return (exact_match, type_match, importance)

        return min(results, key=rank_key)

    def _resolve_nominatim_row(self, query: str, scope: str = "region") -> dict[str, Any] | None:
        normalized = query.strip().casefold()
        if not normalized:
            return None
        key = ("nominatim_row", normalized, scope)
        cached = self._cached(key)
        if cached is not None:
            return cached
        results = self._nominatim_get({
            "q": f"{query.strip()}, India",
            "format": "jsonv2",
            "limit": 8,
            "countrycodes": "in",
            "addressdetails": 1,
        })
        row = self._pick_nominatim_row(results, query, scope=scope)
        if row is not None:
            self._put(key, row)
        return row

    @staticmethod
    def _destination_from_nominatim(row: dict[str, Any], query: str) -> Destination | None:
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
        except (KeyError, TypeError, ValueError):
            return None
        address = row.get("address") or {}
        name = address.get("city") or address.get("town") or address.get("village") or address.get("state") or row.get("name") or query
        state = address.get("state")
        osm_type = row.get("osm_type", "unknown")
        osm_id = row.get("osm_id", "unknown")
        return Destination(
            id=f"osm:{osm_type}:{osm_id}",
            name=str(name)[:100],
            state=state,
            country="India",
            center=GeoPoint(latitude=lat, longitude=lon),
            aliases=[query] if str(name).casefold() != query.strip().casefold() else [],
            description=row.get("display_name"),
            source=DataSource.EXTERNAL_API,
            last_updated=datetime.now(timezone.utc),
            confidence=0.8,
        )

    def resolve_destination(self, query: str) -> Destination | None:
        normalized = query.strip().casefold()
        if not normalized:
            return None
        key = ("destination", normalized)
        cached = self._cached(key)
        if cached is not None:
            return cached
        row = self._resolve_nominatim_row(query, scope="region")
        if not row:
            return None
        dest = self._destination_from_nominatim(row, query)
        if dest is not None:
            self._put(key, dest)
        return dest

    def discover_places(self, destination: Destination) -> list[Place]:
        key = ("places", destination.id)
        cached = self._cached(key)
        if cached is not None:
            rows = cached
        else:
            try:
                rows = self._put(key, self._overpass(destination.center))
            except ProviderError as overpass_error:
                # Overpass instances can be rate-limited or blocked on some
                # networks. Use Wikipedia's geosearch as an independent,
                # real-world source rather than failing the entire plan.
                try:
                    wiki_rows = self._wikipedia_places(destination.center)
                except ProviderError as wiki_error:
                    raise ProviderError(
                        "OpenStreetMap Overpass and Wikipedia geosearch are both unavailable",
                        details={"overpass": overpass_error.details, "wikipedia": wiki_error.details},
                    ) from wiki_error
                if not wiki_rows:
                    raise ProviderError(
                        "OpenStreetMap Overpass is unavailable and Wikipedia returned no nearby place articles",
                        details={"overpass": overpass_error.details, "wikipedia": {"results": 0}},
                    ) from overpass_error
                rows = self._put(key, wiki_rows)
        places: list[Place] = []
        seen_names: set[str] = set()
        for row in rows:
            tags = row.get("tags") or {}
            name = str(tags.get("name") or "").strip()
            if not name:
                continue
            name_key = name.casefold()
            if name_key in seen_names:
                continue
            lat, lon = self._element_point(row)
            if lat is None or lon is None:
                continue
            category = self._category(tags)
            osm_kind = tags.get("tourism") or tags.get("historic") or tags.get("natural") or tags.get("leisure") or tags.get("amenity") or "osm"
            osm_id = f"{row.get('type','element')}:{row.get('id','unknown')}"
            fee = self._numeric_fee(tags.get("fee"))
            record = Place(
                id=f"osm:{osm_id}",
                destination_id=destination.id,
                name=name[:150],
                category=category,
                tags=self._tags(tags, osm_kind),
                location=GeoPoint(latitude=lat, longitude=lon),
                entry_fee_inr=fee,
                # OSM generally does not provide visit duration/intensity.
                # These are explicitly documented planner assumptions.
                avg_visit_minutes=self.config.planner_visit_minutes,
                intensity=self.config.planner_intensity,
                description=tags.get("description") or tags.get("official_name"),
                source=DataSource.EXTERNAL_API,
                last_updated=datetime.now(timezone.utc),
                confidence=0.7,
            )
            places.append(record)
            seen_names.add(name_key)
            if len(places) >= self.config.max_places:
                break
        return places

    def _wikipedia_places(self, center: GeoPoint, *, radius_m: int | None = None) -> list[dict[str, Any]]:
        radius = min(radius_m or self.config.search_radius_m, 10000)
        params = {
            "action": "query",
            "generator": "geosearch",
            "ggscoord": f"{center.latitude}|{center.longitude}",
            "ggsradius": radius,
            "ggslimit": 50,
            "prop": "coordinates|description|info",
            "inprop": "url",
            "format": "json",
            "formatversion": 2,
        }
        try:
            response = self._client.get(self.config.wikipedia_api_url, params=params)
        except httpx.HTTPError as exc:
            logger.warning("Wikipedia geosearch failed: %s", exc)
            raise ProviderError("Wikipedia geosearch request failed", details={"error": str(exc)}) from exc
        if response.status_code != 200:
            logger.warning("Wikipedia geosearch returned HTTP %s", response.status_code)
            raise ProviderError("Wikipedia geosearch returned an error", details={"status": response.status_code})
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("Wikipedia geosearch returned invalid JSON") from exc
        pages = (payload.get("query") or {}).get("pages") if isinstance(payload, dict) else None
        if not isinstance(pages, list):
            raise ProviderError("Wikipedia geosearch returned an unexpected response")
        rows = []
        for page in pages:
            coords = page.get("coordinates") or []
            title = str(page.get("title") or "").strip()
            if not coords or not title:
                continue
            if title.casefold().startswith(_NON_ATTRACTION_WIKI_PREFIXES):
                continue
            coord = coords[0]
            rows.append({
                "type": "wikipedia", "id": page.get("pageid", title),
                "lat": coord.get("lat"), "lon": coord.get("lon"),
                "tags": {
                    "name": title,
                    "description": page.get("description"),
                    "wikipedia": page.get("fullurl") or f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    "tourism": "attraction",
                    "_provider_source": "WIKIPEDIA",
                },
            })
        return rows

    def _wikipedia_summary(self, title: str) -> tuple[str | None, str | None]:
        cleaned = str(title or "").strip()
        if not cleaned:
            return None, None
        key = ("wiki_summary", cleaned.casefold())
        cached = self._cached(key)
        if cached is not None:
            return cached
        slug = cleaned.replace(" ", "_")
        url = f"{self.config.wikipedia_summary_url}{httpx.URL(slug)}"
        try:
            response = self._client.get(url, timeout=self.config.summary_timeout_seconds)
            if response.status_code != 200:
                return None, None
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("type") == "disambiguation":
                return None, None
            extract = str(payload.get("extract") or "").strip() or None
            page_url = ((payload.get("content_urls") or {}).get("desktop") or {}).get("page")
            result = (extract, page_url)
            if extract:
                self._put(key, result)
            return result
        except (httpx.HTTPError, ValueError):
            return None, None

    def _overpass(
        self,
        center: GeoPoint,
        *,
        radius_m: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        radius = radius_m or self.config.search_radius_m
        out_clause = f"out center tags {limit};" if limit else "out center tags;"
        q = f"""[out:json][timeout:{self.config.overpass_timeout_seconds}];
(
  nw(around:{radius},{center.latitude},{center.longitude})[tourism~"^(attraction|museum|viewpoint|artwork|gallery|zoo|aquarium|theme_park|information)$"];
  nw(around:{radius},{center.latitude},{center.longitude})[historic];
  nw(around:{radius},{center.latitude},{center.longitude})[natural~"^(beach|waterfall|peak|cave|cave_entrance|valley|lake|hot_spring|spring|wood)$"];
  nw(around:{radius},{center.latitude},{center.longitude})[leisure~"^(park|nature_reserve|water_park|garden)$"];
  nw(around:{radius},{center.latitude},{center.longitude})["amenity"="place_of_worship"];
);
{out_clause}"""
        endpoints = tuple(dict.fromkeys((self.config.overpass_url, *self.config.overpass_fallback_urls)))
        failures: list[dict[str, Any]] = []
        for endpoint in endpoints:
            try:
                response = self._client.post(endpoint, data={"data": q})
            except httpx.HTTPError as exc:
                logger.warning("Overpass endpoint %s failed: %s", endpoint, exc)
                failures.append({"endpoint": endpoint, "error": str(exc)})
                continue
            if response.status_code != 200:
                logger.warning("Overpass endpoint %s returned HTTP %s", endpoint, response.status_code)
                failures.append({"endpoint": endpoint, "status": response.status_code})
                continue
            try:
                payload = response.json()
            except ValueError:
                failures.append({"endpoint": endpoint, "error": "invalid JSON"})
                continue
            elements = payload.get("elements") if isinstance(payload, dict) else None
            if isinstance(elements, list):
                return elements
            failures.append({"endpoint": endpoint, "error": "unexpected response"})
        raise ProviderError(
            "All OpenStreetMap Overpass endpoints failed",
            details={"provider": "Overpass", "attempts": failures},
        )

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        )
        return 2 * r * math.asin(math.sqrt(min(1.0, a)))

    @staticmethod
    def _wikipedia_url_from_tag(value: Any) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        if raw.startswith(("http://", "https://")):
            return raw
        if ":" in raw:
            lang, title = raw.split(":", 1)
            lang = lang.strip() or "en"
            title = title.strip().replace(" ", "_")
        else:
            lang = "en"
            title = raw.replace(" ", "_")
        return f"https://{lang}.wikipedia.org/wiki/{title}" if title else None

    @staticmethod
    def _image_url_from_tags(tags: dict[str, Any]) -> str | None:
        raw = str(tags.get("image") or tags.get("wikimedia_image") or "").strip()
        if raw.startswith(("http://", "https://")):
            return raw
        return None

    @staticmethod
    def _ui_category(category: PlaceCategory, tags: dict[str, Any]) -> str:
        text = " ".join(
            str(v)
            for v in (
                tags.get("tourism"),
                tags.get("historic"),
                tags.get("natural"),
                tags.get("leisure"),
                tags.get("amenity"),
                tags.get("name"),
            )
            if v
        ).lower()
        if category == PlaceCategory.RELIGIOUS or "place_of_worship" in text:
            return "temples"
        if category == PlaceCategory.MUSEUM or "museum" in text:
            return "museum"
        if category == PlaceCategory.HISTORICAL or tags.get("historic"):
            return "heritage"
        if category in {
            PlaceCategory.BEACH,
            PlaceCategory.WATERFALL,
            PlaceCategory.VIEWPOINT,
            PlaceCategory.NATURE,
            PlaceCategory.PARK,
            PlaceCategory.WILDLIFE,
        }:
            return "nature"
        if category == PlaceCategory.CULTURAL and any(
            word in text for word in ("fort", "palace", "monument", "heritage", "memorial", "temple", "ruins")
        ):
            return "temples" if "temple" in text else "heritage"
        return "other"

    @staticmethod
    def _region_place_score(tags: dict[str, Any], name: str, ui_category: str, has_wiki: bool) -> int:
        score = 0
        if has_wiki:
            score += 45
        if tags.get("wikidata"):
            score += 20
        if tags.get("image") or tags.get("wikimedia_commons") or tags.get("wikimedia_image"):
            score += 16
        if tags.get("description") or tags.get("description:en"):
            score += 12
        if tags.get("website") or tags.get("contact:website"):
            score += 5
        if tags.get("opening_hours"):
            score += 3
        tourism = str(tags.get("tourism") or "").lower()
        historic = str(tags.get("historic") or "").lower()
        natural = str(tags.get("natural") or "").lower()
        if tourism in {"attraction", "museum", "viewpoint"}:
            score += 24
        elif tourism in {"artwork", "theme_park", "zoo", "aquarium", "gallery"}:
            score += 18
        if historic in {"monument", "fort", "palace", "castle", "archaeological_site", "ruins", "memorial"}:
            score += 23
        if natural in {"beach", "waterfall", "national_park", "cave_entrance", "hot_spring", "peak"}:
            score += 22
        if tags.get("amenity") == "place_of_worship":
            score += 8
        if ui_category != "other":
            score += 8
        if len(name) < 4 or name[0].isdigit() or re.match(r"^(unnamed|unknown|no name|unnamed road)$", name, re.I):
            score -= 45
        if re.match(r"^(shop|restaurant|bus stop|parking|building|residential area)$", name.strip(), re.I):
            score -= 18
        return score

    def _serialize_region_place(
        self,
        row: dict[str, Any],
        destination: Destination,
        *,
        is_fallback: bool = False,
    ) -> tuple[dict[str, Any], int, float] | None:
        tags = row.get("tags") or {}
        name = str(tags.get("name") or tags.get("name:en") or "").strip()
        if not name:
            return None
        tourism = str(tags.get("tourism") or "").lower()
        if tourism in _LODGING_TOURISM_VALUES and not tags.get("historic"):
            return None
        lat, lon = self._element_point(row)
        if lat is None or lon is None:
            return None
        category = self._category(tags)
        ui_category = "other" if is_fallback else self._ui_category(category, tags)
        raw_type = (
            "Wikipedia Article"
            if is_fallback
            else (
                tags.get("tourism")
                or tags.get("historic")
                or tags.get("natural")
                or tags.get("leisure")
                or tags.get("amenity")
                or "place"
            )
        )
        type_label = str(raw_type).replace("_", " ").title()
        osm_type = str(row.get("type") or "element")
        osm_raw_id = str(row.get("id") or "unknown")
        osm_id = f"{osm_type}:{osm_raw_id}"
        wiki_url = self._wikipedia_url_from_tag(tags.get("wikipedia"))
        source_url = (
            wiki_url
            if is_fallback
            else f"https://www.openstreetmap.org/{osm_type}/{osm_raw_id}"
        )
        fee = self._numeric_fee(tags.get("fee"))
        osm_kind = tags.get("tourism") or tags.get("historic") or tags.get("natural") or tags.get("leisure") or tags.get("amenity") or "osm"
        place_model = Place(
            id=f"osm:{osm_id}",
            destination_id=destination.id,
            name=name[:150],
            category=PlaceCategory.OTHER if is_fallback else category,
            tags=self._tags(tags, osm_kind),
            location=GeoPoint(latitude=lat, longitude=lon),
            entry_fee_inr=fee,
            avg_visit_minutes=self.config.planner_visit_minutes,
            intensity=self.config.planner_intensity,
            description=tags.get("description") or tags.get("description:en") or tags.get("official_name"),
            source=DataSource.EXTERNAL_API,
            last_updated=datetime.now(timezone.utc),
            confidence=0.45 if is_fallback else 0.75,
        )
        payload = place_model.model_dump(mode="json")
        payload.update({
            "osm_id": osm_id,
            "type": type_label,
            "ui_category": ui_category,
            "wikipedia_url": wiki_url,
            "source_url": source_url,
            "website": tags.get("website") or tags.get("contact:website"),
            "opening_hours": tags.get("opening_hours"),
            "image_url": self._image_url_from_tags(tags),
            "provider_source": "WIKIPEDIA" if is_fallback else "OPENSTREETMAP",
            "is_fallback": is_fallback,
        })
        score = self._region_place_score(tags, name, ui_category, bool(wiki_url))
        dist = self._haversine_km(destination.center.latitude, destination.center.longitude, lat, lon)
        return payload, score, dist

    def discover_region_places(
        self,
        *,
        name: str,
        scope: str = "region",
        lat: float | None = None,
        lon: float | None = None,
        refresh: bool = False,
        primary_limit: int = 36,
        nearby_limit: int = 12,
    ) -> dict[str, Any]:
        cleaned_name = str(name or "").strip()
        if len(cleaned_name) < 2:
            raise NotFoundError("Region name must be at least 2 characters.", details={"name": name})
        lat_key = f"{lat:.3f}" if lat is not None else "none"
        lon_key = f"{lon:.3f}" if lon is not None else "none"
        cache_key = ("region_discover", cleaned_name.casefold(), scope, lat_key, lon_key)
        if not refresh:
            cached = self._cached(cache_key)
            if cached is not None:
                logger.info("Region discovery cache hit for %s (%s)", cleaned_name, scope)
                return {**cached, "cache_hit": True}

        warnings: list[str] = []
        providers_used: list[str] = []
        bbox: list[float] | None = None
        destination: Destination | None = None
        area_source = DataSource.EXTERNAL_API.value

        try:
            row = self._resolve_nominatim_row(cleaned_name, scope=scope)
            if row is not None:
                destination = self._destination_from_nominatim(row, cleaned_name)
                providers_used.append("nominatim")
                raw_bbox = row.get("boundingbox")
                if isinstance(raw_bbox, list) and len(raw_bbox) >= 4:
                    try:
                        bbox = [float(raw_bbox[0]), float(raw_bbox[1]), float(raw_bbox[2]), float(raw_bbox[3])]
                    except (TypeError, ValueError):
                        bbox = None
        except ProviderError as exc:
            logger.warning("Nominatim resolution failed for %s: %s", cleaned_name, exc.message)
            if lat is not None and lon is not None:
                warnings.append("Geocoder (Nominatim) was temporarily unavailable; using supplied coordinates.")
            else:
                raise

        if destination is None:
            if lat is not None and lon is not None:
                area_source = "supplied_coordinates"
                destination = Destination(
                    id=f"region-coordinate:{scope}:{cleaned_name.casefold().replace(' ', '-')}",
                    name=cleaned_name[:100],
                    country="India",
                    center=GeoPoint(latitude=lat, longitude=lon),
                    description=f"{cleaned_name} (centered on supplied coordinates)",
                    source=DataSource.EXTERNAL_API,
                    last_updated=datetime.now(timezone.utc),
                    confidence=0.6,
                )
            else:
                raise NotFoundError(
                    f"No matching Indian region or city was found for '{cleaned_name}'.",
                    details={"name": cleaned_name, "scope": scope},
                )

        inner_km = 25.0 if scope == "city" else 40.0
        query_radius_m = 30000 if scope == "city" else 45000
        is_fallback = False
        raw_rows: list[dict[str, Any]] = []

        try:
            raw_rows = self._overpass(destination.center, radius_m=query_radius_m, limit=140)
            providers_used.append("overpass")
        except ProviderError as overpass_error:
            logger.warning("Overpass failed for %s (%s): %s", destination.name, scope, overpass_error.message)
            try:
                raw_rows = self._wikipedia_places(destination.center, radius_m=10000)
                is_fallback = True
                providers_used.append("wikipedia_geosearch")
                warnings.append(
                    "OpenStreetMap Overpass is temporarily unavailable. Showing nearby Wikipedia article locations as a fallback."
                )
            except ProviderError as wiki_error:
                raise ProviderError(
                    "OpenStreetMap Overpass and Wikipedia geosearch are both unavailable",
                    details={"overpass": overpass_error.details, "wikipedia": wiki_error.details},
                ) from wiki_error
            if not raw_rows:
                raise ProviderError(
                    "OpenStreetMap Overpass is unavailable and Wikipedia returned no nearby place articles",
                    details={"overpass": overpass_error.details, "wikipedia": {"results": 0}},
                ) from overpass_error

        deduped: dict[str, tuple[dict[str, Any], int, float]] = {}
        for row in raw_rows:
            item = self._serialize_region_place(row, destination, is_fallback=is_fallback)
            if item is None:
                continue
            payload, score, dist = item
            if score <= -10 or len(payload["name"].strip()) < 2:
                continue
            oid = payload["osm_id"]
            existing = deduped.get(oid)
            if existing is None or score > existing[1]:
                deduped[oid] = (payload, score, dist)

        # Remove same-name duplicates within 500 m (e.g. node + way for the same landmark).
        ranked_items = sorted(
            deduped.values(),
            key=lambda entry: (-entry[1], entry[2], entry[0]["name"].casefold()),
        )
        unique_items: list[tuple[dict[str, Any], int, float]] = []
        for payload, score, dist in ranked_items:
            norm_name = re.sub(r"[^a-z0-9]+", " ", payload["name"].casefold()).strip()
            p_lat = payload["location"]["latitude"]
            p_lon = payload["location"]["longitude"]
            if any(
                re.sub(r"[^a-z0-9]+", " ", existing_p["name"].casefold()).strip() == norm_name
                and self._haversine_km(
                    existing_p["location"]["latitude"],
                    existing_p["location"]["longitude"],
                    p_lat,
                    p_lon,
                )
                <= 0.5
                for existing_p, _, _ in unique_items
            ):
                continue
            unique_items.append((payload, score, dist))

        if is_fallback:
            places = [item[0] for item in unique_items[:primary_limit]]
            nearby_places: list[dict[str, Any]] = []
        else:
            inner_items = [item for item in unique_items if item[2] <= inner_km]
            outer_items = [item for item in unique_items if item[2] > inner_km]
            primary_items = inner_items[:primary_limit]
            if len(primary_items) < 3:
                needed = min(3, primary_limit) - len(primary_items)
                primary_items.extend(outer_items[:needed])
                overflow_items = outer_items[needed:]
            else:
                overflow_items = inner_items[primary_limit:] + outer_items
            places = [item[0] for item in primary_items]
            nearby_places = [item[0] for item in overflow_items[:nearby_limit]]

        summary, summary_url = self._wikipedia_summary(destination.name)
        if summary:
            providers_used.append("wikipedia_summary")

        if not places:
            status = "empty"
            message = f"No mapped tourist places were found around {destination.name} from OpenStreetMap."
        elif warnings:
            status = "partial"
            message = warnings[0]
        else:
            status = "ok"
            message = None

        result = {
            "status": status,
            "area": {
                "name": destination.name,
                "display_name": destination.description or destination.name,
                "summary": summary,
                "summary_url": summary_url,
                "lat": destination.center.latitude,
                "lon": destination.center.longitude,
                "source": area_source,
                "scope": scope,
                "bbox": bbox,
            },
            "places": places,
            "nearby_places": nearby_places,
            "provider": "Wikipedia Geosearch (Fallback)" if is_fallback else "OpenStreetMap (Overpass & Nominatim)",
            "providers_used": providers_used,
            "warnings": warnings,
            "cache_hit": False,
            "message": message,
        }
        if status == "ok" or (status == "empty" and not warnings):
            self._put(cache_key, result)
        return result

    @staticmethod
    def _element_point(row: dict[str, Any]) -> tuple[float | None, float | None]:
        if row.get("lat") is not None and row.get("lon") is not None:
            return float(row["lat"]), float(row["lon"])
        center = row.get("center") or {}
        if center.get("lat") is not None and center.get("lon") is not None:
            return float(center["lat"]), float(center["lon"])
        return None, None

    @staticmethod
    def _category(tags: dict[str, Any]) -> PlaceCategory:
        tourism = str(tags.get("tourism") or "").lower()
        historic = str(tags.get("historic") or "").lower()
        natural = str(tags.get("natural") or "").lower()
        leisure = str(tags.get("leisure") or "").lower()
        amenity = str(tags.get("amenity") or "").lower()
        if amenity == "place_of_worship": return PlaceCategory.RELIGIOUS
        if natural == "beach": return PlaceCategory.BEACH
        if natural in {"waterfall", "spring"}: return PlaceCategory.WATERFALL
        if natural in {"peak", "cliff"}: return PlaceCategory.VIEWPOINT
        if natural in {"cave", "cave_entrance", "nature_reserve", "lake", "wood", "valley", "hot_spring"} or leisure == "nature_reserve": return PlaceCategory.NATURE
        if historic: return PlaceCategory.HISTORICAL
        if tourism in {"museum", "gallery"}: return PlaceCategory.MUSEUM
        if tourism in {"zoo", "aquarium", "theme_park"}: return PlaceCategory.ENTERTAINMENT
        if tourism in {"viewpoint"}: return PlaceCategory.VIEWPOINT
        if tourism in {"attraction", "artwork", "heritage"}: return PlaceCategory.CULTURAL
        if tourism == "park" or leisure in {"park", "water_park", "garden"}: return PlaceCategory.PARK
        return PlaceCategory.OTHER

    @staticmethod
    def _numeric_fee(value: Any) -> float | None:
        if value is None or str(value).strip().lower() in {"", "no", "free", "0"}:
            return 0.0 if value is not None else None
        match = re.search(r"(?:₹|inr|rs\.?\s*)?\s*(\d+(?:\.\d+)?)", str(value), re.I)
        return float(match.group(1)) if match else None

    @staticmethod
    def _tags(tags: dict[str, Any], kind: str) -> list[str]:
        out = {"osm", str(kind).lower()}
        if tags.get("wikidata"): out.add("wikidata")
        if tags.get("wikipedia"): out.add("wikipedia")
        if tags.get("website"): out.add("website")
        return sorted(out)
