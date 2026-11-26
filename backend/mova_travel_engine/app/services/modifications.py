"""E4 structured modification and re-optimization service."""
from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.data.filters import PlaceFilter, RestaurantFilter, HotelFilter
from app.data.repositories.base import Repositories
from app.schemas.modification import PlanModification, PlanModificationRequest, PlanModificationResult
from app.schemas.planner import PlanGenerationRequest
from app.schemas.itinerary import DayPlan, Itinerary, ItineraryItem
from app.services.planner import PlannerService
from app.utils.time import from_minutes, to_minutes

class PlanModificationService:
    def __init__(self, planner: PlannerService):
        self.planner = planner

    def apply(self, request: PlanModificationRequest) -> PlanModificationResult:
        itinerary = request.itinerary
        applied=[]; rejected=[]; messages=[]
        excluded_ids={m.place_id for m in request.modifications if m.action=="remove_place" and m.place_id}
        destination=self.planner.repositories.destinations.resolve(request.trip.destination)
        if destination is None:
            raise NotFoundError(f"destination not found: {request.trip.destination}")
        candidates=self.planner.repositories.places.list_by_destination(destination.id, PlaceFilter(available_in_month=request.trip.start_date.month, include_unknown=True))
        if not candidates and self.planner.live_provider is not None:
            try:
                candidates=self.planner.live_provider.discover_places(destination)
            except Exception:
                candidates=[]
        candidate_ids={p.id for p in candidates}
        for mod in request.modifications:
            if mod.action in {"add_place","remove_place","move_place"} and mod.place_id not in candidate_ids:
                rejected.append(mod); messages.append(f"Place {mod.place_id!r} is not available in the current destination data."); continue
            if mod.action == "remove_place":
                itinerary=self._remove_place(itinerary, mod.place_id); applied.append(mod)
            elif mod.action == "move_place":
                moved=self._move_place(itinerary, mod)
                if moved is None: rejected.append(mod); messages.append(f"Could not move {mod.place_id!r} to the requested day/time.")
                else: itinerary=moved; applied.append(mod)
            elif mod.action == "add_place":
                # Required IDs are passed to E2 so the optimizer inserts and validates it.
                applied.append(mod)
            elif mod.action == "reoptimize":
                applied.append(mod)
        required=[m.place_id for m in applied if m.action=="add_place" and m.place_id]
        # Re-run the whole planning/repair stack on the edited base itinerary.
        opt=request.options.optimizer.model_copy(update={"required_place_ids": required, "excluded_place_ids": sorted(excluded_ids)})
        plan_req=PlanGenerationRequest(trip=request.trip, base_itinerary=itinerary, options=request.options.model_copy(update={"optimizer":opt}))
        result=self.planner.generate(plan_req)
        messages.append("Applied changes were revalidated by E1 and re-optimized by E2.")
        return PlanModificationResult(plan=result, applied=applied, rejected=rejected, messages=messages)

    @staticmethod
    def _remove_place(itinerary: Itinerary, place_id: str) -> Itinerary:
        days=[]
        for d in itinerary.days:
            items=[i for i in d.items if i.place_id!=place_id and i.from_id!=place_id and i.to_id!=place_id]
            days.append(DayPlan(day=d.day,date=d.date,items=items))
        return Itinerary(plan_id=itinerary.plan_id,days=days)

    @staticmethod
    def _move_place(itinerary: Itinerary, mod: PlanModification) -> Itinerary | None:
        found=None
        days=[DayPlan(day=d.day,date=d.date,items=list(d.items)) for d in itinerary.days]
        for d in days:
            for i in list(d.items):
                if i.place_id==mod.place_id and i.type.value=="activity":
                    found=(d,i); break
            if found: break
        if not found: return None
        source,item=found
        if mod.day is None or mod.day>len(days): return None
        source.items.remove(item)
        target=days[mod.day-1]
        start=mod.start or "09:00"
        end=mod.end or from_minutes(to_minutes(start)+item.duration_minutes)
        try:
            moved=ItineraryItem.model_validate({**item.model_dump(),"start":start,"end":end})
        except Exception:
            return None
        target.items.append(moved)
        # Remove travel edges touching the moved place; E2/E1 will re-evaluate the plan.
        for d in days:
            d.items=[i for i in d.items if not (i.type.value=="travel" and (i.from_id==mod.place_id or i.to_id==mod.place_id))]
        return Itinerary(plan_id=itinerary.plan_id,days=days)
