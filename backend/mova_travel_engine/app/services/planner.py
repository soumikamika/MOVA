"""Phase E3 Plan Orchestrator.

The orchestrator is the single business entry point that a future API layer
should call for plan generation.  It owns the order of operations but not the
individual intelligence algorithms:

    destination -> repositories -> recommendations -> optimizer/E1 -> result

No external provider, LLM, or database implementation is imported here.
Repositories and services are injected, so JSON can later be replaced by
PostgreSQL/live providers without changing the contract.
"""
from __future__ import annotations

import math
import uuid
import datetime as dt

from app.core.exceptions import DataUnavailableError, NotFoundError
from app.data.filters import PlaceFilter, RestaurantFilter, HotelFilter
from app.data.repositories.base import Repositories
from app.optimizer.service import OptimizerService
from app.recommendation.service import RecommendationService
from app.schemas.common import ConfidenceLevel, ConflictType, DataSource, Severity, TransportPreference
from app.schemas.itinerary import Itinerary, DayPlan, PlanConflict
from app.schemas.optimizer import OptimizerRequest
from app.constraints.context import ConstraintContext
from app.constraints.engine import ConstraintEngine
from app.schemas.planner import (
    DataQuality,
    EngineStatus,
    PlanGenerationRequest,
    PlanGenerationResult,
)
from app.travel_cost.service import TravelCostService
from app.travel_time.service import TravelTimeService
from app.providers.osm import OSMProvider
from app.routing.service import RoutingService
from app.services.travel_method import TravelMethodService
from app.schemas.routing import RouteLeg, RouteResult
from app.schemas.budget import Budget, BudgetStatus, CostBreakdown


# Waking hours per trip day available for travel + sightseeing. Used only by the
# origin-journey time check; it is a documented planning assumption, not a fact.
WAKING_MINUTES_PER_DAY = 16 * 60


class PlannerService:
    """Stateless, dependency-injected plan generation orchestrator."""

    def __init__(
        self,
        repositories: Repositories,
        recommendation_service: RecommendationService | None = None,
        travel_time_service: TravelTimeService | None = None,
        travel_cost_service: TravelCostService | None = None,
        optimizer_service: OptimizerService | None = None,
        live_provider: OSMProvider | None = None,
        routing_service: RoutingService | None = None,
        travel_method_service: TravelMethodService | None = None,
    ) -> None:
        self.repositories = repositories
        self.recommendation_service = recommendation_service or RecommendationService()
        self.travel_time_service = travel_time_service or TravelTimeService()
        self.travel_cost_service = travel_cost_service or TravelCostService()
        self.live_provider = live_provider
        self.routing_service = routing_service or RoutingService()
        self.travel_method_service = travel_method_service or TravelMethodService()
        self.optimizer_service = optimizer_service or OptimizerService(
            recommendation_service=self.recommendation_service,
            travel_time_service=self.travel_time_service,
        )

    def validate_itinerary(self, trip, itinerary, candidates, restaurants=None):
        """Validate an itinerary with E1 using caller-supplied records."""
        return ConstraintEngine().validate(ConstraintContext(
            trip=trip, itinerary=itinerary,
            places={p.id: p for p in candidates},
            restaurants={r.id: r for r in (restaurants or [])},
        ))

    def _resolve_destination_for_route(self, name: str):
        destination = self.repositories.destinations.resolve(name)
        if destination is None and self.live_provider is not None:
            try:
                destination = self.live_provider.resolve_destination(name)
            except Exception:
                destination = None
        return destination

    @staticmethod
    def _legacy_transport_preference_methods(preference: TransportPreference | None) -> list[str] | None:
        """Map the legacy single `transport_preference` onto TravelMethodService's list API."""
        if preference is None or preference == TransportPreference.FLEXIBLE:
            return None
        return ["car" if preference == TransportPreference.ROAD else preference.value]

    def _build_route_legs(self, trip, destination_names: list[str]) -> tuple[list[RouteLeg], RouteResult | None]:
        """Build road route legs from the origin through destination centers.

        If the user supplied a starting city but browser coordinates were not
        available, the live OSM provider is allowed to geocode that city.
        This keeps the manual-origin fallback useful without inventing
        coordinates.
        """
        resolved = [self._resolve_destination_for_route(name) for name in destination_names]
        legs: list[RouteLeg] = []
        route_results: list[RouteResult] = []

        previous_name = trip.origin or None
        previous_lat = trip.origin_latitude
        previous_lon = trip.origin_longitude
        if (previous_lat is None or previous_lon is None) and trip.origin:
            # Bundled dataset first (exact id/name/alias match), then the live
            # geocoder. Coordinates are never guessed.
            origin_destination = self._resolve_destination_for_route(trip.origin)
            if origin_destination and origin_destination.center:
                previous_lat = origin_destination.center.latitude
                previous_lon = origin_destination.center.longitude

        for index, destination in enumerate(resolved):
            if destination is None:
                continue
            current_name = destination.name
            current_lat = destination.center.latitude if destination.center else None
            current_lon = destination.center.longitude if destination.center else None

            if previous_lat is None or previous_lon is None or current_lat is None or current_lon is None:
                if index == 0:
                    legs.append(RouteLeg(
                        origin=previous_name or "Starting location",
                        destination=current_name,
                        mode="car",
                        status="unavailable",
                        source="OSRM",
                        notes=["Origin coordinates are required for live route calculation."],
                    ))
                previous_name = current_name
                previous_lat, previous_lon = current_lat, current_lon
                continue

            result = self.routing_service.route(
                origin_latitude=previous_lat,
                origin_longitude=previous_lon,
                destination_latitude=current_lat,
                destination_longitude=current_lon,
                origin_name=previous_name or "Starting location",
                destination_name=current_name,
            )
            route_results.append(result)
            legs.append(RouteLeg(
                origin=result.origin,
                destination=result.destination,
                distance_km=result.distance_km,
                duration_minutes=result.duration_minutes,
                mode="car",
                source=result.source,
                status=result.status,
                geometry=result.geometry,
                notes=result.notes,
            ))
            previous_name = current_name
            previous_lat, previous_lon = current_lat, current_lon

        available = [r for r in route_results if r.status == "available"]
        if not available:
            return legs, None

        return legs, RouteResult(
            origin=trip.origin or (destination_names[0] if destination_names else "Starting location"),
            destination=destination_names[-1] if destination_names else "",
            distance_km=round(sum(r.distance_km or 0 for r in available), 2),
            duration_minutes=round(sum(r.duration_minutes or 0 for r in available), 1),
            source="OSRM",
            status="available",
            notes=[f"Aggregated from {len(available)} live road route leg(s)."],
        )

    def _assess_origin_travel_time(self, trip, result: PlanGenerationResult) -> PlanGenerationResult:
        """Account for the journey from the traveller's origin in time/feasibility.

        Uses only real route legs (OSRM). Road time is counted out and back
        (same round-trip assumption as the fuel cost). If the selected mode is
        flight/train/bus/etc. its duration is NOT integrated, so it is reported
        as missing data instead of being invented. Itinerary activities are
        never removed or moved here; a shortfall is reported as a conflict.
        """
        if not (trip.origin or trip.origin_latitude is not None):
            return result  # no origin supplied: local-only planning, as before
        legs = list(result.route_legs)
        if not legs:
            return result

        warnings = list(result.warnings)
        conflicts = list(result.conflicts)
        notes = list(result.notes)
        feasible = result.feasible

        first = legs[0]
        if first.status != "available" or first.duration_minutes is None:
            reason = "; ".join(first.notes) if first.notes else "route provider returned no route"
            warnings.append(PlanConflict(
                type=ConflictType.MISSING_DATA, severity=Severity.MEDIUM,
                message=(f"Travel time from {first.origin} to {first.destination} could not be calculated "
                         f"({reason}). The plan does not account for the journey to your destination."),
                details={"origin": first.origin, "destination": first.destination, "leg_status": first.status},
            ))
            return result.model_copy(update={"warnings": warnings})

        available_legs = [l for l in legs if l.status == "available" and l.duration_minutes is not None]
        outbound = round(sum(l.duration_minutes for l in available_legs), 1)
        outbound_km = round(sum((l.distance_km or 0) for l in available_legs), 1)

        tm = result.travel_method
        selected = next((o for o in tm.options if o.mode == tm.recommended_mode), None) if tm else None
        if selected is not None and selected.status == "NOT_INTEGRATED":
            warnings.append(PlanConflict(
                type=ConflictType.MISSING_DATA, severity=Severity.MEDIUM,
                message=(f"{selected.mode.replace('_', ' ').title()} is preferred for {first.origin} to "
                         f"{first.destination}, but live {selected.mode.replace('_', ' ')} schedules, durations and "
                         "fares are not integrated, so that journey time is not included in the feasibility check."),
                details={"origin": first.origin, "mode": selected.mode, "status": "NOT_INTEGRATED",
                         "road_reference_minutes": outbound, "road_reference_km": outbound_km},
            ))
            return result.model_copy(update={"warnings": warnings})

        return_minutes = outbound  # return retraces the same road route (estimate)
        itinerary_minutes = sum(i.duration_minutes for d in result.itinerary.days for i in d.items)
        window_minutes = trip.num_days * WAKING_MINUTES_PER_DAY
        required = outbound + return_minutes + itinerary_minutes
        shortfall = required - window_minutes
        notes.append(
            f"Journey from {first.origin}: about {outbound / 60:.1f} h one way by road ({outbound_km} km, live OSRM); "
            f"return assumed equal. Time check uses {WAKING_MINUTES_PER_DAY // 60} waking hours per trip day."
        )
        if shortfall > 0:
            extra_minutes = math.ceil(shortfall)
            conflicts.append(PlanConflict(
                type=ConflictType.INSUFFICIENT_TIME, severity=Severity.HIGH,
                message=(f"Not enough time: about {extra_minutes / 60:.1f} additional hours are required "
                         f"once {outbound / 60:.1f} h of travel each way from {first.origin} is included."),
                details={
                    "additional_minutes_required": extra_minutes,
                    "additional_hours_required": round(extra_minutes / 60, 1),
                    "outbound_travel_minutes": outbound,
                    "return_travel_minutes": return_minutes,
                    "itinerary_minutes": itinerary_minutes,
                    "available_minutes": window_minutes,
                    "trip_days": trip.num_days,
                    "waking_minutes_per_day": WAKING_MINUTES_PER_DAY,
                    "basis": "road route (OSRM); return assumed equal to outbound",
                },
            ))
            feasible = False
        return result.model_copy(update={
            "warnings": warnings, "conflicts": conflicts, "notes": notes, "feasible": feasible,
        })

    def _calculate_budget_status(self, trip, itinerary, route_legs, travel_method):
        """Calculate only costs supported by explicit inputs or itinerary facts."""
        activities = 0.0
        for day in itinerary.days:
            for item in day.items:
                if item.type.value == "activity" and item.cost_inr is not None:
                    activities += item.cost_inr

        food = 0.0
        if trip.food_budget_per_person_per_day is not None:
            food = round(trip.food_budget_per_person_per_day * trip.travellers * trip.num_days, 2)

        transport = 0.0
        for day in itinerary.days:
            for item in day.items:
                if item.type.value == "travel" and item.cost_inr is not None:
                    transport += item.cost_inr
        fuel_known = False
        if (travel_method and travel_method.recommended_mode == "car"
                and trip.vehicle_mileage_kmpl
                and trip.fuel_price_inr_per_litre is not None):
            total_distance = sum((leg.distance_km or 0) for leg in route_legs if leg.status == "available")
            # Intercity route is treated as a return journey because the planner
            # starts and ends the trip from the same origin.
            transport = round((total_distance * 2 / trip.vehicle_mileage_kmpl) * trip.fuel_price_inr_per_litre, 2)
            fuel_known = bool(total_distance)

        breakdown = CostBreakdown(transport=transport, food=food, activities=round(activities, 2))
        status = BudgetStatus.evaluate(Budget(total_inr=trip.budget, travellers=trip.travellers), breakdown)
        notes = []
        if trip.food_budget_per_person_per_day is None:
            notes.append("Food is not included because no per-person daily food budget was provided.")
        if travel_method and travel_method.recommended_mode == "car" and not fuel_known:
            notes.append("Self-drive fuel is not included until a live route and vehicle fuel inputs are available.")
        if trip.hotel_category is not None:
            notes.append("Accommodation is not included until a hotel is selected or a real hotel price is available.")
        if notes:
            # Keep the caveats on the breakdown through the result-level notes;
            # BudgetStatus itself remains a clean numeric contract.
            pass
        return status

    def _create_empty_block(self, trip, name, error_msg, block_start, block_end, days_for_stop):
        from app.schemas.itinerary import Itinerary, DayPlan
        from app.schemas.planner import PlanGenerationResult, EngineStatus, DataQuality, PlanConflict
        from app.schemas.common import DataSource
        
        days = []
        for i in range(days_for_stop):
            days.append(DayPlan(day=i+1, date=block_start + dt.timedelta(days=i), items=[]))
            
        import uuid
        return PlanGenerationResult(
            plan_id=uuid.uuid4().hex,
            destination_id=name,
            destination_name=name,
            trip=trip,
            itinerary=Itinerary(plan_id="empty", days=days),
            feasible=False,
            objective_score=0.0,
            optimizer_method="fallback",
            iterations=0,
            warnings=[PlanConflict(type="data_missing", message=error_msg, severity="error")],
            engine=EngineStatus(version="1.0.0", cache_hit=False, elapsed_ms=0, timestamp=dt.datetime.now(dt.UTC)),
            data_quality=DataQuality(destinations=1, candidates=0, restaurants=0, hotels=0, recommendations=0, sources=[DataSource.REAL], development_only=False, notes=[])
        )

    def generate(self, request: PlanGenerationRequest) -> PlanGenerationResult:
        """Generate one itinerary or a simple multi-stop itinerary.

        Multi-stop trips are split into contiguous day blocks and each stop is
        planned with the same deterministic engine. This keeps the existing
        single-destination optimizer intact while giving the frontend a real
        multi-destination contract. Inter-stop transport is left to the route
        layer until live transport data is connected.
        """
        trip = request.trip
        names = list(dict.fromkeys([n.strip() for n in (trip.destinations or []) if n.strip()]))
        if not names:
            names = [trip.destination]
        if len(names) == 1:
            return self._assess_origin_travel_time(trip, self._generate_single(request))
        if trip.num_days < len(names):
            raise DataUnavailableError(
                "Multi-stop trips need at least one day per destination.",
                details={"destinations": names, "trip_days": trip.num_days},
            )

        total_days = trip.num_days
        base, remainder = divmod(total_days, len(names))
        blocks=[]; cursor=trip.start_date
        for idx, name in enumerate(names):
            days_for_stop = base + (1 if idx < remainder else 0)
            block_start = cursor
            block_end = block_start + dt.timedelta(days=days_for_stop - 1)
            subtrip = trip.model_copy(update={
                "destination": name,
                "destinations": [name],
                "start_date": block_start,
                "end_date": block_end,
                "budget": round(trip.budget * days_for_stop / total_days, 2),
                "origin": trip.origin if idx == 0 else name,
                "origin_latitude": trip.origin_latitude if idx == 0 else None,
                "origin_longitude": trip.origin_longitude if idx == 0 else None,
            })
            try:
                blocks.append(self._generate_single(request.model_copy(update={"trip": subtrip, "base_itinerary": None})))
            except Exception as e:
                blocks.append(self._create_empty_block(subtrip, name, f"Could not generate itinerary for {name}: {str(e)}", block_start, block_end, days_for_stop))
            cursor = block_end + dt.timedelta(days=1)

        merged_id = uuid.uuid4().hex
        merged_days=[]; day_number=1
        for block in blocks:
            for day in block.itinerary.days:
                merged_days.append(DayPlan(day=day_number, date=day.date, items=day.items))
                day_number += 1
        primary=blocks[0]
        all_sources=[]; seen=set()
        for block in blocks:
            for src in block.data_quality.sources:
                if src.value not in seen: all_sources.append(src); seen.add(src.value)
        all_recs=[r for block in blocks for r in block.recommendations]
        all_changes=[c for block in blocks for c in block.changes]
        all_rejected=[x for block in blocks for x in block.rejected_place_ids]
        all_conflicts=[x for block in blocks for x in block.conflicts]
        all_warnings=[x for block in blocks for x in block.warnings]
        all_notes=[x for block in blocks for x in block.notes]
        itinerary=Itinerary(plan_id=merged_id, days=merged_days)
        route_legs, aggregate_route = self._build_route_legs(trip, names)
        travel_method = self.travel_method_service.recommend(
            distance_km=aggregate_route.distance_km if aggregate_route else None,
            route=aggregate_route,
            preferred_travel_methods=[m.value for m in trip.preferred_travel_methods] if trip.preferred_travel_methods else None,
            avoid_travel_methods=[m.value for m in trip.avoid_travel_methods] if trip.avoid_travel_methods else None,
            travellers=trip.travellers,
            fuel_type=trip.vehicle_fuel_type,
            mileage_kmpl=trip.vehicle_mileage_kmpl,
            fuel_price_inr_per_litre=trip.fuel_price_inr_per_litre,
        )
        budget_status = self._calculate_budget_status(trip, itinerary, route_legs, travel_method)
        q=primary.data_quality.model_copy(update={
            "destinations": len(blocks),
            "candidates": sum(b.data_quality.candidates for b in blocks),
            "restaurants": sum(b.data_quality.restaurants for b in blocks),
            "hotels": sum(b.data_quality.hotels for b in blocks),
            "recommendations": len(all_recs),
            "sources": all_sources,
            "development_only": any(b.data_quality.development_only for b in blocks),
            "notes": all_notes + ["Multi-stop itinerary: destinations are planned as contiguous day blocks; inter-stop transport is represented by the route layer when live transport data is available."],
        })
        merged = primary.model_copy(update={
            "plan_id": merged_id,
            "itinerary": itinerary,
            "recommendations": all_recs,
            "changes": all_changes,
            "rejected_place_ids": all_rejected,
            "conflicts": all_conflicts,
            "warnings": all_warnings,
            "feasible": all(b.feasible for b in blocks),
            "objective_score": round(sum(b.objective_score for b in blocks)/len(blocks), 4),
            "iterations": sum(b.iterations for b in blocks),
            "data_quality": q,
            "route_legs": route_legs,
            "travel_method": travel_method,
            "budget_status": budget_status,
            "notes": all_notes + [f"Multi-stop route contains {len(blocks)} destinations: {', '.join(names)}."],
        })
        return self._assess_origin_travel_time(trip, merged)

    def _generate_single(self, request: PlanGenerationRequest) -> PlanGenerationResult:
        trip = request.trip
        destination = self.repositories.destinations.resolve(trip.destination)
        live_destination = False
        if destination is None and self.live_provider is not None:
            destination = self.live_provider.resolve_destination(trip.destination)
            live_destination = destination is not None
        if destination is None:
            raise NotFoundError(
                f"destination not found: {trip.destination}",
                details={"destination": trip.destination},
            )

        place_filter = PlaceFilter(
            destination_id=destination.id,
            available_in_month=trip.start_date.month,
            include_unknown=True,
        )
        candidates = self.repositories.places.list_by_destination(
            destination.id, place_filter
        )[: request.options.candidate_limit]

        if not candidates and self.live_provider is not None:
            try:
                candidates = self.live_provider.discover_places(destination)[: request.options.candidate_limit]
            except Exception as exc:
                if request.base_itinerary is None:
                    raise DataUnavailableError(
                        "Live place discovery failed: OpenStreetMap is unavailable and MOVA could not retrieve nearby places from its Wikipedia fallback. Check backend internet access and retry.",
                        details={"destination": destination.name, "provider_error": str(exc), "provider_details": getattr(exc, "details", {})},
                    ) from exc

        if not candidates and request.base_itinerary is None:
            raise DataUnavailableError(
                "No candidate places are available for this destination and trip month.",
                details={"destination_id": destination.id},
            )

        restaurants = []
        if request.options.include_restaurants:
            restaurants = self.repositories.restaurants.list_by_destination(
                destination.id,
                RestaurantFilter(include_unknown=True),
            )

        hotels = []
        if request.options.include_hotels:
            hotels = self.repositories.hotels.list_by_destination(
                destination.id,
                HotelFilter(include_unknown=True),
            )

        recommendations = self.recommendation_service.recommend(trip, candidates)

        # Preserve traveller-pinned places when the bundled dataset contains a
        # matching record. Unknown names remain in the request for the future
        # live-data layer rather than being invented here.
        requested_names = {str(name).strip().lower() for name in trip.must_visit_places}
        required_ids = list(request.options.optimizer.required_place_ids)
        for candidate in candidates:
            if candidate.name.strip().lower() in requested_names and candidate.id not in required_ids:
                required_ids.append(candidate.id)
        optimizer_options = request.options.optimizer.model_copy(update={"required_place_ids": required_ids})

        optimizer_request = OptimizerRequest(
            trip=trip,
            candidates=candidates,
            recommendations=recommendations,
            restaurants=restaurants,
            base_itinerary=request.base_itinerary,
            options=optimizer_options,
        )
        optimized = self.optimizer_service.optimize(optimizer_request)

        sources = {destination.source}
        sources.update(p.source for p in candidates)
        sources.update(r.source for r in restaurants)
        sources.update(h.source for h in hotels)
        ordered_sources = sorted(sources, key=lambda s: s.value)
        development_only = any(s.is_development_only for s in ordered_sources)

        known_source_count = sum(1 for p in candidates if p.source in {DataSource.REAL, DataSource.EXTERNAL_API, DataSource.USER_GENERATED})
        if development_only:
            confidence = ConfidenceLevel.LOW
        elif known_source_count >= 20:
            confidence = ConfidenceLevel.MEDIUM
        elif known_source_count > 0:
            confidence = ConfidenceLevel.LOW
        else:
            confidence = ConfidenceLevel.UNKNOWN

        quality_notes = []
        if live_destination or any(p.source == DataSource.EXTERNAL_API for p in candidates):
            quality_notes.append("Live OpenStreetMap data was used. Visit duration and intensity are planner estimates where OSM did not provide those facts; they are not claims about the destination. OSM data © OpenStreetMap contributors, available under ODbL.")
        if development_only:
            quality_notes.append("Development-only records are present; they must not be presented as live travel facts.")
        if not restaurants and request.options.include_restaurants:
            quality_notes.append("No restaurant records were available for this destination.")
        if not hotels and request.options.include_hotels:
            quality_notes.append("No hotel records were available for this destination.")

        route_legs, aggregate_route = self._build_route_legs(trip, [destination.name])
        travel_method = self.travel_method_service.recommend(
            distance_km=aggregate_route.distance_km if aggregate_route else None,
            route=aggregate_route,
            preferred_travel_methods=(
                [m.value for m in trip.preferred_travel_methods]
                if trip.preferred_travel_methods
                else self._legacy_transport_preference_methods(trip.transport_preference)
            ),
            avoid_travel_methods=[m.value for m in trip.avoid_travel_methods] if trip.avoid_travel_methods else None,
            travellers=trip.travellers,
            fuel_type=trip.vehicle_fuel_type,
            mileage_kmpl=trip.vehicle_mileage_kmpl,
            fuel_price_inr_per_litre=trip.fuel_price_inr_per_litre,
        )
        if route_legs:
            quality_notes.append(
                "Live road routing is available for route legs marked available; unavailable legs indicate missing coordinates or provider data."
            )

        budget_status = self._calculate_budget_status(trip, optimized.itinerary, route_legs, travel_method)

        rec_status = self.recommendation_service.engine_status()
        tt_status = self.travel_time_service.engine_status()
        tc_status = self.travel_cost_service.engine_status()

        return PlanGenerationResult(
            plan_id=optimized.itinerary.plan_id,
            destination_id=destination.id,
            destination_name=destination.name,
            trip=trip,
            itinerary=optimized.itinerary,
            recommendations=recommendations,
            changes=optimized.changes,
            rejected_place_ids=optimized.rejected_place_ids,
            feasible=optimized.feasible,
            objective_score=optimized.objective_score,
            optimizer_method=optimized.optimizer_method,
            iterations=optimized.iterations,
            conflicts=optimized.conflicts,
            warnings=optimized.warnings,
            engine=EngineStatus(
                recommendation_method=rec_status.scoring_method.value,
                recommendation_model_loaded=rec_status.model_loaded,
                recommendation_model_production=rec_status.model_is_production,
                travel_time_method=tt_status.scoring_method.value,
                travel_time_model_loaded=tt_status.model_loaded,
                travel_time_model_production=tt_status.model_is_production,
                travel_cost_method=tc_status.scoring_method.value,
                travel_cost_model_loaded=tc_status.model_loaded,
                travel_cost_model_production=tc_status.model_is_production,
                optimizer_method=optimized.optimizer_method,
            ),
            data_quality=DataQuality(
                sources=ordered_sources,
                development_only=development_only,
                destinations=1,
                candidates=len(candidates),
                restaurants=len(restaurants),
                hotels=len(hotels),
                recommendations=len(recommendations),
                confidence=confidence,
                notes=quality_notes,
            ),
            route_legs=route_legs,
            travel_method=travel_method,
            budget_status=budget_status,
            notes=[
                "E3 orchestrates existing recommendation, travel prediction, E2 optimization, E1 validation, and routing layers.",
                "The orchestrator does not invent missing prices, opening hours, routes, or ratings.",
                "Route distances and durations are live only when the route leg source is OSRM and status is available.",
                "The future API should call PlannerService.generate() rather than individual intelligence layers.",
            ],
        )
