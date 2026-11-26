import datetime as dt

from app.schemas.modification import PlanModification, PlanModificationRequest
from app.schemas.planner import PlannerOptions
from app.services.modifications import PlanModificationService
from app.services.planner import PlannerService
from tests.factories import make_repos, make_place
from tests.factories_constraints import itinerary, day, activity
from app.schemas.trip import TripRequest


def trip():
    return TripRequest(
        destination="Testville",
        start_date=dt.date.today()+dt.timedelta(days=30),
        end_date=dt.date.today()+dt.timedelta(days=31),
        travellers=2, trip_type="friends", budget=30000, interests=["beach"]
    )


def test_remove_place_reoptimizes_and_returns_plan():
    repos=make_repos(places=[make_place(id="p1"),make_place(id="p2",name="Two")])
    planner=PlannerService(repos)
    base=planner.generate(__import__('app.schemas.planner',fromlist=['PlanGenerationRequest']).PlanGenerationRequest(trip=trip())).itinerary
    result=PlanModificationService(planner).apply(PlanModificationRequest(
        trip=trip(), itinerary=base, modifications=[PlanModification(action="remove_place",place_id="p1")]
    ))
    ids={i.place_id for d in result.plan.itinerary.days for i in d.items if i.place_id}
    assert "p1" not in ids
    assert result.applied and not result.rejected


def test_remove_place_is_excluded_from_followup_optimization():
    repos=make_repos(places=[make_place(id="p1"),make_place(id="p2",name="Two"),make_place(id="p3",name="Three")])
    planner=PlannerService(repos)
    base=planner.generate(__import__('app.schemas.planner',fromlist=['PlanGenerationRequest']).PlanGenerationRequest(trip=trip())).itinerary
    result=PlanModificationService(planner).apply(PlanModificationRequest(
        trip=trip(), itinerary=base, modifications=[PlanModification(action="remove_place",place_id="p1")]
    ))
    ids={i.place_id for d in result.plan.itinerary.days for i in d.items if i.place_id}
    assert "p1" not in ids
    assert not result.rejected


def test_add_place_uses_required_place_path():
    repos=make_repos(places=[make_place(id="p1"),make_place(id="p2",name="Two")])
    planner=PlannerService(repos)
    base=itinerary(day(1,[]),day(2,[]))
    result=PlanModificationService(planner).apply(PlanModificationRequest(
        trip=trip(), itinerary=base, modifications=[PlanModification(action="add_place",place_id="p2")]
    ))
    ids={i.place_id for d in result.plan.itinerary.days for i in d.items if i.place_id}
    assert "p2" in ids


def test_move_place_changes_requested_day():
    repos=make_repos(places=[make_place(id="p1"),make_place(id="p2",name="Two")])
    planner=PlannerService(repos)
    base=itinerary(day(1,[activity("09:00","10:00",60,place_id="p1")]),day(2,[]))
    result=PlanModificationService(planner).apply(PlanModificationRequest(
        trip=trip(), itinerary=base, modifications=[PlanModification(action="move_place",place_id="p1",day=2,start="10:00")]
    ))
    assert any(i.place_id=="p1" for i in result.plan.itinerary.days[1].items)


def test_invalid_modification_action_is_rejected_by_schema():
    try:
        PlanModification(action="unknown")
        assert False
    except ValueError:
        assert True


class FakeLiveProvider:
    def discover_places(self, destination):
        return [make_place(id="live-p1", name="Live Place", destination_id=destination.id)]


def test_modification_service_accepts_live_places_when_local_dataset_is_empty():
    destination = __import__('tests.factories', fromlist=['make_destination']).make_destination(id="testville", name="Testville")
    repos = make_repos(destinations=[destination], places=[])
    planner = PlannerService(repos, live_provider=FakeLiveProvider())
    base = itinerary(day(1, []), day(2, []))
    result = PlanModificationService(planner).apply(PlanModificationRequest(
        trip=trip(), itinerary=base, modifications=[PlanModification(action="add_place", place_id="live-p1")]
    ))
    assert result.applied and not result.rejected
    assert any(i.place_id == "live-p1" for d in result.plan.itinerary.days for i in d.items)
