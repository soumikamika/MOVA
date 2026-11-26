"""Phase E2 deterministic itinerary optimizer.

This first optimizer is intentionally dependency-light.  It uses the existing
recommendation ranking and TravelTimeService, builds a day-by-day candidate
schedule, validates it through E1, and repairs hard violations by removing the
lowest-value conflicting candidate.  The public service contract is designed
so an OR-Tools implementation can replace the search strategy later without
changing the schemas or caller.

No price, route, opening hour, or rating is invented.  Unknown values remain
unknown and are surfaced by E1 as warnings.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from app.constraints.context import ConstraintContext
from app.constraints.engine import ConstraintEngine
from app.recommendation.service import RecommendationService
from app.schemas.common import ItemType, TransportMode
from app.schemas.itinerary import DayPlan, Itinerary, ItineraryItem
from app.schemas.optimizer import OptimizationChange, OptimizerRequest, OptimizerResult
from app.schemas.place import Place
from app.schemas.logistics import TravelTimeRequest
from app.schemas.trip import TripRequest
from app.travel_time.service import TravelTimeService
from app.utils.geo import haversine_km
from app.utils.time import from_minutes, to_minutes


@dataclass(frozen=True)
class _Candidate:
    place: Place
    score: float


class OptimizerService:
    """Stateless optimizer; safe to instantiate once and reuse."""

    def __init__(
        self,
        recommendation_service: RecommendationService | None = None,
        travel_time_service: TravelTimeService | None = None,
        constraint_engine: ConstraintEngine | None = None,
    ) -> None:
        self.recommendation_service = recommendation_service or RecommendationService()
        self.travel_time_service = travel_time_service or TravelTimeService()
        self.constraint_engine = constraint_engine or ConstraintEngine()

    def optimize(self, request: OptimizerRequest) -> OptimizerResult:
        candidates = {p.id: p for p in request.candidates}
        if request.base_itinerary is not None:
            return self._repair_existing(request, candidates)

        if not candidates:
            empty = Itinerary(plan_id=f"mova-{request.trip.start_date.isoformat()}", days=[])
            return OptimizerResult(
                itinerary=empty, feasible=True, objective_score=0.0,
                optimizer_method="greedy_e2", iterations=0,
                notes=["No candidate places were supplied; no itinerary was generated."],
            )

        excluded = set(request.options.excluded_place_ids)
        if excluded:
            candidates = {pid: p for pid, p in candidates.items() if pid not in excluded}
        ranked = self._rank(request.trip, list(candidates.values()), request)
        itinerary, changes, rejected = self._build(request.trip, ranked, request)
        context = self._context(request.trip, itinerary, candidates, request)
        validation = self.constraint_engine.validate(context)

        # E1 can report confirmed hard conflicts caused by generated data. Repair
        # deterministically until feasible or no removable activity remains.
        iterations = 1
        while not validation.feasible and iterations < len(ranked) + 2:
            conflict_ids = self._conflicting_place_ids(validation.conflicts, itinerary)
            if not conflict_ids:
                break
            remove_id = self._lowest_rank_conflicting(conflict_ids, ranked)
            if remove_id is None:
                break
            itinerary = self._remove_place(itinerary, remove_id)
            rejected.append(remove_id)
            changes.append(OptimizationChange(
                action="remove", place_id=remove_id,
                reason="Removed during constraint repair because the candidate caused a hard itinerary conflict.",
            ))
            itinerary = self._compact_days(itinerary)
            validation = self.constraint_engine.validate(self._context(request.trip, itinerary, candidates, request))
            iterations += 1

        score = self._objective(itinerary, ranked, request.trip)
        notes = [
            "E2 uses deterministic greedy search with E1 validation; it does not claim ML accuracy.",
            "Unknown source data is preserved and surfaced as E1 warnings rather than guessed.",
        ]
        return OptimizerResult(
            itinerary=itinerary,
            feasible=validation.feasible,
            objective_score=score,
            optimizer_method="greedy_e2",
            iterations=iterations,
            changes=changes,
            rejected_place_ids=rejected,
            conflicts=validation.conflicts,
            warnings=validation.warnings,
            notes=notes,
        )

    def _rank(self, trip: TripRequest, candidates: list[Place], request: OptimizerRequest) -> list[_Candidate]:
        supplied = {r.place_id: r for r in request.recommendations}
        if supplied:
            rows = [_Candidate(p, supplied[p.id].score if p.id in supplied else 0.0) for p in candidates]
            rows.sort(key=lambda c: (-c.score, c.place.id))
            return rows
        recs = self.recommendation_service.recommend(trip, candidates)
        scores = {r.place_id: r.score for r in recs}
        return sorted((_Candidate(p, scores.get(p.id, 0.0)) for p in candidates), key=lambda c: (-c.score, c.place.id))

    def _build(self, trip: TripRequest, ranked: list[_Candidate], request: OptimizerRequest):
        days = [DayPlan(day=i + 1, date=d, items=[]) for i, d in enumerate(trip.dates)]
        changes: list[OptimizationChange] = []
        rejected: list[str] = []
        used: set[str] = set()
        cursor = [to_minutes(request.options.day_start)] * len(days)
        end = to_minutes(request.options.day_end)
        last_place: list[str | None] = [None] * len(days)

        for candidate in ranked:
            if candidate.place.id in used:
                continue
            if candidate.place.id in rejected:
                continue
            placed = False
            for di, day in enumerate(days):
                if len([i for i in day.items if i.type == ItemType.ACTIVITY]) >= request.options.max_activities_per_day:
                    continue
                start = cursor[di]
                travel_minutes = 0
                from_id = last_place[di]
                if from_id:
                    previous = next((c.place for c in ranked if c.place.id == from_id), None)
                    if previous:
                        travel_minutes = self._travel_minutes(previous, candidate.place, day.date, request.options.default_transport)
                        start += travel_minutes + request.options.minimum_gap_minutes
                visit = candidate.place.avg_visit_minutes
                finish = start + visit
                if finish > end:
                    continue
                if candidate.place.opening_hours is not None and not candidate.place.opening_hours.is_open(day.date.weekday(), start, finish):
                    # Try the next day rather than assuming a venue is open.
                    continue
                if candidate.place.closed_months and day.date.month in candidate.place.closed_months:
                    continue

                if from_id:
                    day.items.append(ItineraryItem(
                        type=ItemType.TRAVEL,
                        start=from_minutes(start - travel_minutes - request.options.minimum_gap_minutes),
                        end=from_minutes(start - request.options.minimum_gap_minutes),
                        duration_minutes=travel_minutes,
                        from_id=from_id,
                        to_id=candidate.place.id,
                        transport_mode=request.options.default_transport,
                        cost_inr=None,
                    ))
                fee = candidate.place.entry_fee_inr
                day.items.append(ItineraryItem(
                    type=ItemType.ACTIVITY,
                    start=from_minutes(start), end=from_minutes(finish),
                    duration_minutes=visit, place_id=candidate.place.id,
                    cost_inr=(fee * trip.travellers if fee is not None else None),
                    facts={"optimizer_score": round(candidate.score, 4), "place_name": candidate.place.name, "latitude": candidate.place.location.latitude, "longitude": candidate.place.location.longitude, "category": candidate.place.category.value},
                ))
                cursor[di] = finish
                last_place[di] = candidate.place.id
                used.add(candidate.place.id)
                changes.append(OptimizationChange(action="schedule", place_id=candidate.place.id, day=di + 1,
                                                  reason="Selected by recommendation score and fitted within time/opening constraints."))
                placed = True
                break
            if not placed:
                rejected.append(candidate.place.id)
                changes.append(OptimizationChange(action="reject", place_id=candidate.place.id,
                                                  reason="Could not fit within the available day window or confirmed opening constraints."))
        return Itinerary(plan_id=f"mova-{trip.start_date.isoformat()}", days=days), changes, rejected

    def _repair_existing(self, request: OptimizerRequest, candidates: dict[str, Place]):
        itinerary = request.base_itinerary
        validation = self.constraint_engine.validate(self._context(request.trip, itinerary, candidates, request))
        changes: list[OptimizationChange] = []
        rejected: list[str] = []
        iterations = 1

        # E4 can request places that must be added to an existing plan. Build a
        # fresh feasible schedule for those additions, then validate/repair the
        # combined itinerary. Unknown place facts remain unknown.
        existing_ids = {
            item.place_id
            for day in itinerary.days
            for item in day.items
            if item.place_id
        }
        required = [
            candidates[pid] for pid in request.options.required_place_ids
            if pid in candidates and pid not in existing_ids
        ]
        if required:
            ranked_required = self._rank(request.trip, required, request)
            for cand in ranked_required:
                inserted = self._insert_activity_on_best_day(itinerary, cand.place, request)
                if inserted is not None:
                    itinerary = inserted
                    changes.append(OptimizationChange(
                        action="add", place_id=cand.place.id,
                        reason="Added because the modification request marked this place as required, then revalidated the itinerary.",
                    ))
                else:
                    rejected.append(cand.place.id)
                    changes.append(OptimizationChange(
                        action="reject", place_id=cand.place.id,
                        reason="Could not add the required place without violating the available day window or confirmed opening constraints.",
                    ))
            validation = self.constraint_engine.validate(self._context(request.trip, itinerary, candidates, request))
        while not validation.feasible and iterations < len(itinerary.days) * 20 + 2:
            duplicate = next((c for c in validation.conflicts if c.type.value == "duplicate_place" and len(c.item_refs) >= 2), None)
            if duplicate:
                ref = duplicate.item_refs[-1]
                item = self._item_from_ref(itinerary, ref)
                if item and item.place_id:
                    itinerary = self._remove_item_ref(itinerary, ref)
                    changes.append(OptimizationChange(action="remove", place_id=item.place_id, day=duplicate.day,
                                                      reason="Removed the lower-priority duplicate visit while preserving the first scheduled visit."))
                    validation = self.constraint_engine.validate(self._context(request.trip, itinerary, candidates, request))
                    iterations += 1
                    continue
            ids = self._conflicting_place_ids(validation.conflicts, itinerary)
            if not ids:
                break
            rid = self._lowest_rank_conflicting(ids, self._rank(request.trip, list(candidates.values()), request))
            if rid is None:
                break
            itinerary = self._remove_place(itinerary, rid)
            rejected.append(rid)
            changes.append(OptimizationChange(action="remove", place_id=rid,
                                              reason="Removed from the supplied itinerary to resolve a hard constraint conflict."))
            itinerary = self._compact_days(itinerary)
            validation = self.constraint_engine.validate(self._context(request.trip, itinerary, candidates, request))
            iterations += 1
        return OptimizerResult(
            itinerary=itinerary, feasible=validation.feasible,
            objective_score=self._objective(itinerary, self._rank(request.trip, list(candidates.values()), request), request.trip),
            optimizer_method="greedy_e2_repair", iterations=iterations,
            changes=changes, rejected_place_ids=rejected,
            conflicts=validation.conflicts, warnings=validation.warnings,
            notes=["Existing itinerary was repaired without inventing missing facts."],
        )

    def _insert_activity_on_best_day(self, itinerary: Itinerary, place: Place, request: OptimizerRequest) -> Itinerary | None:
        # Conservative insertion: append after the final activity/travel on the
        # day, preserving existing items and only adding a travel edge when the
        # previous activity is known. This is intentionally deterministic.
        for day in itinerary.days:
            activities = [i for i in day.items if i.type == ItemType.ACTIVITY]
            if len(activities) >= request.options.max_activities_per_day:
                continue
            start = to_minutes(request.options.day_start)
            previous_id = None
            if day.items:
                last = max(day.items, key=lambda i: to_minutes(i.end))
                start = to_minutes(last.end)
                previous_id = last.place_id or last.to_id
            travel = 0
            if previous_id and previous_id in {
                i.place_id for d in itinerary.days for i in d.items if i.place_id
            }:
                previous_place = request_place = None
                # Existing place records are supplied in request.candidates.
                previous_place = next((p for p in request.candidates if p.id == previous_id), None)
                if previous_place is not None:
                    travel = self._travel_minutes(previous_place, place, day.date, request.options.default_transport)
                    start += travel + request.options.minimum_gap_minutes
            finish = start + place.avg_visit_minutes
            if finish > to_minutes(request.options.day_end):
                continue
            if place.opening_hours is not None and not place.opening_hours.is_open(day.date.weekday(), start, finish):
                continue
            if place.closed_months and day.date.month in place.closed_months:
                continue
            items = list(day.items)
            if previous_id and travel > 0:
                items.append(ItineraryItem(
                    type=ItemType.TRAVEL,
                    start=from_minutes(start - travel - request.options.minimum_gap_minutes),
                    end=from_minutes(start - request.options.minimum_gap_minutes),
                    duration_minutes=travel, from_id=previous_id, to_id=place.id,
                    transport_mode=request.options.default_transport, cost_inr=None,
                ))
            items.append(ItineraryItem(
                type=ItemType.ACTIVITY, start=from_minutes(start), end=from_minutes(finish),
                duration_minutes=place.avg_visit_minutes, place_id=place.id,
                cost_inr=(place.entry_fee_inr * request.trip.travellers if place.entry_fee_inr is not None else None),
                facts={"required_by_user": True},
            ))
            days = [DayPlan(day=d.day, date=d.date, items=(items if d.day == day.day else d.items)) for d in itinerary.days]
            return Itinerary(plan_id=itinerary.plan_id, days=days)
        return None

    def _travel_minutes(self, a: Place, b: Place, date: dt.date, mode: TransportMode) -> int:
        distance = haversine_km(a.location.latitude, a.location.longitude, b.location.latitude, b.location.longitude)
        prediction = self.travel_time_service.predict(TravelTimeRequest(
            origin=a.id, destination=b.id, mode=mode, distance_km=distance, date=date,
        ))
        if prediction.is_unknown or prediction.value is None:
            return 0
        return max(1, int(round(prediction.value)))

    @staticmethod
    def _context(trip: TripRequest, itinerary: Itinerary, candidates: dict[str, Place], request: OptimizerRequest):
        restaurants = {r.id: r for r in request.restaurants}
        return ConstraintContext(trip=trip, itinerary=itinerary, places=candidates, restaurants=restaurants)

    @staticmethod
    def _conflicting_place_ids(conflicts, itinerary: Itinerary) -> set[str]:
        ids: set[str] = set()
        for c in conflicts:
            for ref in c.item_refs:
                if ":item" not in ref:
                    continue
                try:
                    day_no, item_no = ref.replace("day", "").split(":item")
                    item = itinerary.days[int(day_no) - 1].items[int(item_no)]
                except (ValueError, IndexError):
                    continue
                if item.place_id:
                    ids.add(item.place_id)
        return ids

    @staticmethod
    def _lowest_rank_conflicting(ids: set[str], ranked: list[_Candidate]) -> str | None:
        rows = [c for c in ranked if c.place.id in ids]
        return min(rows, key=lambda c: (c.score, c.place.id)).place.id if rows else None

    @staticmethod
    def _item_from_ref(itinerary: Itinerary, ref: str):
        try:
            day_no, item_no = ref.replace("day", "").split(":item")
            return itinerary.days[int(day_no) - 1].items[int(item_no)]
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _remove_item_ref(itinerary: Itinerary, ref: str) -> Itinerary:
        try:
            day_no, item_no = ref.replace("day", "").split(":item")
            day_index, item_index = int(day_no) - 1, int(item_no)
        except (ValueError, IndexError):
            return itinerary
        days = []
        for index, day in enumerate(itinerary.days):
            items = [item for j, item in enumerate(day.items) if not (index == day_index and j == item_index)]
            days.append(DayPlan(day=day.day, date=day.date, items=items))
        return Itinerary(plan_id=itinerary.plan_id, days=days)

    @staticmethod
    def _remove_place(itinerary: Itinerary, place_id: str) -> Itinerary:
        days = []
        for d in itinerary.days:
            items = [i for i in d.items if i.place_id != place_id and i.to_id != place_id and i.from_id != place_id]
            days.append(DayPlan(day=d.day, date=d.date, items=items))
        return Itinerary(plan_id=itinerary.plan_id, days=days)

    @staticmethod
    def _compact_days(itinerary: Itinerary) -> Itinerary:
        # Keep dates/day numbers stable; simply remove orphaned travel gaps.
        days = []
        for d in itinerary.days:
            days.append(DayPlan(day=d.day, date=d.date, items=d.items))
        return Itinerary(plan_id=itinerary.plan_id, days=days)

    @staticmethod
    def _objective(itinerary: Itinerary, ranked: list[_Candidate], trip: TripRequest) -> float:
        scores = {c.place.id: c.score for c in ranked}
        selected = [i for d in itinerary.days for i in d.items if i.type == ItemType.ACTIVITY and i.place_id]
        value = sum(scores.get(i.place_id, 0.0) for i in selected)
        travel = sum(d.total_travel_minutes for d in itinerary.days)
        # Objective is a deterministic utility score, not a probability.
        return round(max(0.0, value - travel / 1000.0), 4)
