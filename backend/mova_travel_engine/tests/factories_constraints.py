"""Builders for constraint-engine tests. A fictional destination on purpose -
the constraint engine must not depend on any real destination."""
import datetime as dt

from app.constraints.context import ConstraintContext
from app.schemas.itinerary import DayPlan, Itinerary, ItineraryItem
from app.schemas.place import GeoPoint, OpeningHours, Place, Restaurant
from app.schemas.trip import TripRequest

START = dt.date.today() + dt.timedelta(days=30)
CENTER = {"latitude": 15.5, "longitude": 73.8}


def make_trip(**kw):
    base = dict(
        destination="Testville", start_date=START, end_date=START, travellers=2, trip_type="friends",
        budget=10000, interests=[], dislikes=[], activity_level="moderate", transport_preference="flexible",
    )
    base.update(kw)
    return TripRequest(**base)


def make_place(**kw):
    base = dict(
        id="p1", destination_id="testville", name="Test Place", category="beach", tags=[],
        location=CENTER, avg_visit_minutes=60, intensity=2, opening_hours=OpeningHours.daily("08:00", "20:00"),
        entry_fee_inr=0, source="synthetic_dev",
    )
    base.update(kw)
    return Place(**base)


def make_eatery(**kw):
    base = dict(
        id="r1", destination_id="testville", name="Test Diner", location=CENTER,
        opening_hours=OpeningHours.daily("11:00", "23:00"), source="synthetic_dev",
    )
    base.update(kw)
    return Restaurant(**base)


def activity(start, end, duration, place_id="p1", cost_inr=0, **kw):
    return ItineraryItem(type="activity", start=start, end=end, duration_minutes=duration,
                         place_id=place_id, cost_inr=cost_inr, **kw)


def meal(start, end, duration, restaurant_id="r1", meal_type="lunch", cost_inr=0, **kw):
    return ItineraryItem(type="meal", start=start, end=end, duration_minutes=duration,
                         restaurant_id=restaurant_id, meal_type=meal_type, cost_inr=cost_inr, **kw)


def travel(start, end, duration, from_id="p1", to_id="p2", mode="cab", cost_inr=0, **kw):
    return ItineraryItem(type="travel", start=start, end=end, duration_minutes=duration,
                         from_id=from_id, to_id=to_id, transport_mode=mode, cost_inr=cost_inr, **kw)


def rest(start, end, duration, **kw):
    return ItineraryItem(type="rest", start=start, end=end, duration_minutes=duration, **kw)


def day(n, items, date=None):
    return DayPlan(day=n, date=date or (START + dt.timedelta(days=n - 1)), items=items)


def itinerary(*days, plan_id="plan1"):
    return Itinerary(plan_id=plan_id, days=list(days))


def make_context(trip=None, itin=None, places=None, restaurants=None, **kw):
    return ConstraintContext(
        trip=trip or make_trip(), itinerary=itin if itin is not None else itinerary(),
        places=places or {}, restaurants=restaurants or {}, **kw,
    )
