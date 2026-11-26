"""Geographic helpers (pure functions, no schema dependencies)."""
import math

EARTH_RADIUS_KM = 6371.0088

# Deliberately coarse bounding box of India incl. islands. It catches swapped
# lat/lng and wrong-country coordinates; it is NOT a border test.
INDIA_LAT_RANGE = (6.0, 37.6)
INDIA_LNG_RANGE = (68.0, 97.5)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle (straight-line) distance in km. NOT road distance."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def is_within_india_bounds(lat: float, lng: float) -> bool:
    return (
        INDIA_LAT_RANGE[0] <= lat <= INDIA_LAT_RANGE[1]
        and INDIA_LNG_RANGE[0] <= lng <= INDIA_LNG_RANGE[1]
    )
