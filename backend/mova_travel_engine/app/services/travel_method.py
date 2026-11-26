"""Deterministic travel-method recommendation for MOVA.

This service deliberately does not invent train, bus or flight schedules/fares.
It ranks genuinely available routing information first and labels unsupported
modes explicitly so the UI can distinguish live, estimated and unavailable data.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.schemas.common import TransportPreference
from app.schemas.routing import RouteResult, TravelMethodRecommendation, TravelOption


@dataclass(frozen=True)
class TravelMethodService:
    """Recommend a practical mode from available route evidence."""

    def recommend(
        self,
        *,
        distance_km: float | None,
        route: RouteResult | None,
        preferred_travel_methods: list[str] | None = None,
        avoid_travel_methods: list[str] | None = None,
        travellers: int,
        fuel_type: str | None = None,
        mileage_kmpl: float | None = None,
        fuel_price_inr_per_litre: float | None = None,
        round_trip: bool = True,
    ) -> TravelMethodRecommendation:
        options: list[TravelOption] = []
        preferred = preferred_travel_methods or []
        avoid = avoid_travel_methods or []

        fuel_cost = None
        if route is not None and route.status == "available" and mileage_kmpl and fuel_price_inr_per_litre is not None:
            distance = route.distance_km * (2 if round_trip else 1)
            fuel_cost = round((distance / mileage_kmpl) * fuel_price_inr_per_litre, 2)

        if route is not None and route.status == "available":
            options.append(TravelOption(
                mode="car",
                duration_minutes=route.duration_minutes,
                distance_km=route.distance_km,
                estimated_cost_inr=fuel_cost,
                status="LIVE",
                source=route.source,
                reason=("Road distance/duration are live; fuel cost uses your vehicle mileage and fuel price." if fuel_cost is not None else "Road distance and duration are available from the live routing provider. Fuel inputs are required for a fuel-cost estimate."),
            ))
            options.append(TravelOption(
                mode="cab",
                duration_minutes=route.duration_minutes,
                distance_km=route.distance_km,
                estimated_cost_inr=None,
                status="ESTIMATED",
                source="OSRM",
                reason="Cab uses the same road route; a live cab fare provider is not integrated.",
            ))

        unsupported = ["train", "bus", "flight", "walk", "two_wheeler", "ferry"]
        for mode in unsupported:
            options.append(TravelOption(
                mode=mode,
                duration_minutes=None,
                distance_km=distance_km,
                estimated_cost_inr=None,
                status="NOT_INTEGRATED",
                source=None,
                reason=f"Live {mode} schedules/fares are not currently integrated.",
            ))

        valid_options = [o for o in options if o.mode not in avoid]

        recommended = None
        reason = ""

        if not valid_options:
            reason = "All available travel options were excluded by preferences."
        else:
            for pref in preferred:
                match = next((o for o in valid_options if o.mode == pref), None)
                if match:
                    recommended = match.mode
                    if match.status != "NOT_INTEGRATED":
                        reason = f"{pref.title()} was explicitly selected and is available."
                    else:
                        reason = f"{pref.title()} was explicitly selected, but live provider integration is not currently available."
                    break

            if not recommended:
                live_match = next((o for o in valid_options if o.status == "LIVE"), None)
                if live_match:
                    recommended = live_match.mode
                    reason = f"{live_match.mode.title()} is the best available live option."
                else:
                    recommended = valid_options[0].mode
                    reason = "No preferred live option was available; selected fallback."

        return TravelMethodRecommendation(
            recommended_mode=recommended,
            options=options,
            reason=reason,
            travellers=travellers,
            source="MOVA_DETERMINISTIC",
        )
