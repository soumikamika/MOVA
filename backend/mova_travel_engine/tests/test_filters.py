import pytest
from pydantic import ValidationError

from app.data.filters import (
    HotelFilter, OpenDuring, PlaceFilter, RestaurantFilter, TransportFilter,
    match_destination, rank_text_matches,
)
from app.schemas.common import DataSource
from tests.factories import (
    make_destination, make_hotel, make_place, make_restaurant, make_transport,
)


# ---------------------------- PlaceFilter -----------------------------------
def test_empty_filter_matches_everything():
    assert PlaceFilter().matches(make_place()) is True


def test_destination_and_category_filters():
    p = make_place()
    assert PlaceFilter(destination_id="testville").matches(p)
    assert not PlaceFilter(destination_id="elsewhere").matches(p)
    assert PlaceFilter(categories={"beach", "park"}).matches(p)
    assert not PlaceFilter(categories={"museum"}).matches(p)
    assert not PlaceFilter(exclude_categories={"beach"}).matches(p)


def test_tag_filters_are_normalised():
    p = make_place(tags=["beaches", "water_sports"])
    assert PlaceFilter(tags_any=["Beach"]).matches(p)             # synonym -> beaches
    assert PlaceFilter(tags_any=["Water Sports", "zzz"]).matches(p)
    assert not PlaceFilter(tags_any=["museums"]).matches(p)
    assert not PlaceFilter(tags_exclude=["water sports"]).matches(p)
    assert PlaceFilter(tags_exclude=["clubs"]).matches(p)


def test_unknown_rating_follows_include_unknown_policy():
    p = make_place(rating=None)
    assert PlaceFilter(min_rating=4.0).matches(p) is True                          # default: keep
    assert PlaceFilter(min_rating=4.0, include_unknown=False).matches(p) is False
    assert PlaceFilter(min_rating=4.5).matches(make_place(rating=4.0)) is False
    assert PlaceFilter(min_rating=4.0).matches(make_place(rating=4.0)) is True


def test_unknown_fee_is_not_treated_as_free():
    p = make_place(entry_fee_inr=None)
    assert PlaceFilter(max_entry_fee_inr=0).matches(p) is True
    assert PlaceFilter(max_entry_fee_inr=0, include_unknown=False).matches(p) is False
    assert PlaceFilter(max_entry_fee_inr=100).matches(make_place(entry_fee_inr=500)) is False
    assert PlaceFilter(max_entry_fee_inr=100).matches(make_place(entry_fee_inr=0)) is True


def test_intensity_and_duration_limits():
    p = make_place(intensity=4, avg_visit_minutes=180)
    assert not PlaceFilter(max_intensity=3).matches(p)
    assert PlaceFilter(max_intensity=4).matches(p)
    assert not PlaceFilter(max_visit_minutes=120).matches(p)
    assert PlaceFilter(max_visit_minutes=180).matches(p)


def test_family_and_wheelchair_requirements_with_unknowns():
    unknown = make_place(family_friendly=None, wheelchair_accessible=None)
    assert PlaceFilter(require_family_friendly=True).matches(unknown)
    assert not PlaceFilter(require_family_friendly=True, include_unknown=False).matches(unknown)
    assert not PlaceFilter(require_family_friendly=True).matches(make_place(family_friendly=False))
    assert PlaceFilter(require_wheelchair_accessible=True).matches(make_place(wheelchair_accessible=True))
    assert not PlaceFilter(require_wheelchair_accessible=True).matches(make_place(wheelchair_accessible=False))


def test_seasonal_closure_filter():
    p = make_place(closed_months=[6, 7, 8])
    assert not PlaceFilter(available_in_month=7).matches(p)
    assert PlaceFilter(available_in_month=12).matches(p)
    assert PlaceFilter(available_in_month=7).matches(make_place(closed_months=[]))  # no known closures


def test_source_filters():
    synth = make_place(source="synthetic_dev")
    real = make_place(source="real")
    assert PlaceFilter(sources={DataSource.REAL}).matches(real)
    assert not PlaceFilter(sources={DataSource.REAL}).matches(synth)
    assert not PlaceFilter(sources=set()).matches(real)               # empty allow-list = nothing
    assert not PlaceFilter(exclude_development_only=True).matches(synth)
    assert PlaceFilter(exclude_development_only=True).matches(real)
    assert not PlaceFilter(exclude_development_only=True).matches(make_place(source="mock"))


def test_invalid_filter_values_rejected():
    with pytest.raises(ValidationError, match="min_rating"):
        PlaceFilter(min_rating=6)
    with pytest.raises(ValidationError, match="available_in_month"):
        PlaceFilter(available_in_month=13)
    with pytest.raises(ValidationError, match="colour"):
        PlaceFilter(colour="red")
    with pytest.raises(ValidationError, match="sources"):
        PlaceFilter(sources={"verified"})


# -------------------------- RestaurantFilter --------------------------------
def test_restaurant_dietary_all_and_unknown_options():
    r = make_restaurant(dietary_options=["vegetarian", "vegan"])
    assert RestaurantFilter(dietary_all=["vegetarian"]).matches(r)
    assert RestaurantFilter(dietary_all=["vegetarian", "vegan"]).matches(r)
    assert not RestaurantFilter(dietary_all=["vegetarian", "halal"]).matches(r)
    unknown = make_restaurant(dietary_options=[])
    assert RestaurantFilter(dietary_all=["vegetarian"]).matches(unknown)
    assert not RestaurantFilter(dietary_all=["vegetarian"], include_unknown=False).matches(unknown)


def test_restaurant_serves_price_rating_cuisine():
    r = make_restaurant(serves=["dinner"], avg_price_per_person_inr=500, rating=3.5, cuisines=["Goan", "Seafood"])
    assert RestaurantFilter(serves="dinner").matches(r)
    assert not RestaurantFilter(serves="breakfast").matches(r)
    assert not RestaurantFilter(max_price_per_person_inr=400).matches(r)
    assert RestaurantFilter(max_price_per_person_inr=500).matches(r)
    assert not RestaurantFilter(min_rating=4).matches(r)
    assert RestaurantFilter(cuisines_any=["goan"]).matches(r)
    assert not RestaurantFilter(cuisines_any=["thai"]).matches(r)
    assert RestaurantFilter(max_price_per_person_inr=100).matches(make_restaurant(avg_price_per_person_inr=None))


def test_restaurant_open_during_uses_opening_hours():
    r = make_restaurant()  # daily 11:00-23:00
    assert RestaurantFilter(open_during=OpenDuring(weekday=2, start_minute=720, end_minute=780)).matches(r)
    assert not RestaurantFilter(open_during=OpenDuring(weekday=2, start_minute=540, end_minute=600)).matches(r)
    no_hours = make_restaurant(opening_hours=None)
    f = RestaurantFilter(open_during=OpenDuring(weekday=2, start_minute=720, end_minute=780))
    assert f.matches(no_hours)
    assert not f.model_copy(update={"include_unknown": False}).matches(no_hours)


def test_open_during_validation():
    with pytest.raises(ValidationError, match="end_minute"):
        OpenDuring(weekday=1, start_minute=600, end_minute=600)
    with pytest.raises(ValidationError, match="weekday"):
        OpenDuring(weekday=7, start_minute=0, end_minute=60)


# ---------------------------- Hotel / Transport -----------------------------
def test_hotel_filters():
    h = make_hotel(category="midrange", price_per_night_inr=4000, max_occupancy_per_room=3, rating=4.2)
    assert HotelFilter(categories={"midrange"}).matches(h)
    assert not HotelFilter(categories={"luxury"}).matches(h)
    assert not HotelFilter(max_price_per_night_inr=3000).matches(h)
    assert HotelFilter(min_occupancy_per_room=3).matches(h)
    assert not HotelFilter(min_occupancy_per_room=4).matches(h)
    assert HotelFilter(amenities_all=["WiFi"]).matches(h)
    assert not HotelFilter(amenities_all=["spa"]).matches(h)
    assert HotelFilter(min_rating=4.5).matches(make_hotel(rating=None))
    assert not HotelFilter(min_rating=4.5, include_unknown=False).matches(make_hotel(rating=None))


def test_transport_filters_case_insensitive_endpoints():
    t = make_transport(origin="Mumbai", destination="Testville", mode="train", duration_minutes=600,
                       price_per_person_inr=900)
    assert TransportFilter(origin="  mumbai ", destination="TESTVILLE").matches(t)
    assert not TransportFilter(origin="Pune").matches(t)
    assert TransportFilter(modes={"train", "bus"}).matches(t)
    assert not TransportFilter(modes={"flight"}).matches(t)
    assert not TransportFilter(max_duration_minutes=500).matches(t)
    assert not TransportFilter(max_price_per_person_inr=800).matches(t)


# ------------------------ lookup / text-search helpers ----------------------
def test_match_destination_by_id_name_alias():
    a = make_destination(id="testville", name="Testville", aliases=["Test City", "TV"])
    b = make_destination(id="otherton", name="Otherton")
    ds = [b, a]
    assert match_destination("testville", ds) is a
    assert match_destination("  TESTVILLE ", ds) is a
    assert match_destination("test   city", ds) is a
    assert match_destination("tv", ds) is a
    assert match_destination("Otherton", ds) is b
    assert match_destination("nowhere", ds) is None
    assert match_destination("   ", ds) is None
    assert match_destination("Goa", []) is None


def test_match_destination_prefers_name_over_alias():
    a = make_destination(id="a", name="Alpha", aliases=["Beta"])
    b = make_destination(id="b", name="Beta")
    assert match_destination("beta", [a, b]) is b


def test_rank_text_matches_ordering_and_tokens():
    places = [make_place(id="1", name="Sunset Beach Bar"), make_place(id="2", name="Beach"),
              make_place(id="3", name="Beachside Fort"), make_place(id="4", name="Old Fort", tags=["beaches"])]
    hay = lambda p: " ".join([p.name, *p.tags])
    out = rank_text_matches(places, "beach", name=lambda p: p.name, haystack=hay)
    assert [p.id for p in out] == ["2", "3", "1", "4"]    # exact, prefix, substring, other-field
    assert [p.id for p in rank_text_matches(places, "beach fort", name=lambda p: p.name, haystack=hay)] == ["3", "4"]
    assert rank_text_matches(places, "   ", name=lambda p: p.name, haystack=hay) == []
    assert len(rank_text_matches(places, "beach", name=lambda p: p.name, haystack=hay, limit=2)) == 2
