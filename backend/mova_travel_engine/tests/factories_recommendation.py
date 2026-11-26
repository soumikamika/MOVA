"""Recommendation-specific test builders (destination-agnostic; reuses tests/factories.py)."""
import datetime as dt

from app.schemas.common import ActivityLevel, TripType
from app.schemas.trip import TripRequest
from tests.factories import make_place

START = dt.date.today() + dt.timedelta(days=30)


def make_trip(**kw) -> TripRequest:
    base = dict(
        destination="Testville", start_date=START, end_date=START + dt.timedelta(days=4),
        travellers=3, trip_type=TripType.FRIENDS, budget=30000, interests=["beaches", "food", "nature"],
        dislikes=["clubs", "crowds"], transport_preference="flexible", activity_level=ActivityLevel.MODERATE,
        meal_preferences=["vegetarian"],
    )
    base.update(kw)
    return TripRequest(**base)
