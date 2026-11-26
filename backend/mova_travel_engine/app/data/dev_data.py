"""Synthetic DEVELOPMENT dataset generator (Goa sample).

!! EVERY record produced here has source="synthetic_dev". It exists only so the
!! engine can be exercised end-to-end before real data exists. It is NOT tourism
!! information and must never be shown to users as such.

What is real vs invented:
  * Places: the NAME and a rough (~km-level) location are those of well-known
    Goa landmarks so that geography (North/Central/South clustering) is
    realistic. Fees, hours, ratings, durations, popularity, etc. are invented.
  * Restaurants and hotels: entirely fictional ("DEV ..." names).
  * Transport: rough typical durations/prices between big cities and Goa, jittered.
Confidence values are deliberately low. The generator is seeded and deterministic
(same seed + same generated_at => identical output) and contains NO itineraries.

Destination-agnostic design: the engine never imports this module; only scripts
and tests do. Other destinations can be added by adding another generator.
"""
import datetime as dt
import random
from dataclasses import dataclass, field
from pathlib import Path

from app.data.dataset_validation import ValidationReport, validate_collections
from app.data.loaders import DATASET_SPECS, DatasetMeta, write_dataset_file
from app.data.repositories.base import Repositories
from app.data.repositories.json_repos import json_repositories_in_memory
from app.schemas.common import (
    DataSource, DietaryPreference as D, HotelCategory, MealType as M,
    PlaceCategory as C, TimeOfDay as TOD, TransportMode,
)
from app.schemas.logistics import TransportOption
from app.schemas.place import Destination, GeoPoint, Hotel, OpeningHours, Place, Restaurant, TimeWindow

SRC = DataSource.SYNTHETIC_DEV
DISCLAIMER = ("SYNTHETIC DEVELOPMENT DATA - NOT REAL TRAVEL INFORMATION. Landmark names/locations are "
              "approximate; all other attributes are generated for testing only.")
CONF = {"destination": 0.3, "place": 0.2, "restaurant": 0.1, "hotel": 0.1, "transport": 0.2}
DEST_ID = "goa"
_FORBIDDEN_DIRS = {"raw"}  # never write synthetic data into the real-data folder


def _clock_hours(key: str) -> OpeningHours | None:
    w = TimeWindow
    if key == "always":
        return OpeningHours(always_open=True)
    if key == "unknown":
        return None
    if key.startswith("daily_"):  # daily_0900_1730
        _, a, b = key.split("_")
        return OpeningHours.daily(f"{a[:2]}:{a[2:]}", f"{b[:2]}:{b[2:]}")
    if key == "temple":  # split window: a visit cannot span the midday break
        return OpeningHours(weekly={d: [w(open="06:00", close="12:30"), w(open="16:00", close="20:00")]
                                    for d in range(7)})
    if key == "market_mon_sat":
        return OpeningHours(weekly={d: [w(open="09:00", close="19:30")] for d in range(6)})
    if key == "wed_only":
        return OpeningHours(weekly={2: [w(open="08:30", close="18:00")]})
    if key == "lunch_dinner":
        return OpeningHours(weekly={d: [w(open="12:00", close="15:30"), w(open="19:00", close="22:30")]
                                    for d in range(7)})
    if key == "bakery_closed_sun":
        return OpeningHours(weekly={d: [w(open="07:00", close="19:00")] for d in range(6)})
    raise ValueError(f"unknown hours key {key}")


@dataclass(frozen=True)
class _P:  # place seed
    slug: str; name: str; cat: C; tags: tuple; lat: float; lng: float; visit: int; intensity: int
    hours: str; fee: tuple = (0, 0); closed: tuple = (); best: tuple = (); tod: tuple = ()
    family: bool | None = None; wheel: bool | None = None; pop: float = 0.5; crowd: float = 0.5
    unknown: tuple = ()


_WINTER = (11, 12, 1, 2, 3)
PLACES = [
    # ---- North Goa
    _P("baga_beach", "Baga Beach", C.BEACH, ("beaches", "water_sports", "nightlife", "crowds"), 15.5553, 73.7517, 150, 2, "always", best=_WINTER, tod=(TOD.MORNING, TOD.EVENING), family=True, wheel=False, pop=.9, crowd=.9),
    _P("calangute_beach", "Calangute Beach", C.BEACH, ("beaches", "crowds", "food"), 15.5440, 73.7550, 120, 1, "always", best=_WINTER, family=True, pop=.9, crowd=.85),
    _P("anjuna_beach", "Anjuna Beach", C.BEACH, ("beaches", "photography", "relaxation"), 15.5736, 73.7413, 120, 1, "always", best=_WINTER, family=True, pop=.75, crowd=.6),
    _P("vagator_beach", "Vagator Beach", C.BEACH, ("beaches", "scenic_views", "photography"), 15.6006, 73.7353, 120, 2, "always", best=_WINTER, pop=.7, crowd=.55),
    _P("candolim_beach", "Candolim Beach", C.BEACH, ("beaches", "relaxation"), 15.5180, 73.7623, 120, 1, "always", best=_WINTER, family=True, pop=.6, crowd=.5),
    _P("fort_aguada", "Fort Aguada", C.HISTORICAL, ("history", "scenic_views", "photography"), 15.4925, 73.7734, 90, 2, "daily_0830_1730", fee=(0, 100), family=True, pop=.8, crowd=.6),
    _P("chapora_fort", "Chapora Fort", C.HISTORICAL, ("history", "scenic_views", "hiking"), 15.6058, 73.7362, 60, 3, "unknown", pop=.65, crowd=.4, unknown=("hours",)),
    _P("mapusa_market", "Mapusa Market", C.MARKET, ("markets", "shopping", "local_experiences", "food"), 15.5915, 73.8090, 90, 1, "market_mon_sat", pop=.55, crowd=.7),
    _P("anjuna_flea_market", "Anjuna Flea Market", C.MARKET, ("markets", "shopping", "local_experiences", "crowds"), 15.5740, 73.7400, 120, 1, "wed_only", pop=.7, crowd=.85),
    _P("reis_magos_fort", "Reis Magos Fort", C.HISTORICAL, ("history", "photography"), 15.5010, 73.8160, 60, 2, "daily_0930_1730", fee=(25, 75), pop=.4, crowd=.3),
    _P("baga_nightlife_strip", "Baga Nightlife Strip", C.NIGHTLIFE, ("nightlife", "clubs", "crowds"), 15.5570, 73.7530, 180, 2, "daily_2000_2359", fee=(0, 1500), pop=.85, crowd=.95),
    _P("calangute_water_sports", "Calangute Water Sports Zone", C.ADVENTURE, ("water_sports", "adventure", "beaches"), 15.5460, 73.7545, 120, 4, "daily_0900_1730", fee=(1500, 3500), pop=.7, crowd=.7),
    # ---- Central Goa
    _P("fontainhas", "Fontainhas Latin Quarter", C.CULTURAL, ("culture", "history", "photography", "architecture", "local_experiences"), 15.4966, 73.8300, 90, 1, "always", family=True, wheel=True, pop=.6, crowd=.4),
    _P("bom_jesus", "Basilica of Bom Jesus", C.RELIGIOUS, ("religious", "history", "architecture"), 15.5009, 73.9116, 60, 1, "daily_0900_1830", family=True, wheel=True, pop=.85, crowd=.7),
    _P("se_cathedral", "Se Cathedral", C.RELIGIOUS, ("religious", "history", "architecture"), 15.5030, 73.9115, 45, 1, "daily_0730_1800", family=True, wheel=True, pop=.7, crowd=.5),
    _P("dona_paula_viewpoint", "Dona Paula Viewpoint", C.VIEWPOINT, ("scenic_views", "photography", "relaxation"), 15.4530, 73.8040, 60, 1, "always", family=True, pop=.6, crowd=.6),
    _P("miramar_beach", "Miramar Beach", C.BEACH, ("beaches", "relaxation"), 15.4830, 73.8090, 90, 1, "always", family=True, pop=.5, crowd=.5),
    _P("mangueshi_temple", "Mangueshi Temple", C.RELIGIOUS, ("religious", "architecture", "culture"), 15.4520, 73.9770, 60, 1, "temple", family=True, pop=.6, crowd=.5),
    _P("ponda_spice_visit", "Ponda Spice Plantation Visit", C.NATURE, ("nature", "food", "local_experiences"), 15.4000, 74.0100, 150, 2, "daily_0900_1630", fee=(400, 800), family=True, pop=.6, crowd=.4),
    # ---- East Goa
    _P("dudhsagar_falls", "Dudhsagar Falls", C.WATERFALL, ("waterfalls", "nature", "adventure", "hiking"), 15.3144, 74.3143, 240, 4, "daily_0800_1700", fee=(400, 1200), closed=(6, 7, 8, 9), best=(10, 11, 12, 1, 2), tod=(TOD.MORNING,), pop=.9, crowd=.8),
    _P("mollem_sanctuary", "Mollem Wildlife Sanctuary", C.WILDLIFE, ("wildlife", "nature", "hiking"), 15.3900, 74.2500, 180, 3, "daily_0700_1730", fee=(30, 100), closed=(7, 8), best=(11, 12, 1, 2), pop=.5, crowd=.3),
    # ---- South Goa
    _P("colva_beach", "Colva Beach", C.BEACH, ("beaches", "crowds", "food"), 15.2790, 73.9220, 120, 1, "always", best=_WINTER, family=True, pop=.75, crowd=.7),
    _P("palolem_beach", "Palolem Beach", C.BEACH, ("beaches", "relaxation", "water_sports", "photography"), 15.0100, 74.0232, 180, 2, "always", best=_WINTER, family=True, pop=.85, crowd=.65),
    _P("agonda_beach", "Agonda Beach", C.BEACH, ("beaches", "relaxation", "nature"), 15.0450, 73.9865, 150, 1, "always", best=_WINTER, pop=.55, crowd=.3, unknown=("rating",)),
    _P("butterfly_beach", "Butterfly Beach", C.BEACH, ("beaches", "nature", "hiking"), 15.0246, 74.0084, 120, 3, "always", best=_WINTER, pop=.4, crowd=.2),
    _P("cabo_de_rama_fort", "Cabo de Rama Fort", C.HISTORICAL, ("history", "scenic_views", "photography"), 15.0890, 73.9240, 90, 2, "daily_0900_1730", pop=.45, crowd=.25),
    _P("cotigao_sanctuary", "Cotigao Wildlife Sanctuary", C.WILDLIFE, ("wildlife", "nature", "hiking"), 15.1000, 74.1700, 180, 3, "daily_0730_1730", fee=(30, 100), closed=(6, 7, 8), pop=.35, crowd=.1, unknown=("fee",)),
    _P("margao_market", "Margao Municipal Market", C.MARKET, ("markets", "food", "shopping", "local_experiences"), 15.2740, 73.9580, 75, 1, "market_mon_sat", pop=.4, crowd=.6),
]

AREAS = {  # slug: (display name, lat, lng)
    "calangute": ("Calangute", 15.5440, 73.7550), "baga": ("Baga", 15.5553, 73.7517),
    "anjuna": ("Anjuna", 15.5736, 73.7413), "candolim": ("Candolim", 15.5180, 73.7623),
    "panaji": ("Panaji", 15.4989, 73.8278), "margao": ("Margao", 15.2832, 73.9862),
    "colva": ("Colva", 15.2790, 73.9220), "palolem": ("Palolem", 15.0100, 74.0232),
}
# archetype: (label, cuisines, dietary, serves, price range INR/person, hours key)
ARCH = {
    "veg_thali": ("Veg Thali House", ("goan", "indian"), (D.VEGETARIAN, D.JAIN, D.VEGAN), (M.LUNCH, M.DINNER), (180, 320), "lunch_dinner"),
    "seafood": ("Seafood Shack", ("goan", "seafood"), (D.NON_VEGETARIAN, D.GLUTEN_FREE), (M.LUNCH, M.DINNER), (450, 900), "daily_1000_2230"),
    "cafe": ("Garden Cafe", ("continental", "cafe"), (D.VEGETARIAN, D.VEGAN, D.GLUTEN_FREE, D.EGGETARIAN), (M.BREAKFAST, M.LUNCH, M.SNACK), (300, 600), "daily_0730_1830"),
    "diner": ("Family Diner", ("indian", "chinese", "goan"), (D.VEGETARIAN, D.NON_VEGETARIAN, D.HALAL, D.JAIN), (M.BREAKFAST, M.LUNCH, M.DINNER), (250, 500), "daily_0800_2300"),
    "fine": ("Fine Dining Room", ("goan", "portuguese", "continental"), (D.VEGETARIAN, D.NON_VEGETARIAN, D.GLUTEN_FREE), (M.DINNER,), (1200, 2500), "daily_1830_2300"),
    "bakery": ("Bakery and Breakfast", ("bakery", "cafe"), (D.VEGETARIAN, D.EGGETARIAN, D.VEGAN), (M.BREAKFAST, M.SNACK), (100, 250), "bakery_closed_sun"),
}
RESTAURANT_PLAN = {
    "calangute": ("veg_thali", "seafood", "diner"), "baga": ("seafood", "cafe"), "anjuna": ("cafe", "seafood"),
    "candolim": ("fine", "veg_thali"), "panaji": ("veg_thali", "diner", "bakery", "fine"),
    "margao": ("veg_thali", "diner"), "colva": ("seafood", "cafe"), "palolem": ("cafe", "seafood", "veg_thali"),
}
HOTEL_CAT = {  # category: (price range INR/room/night, occupancy, rating range, amenities)
    HotelCategory.BUDGET: ((1200, 2600), 2, (3.4, 4.1), ("wifi",)),
    HotelCategory.MIDRANGE: ((3000, 6500), 3, (3.8, 4.5), ("wifi", "breakfast", "air_conditioning")),
    HotelCategory.PREMIUM: ((7000, 13000), 3, (4.1, 4.7), ("wifi", "breakfast", "pool", "air_conditioning")),
    HotelCategory.LUXURY: ((14000, 32000), 4, (4.3, 4.9), ("wifi", "breakfast", "pool", "spa", "air_conditioning")),
}
HB, HM, HP, HL = HotelCategory.BUDGET, HotelCategory.MIDRANGE, HotelCategory.PREMIUM, HotelCategory.LUXURY
HOTEL_PLAN = {"calangute": (HB, HM, HP), "anjuna": (HB, HM), "panaji": (HM, HP), "colva": (HM, HL),
              "palolem": (HB, HP), "candolim": (HP, HL)}
# origin: mode, typical minutes, price range INR/person  (rough magnitudes only)
TRANSPORT_PLAN = [
    ("Mumbai", TransportMode.FLIGHT, 80, (3000, 8000)), ("Mumbai", TransportMode.TRAIN, 660, (700, 2200)),
    ("Mumbai", TransportMode.BUS, 840, (900, 1800)),
    ("Pune", TransportMode.FLIGHT, 75, (3000, 7500)), ("Pune", TransportMode.TRAIN, 540, (600, 1800)),
    ("Pune", TransportMode.BUS, 720, (800, 1600)),
    ("Bengaluru", TransportMode.FLIGHT, 75, (3000, 8000)), ("Bengaluru", TransportMode.TRAIN, 800, (700, 2000)),
    ("Bengaluru", TransportMode.BUS, 840, (900, 1800)),
    ("Hyderabad", TransportMode.FLIGHT, 95, (3500, 9000)), ("Hyderabad", TransportMode.TRAIN, 1200, (800, 2400)),
    ("Hyderabad", TransportMode.BUS, 900, (1000, 2000)),
    ("Delhi", TransportMode.FLIGHT, 165, (4500, 11000)), ("Delhi", TransportMode.TRAIN, 1620, (1200, 3500)),
]


def _round_to(x: float, base: int) -> int:
    return int(round(x / base) * base)


@dataclass(frozen=True)
class DevDataset:
    destinations: list[Destination]
    places: list[Place]
    restaurants: list[Restaurant]
    hotels: list[Hotel]
    transport: list[TransportOption]
    metas: dict[str, DatasetMeta] = field(default_factory=dict)

    def collections(self) -> dict[str, list]:
        return {"destinations": self.destinations, "places": self.places, "restaurants": self.restaurants,
                "hotels": self.hotels, "transport": self.transport}

    def repositories(self) -> Repositories:
        return json_repositories_in_memory(
            destinations=self.destinations, places=self.places, restaurants=self.restaurants,
            hotels=self.hotels, transport=self.transport)

    def validate(self) -> ValidationReport:
        return validate_collections(**self.collections(), metas=self.metas)


def generate_goa_dev_dataset(seed: int = 42, generated_at: dt.datetime | None = None) -> DevDataset:
    """Deterministic for a given (seed, generated_at). Raises if it would emit invalid data."""
    ts = generated_at or dt.datetime.now(dt.timezone.utc)
    common = lambda kind: dict(source=SRC, last_updated=ts, confidence=CONF[kind])  # noqa: E731

    destination = Destination(
        id=DEST_ID, name="Goa", state="Goa", center=GeoPoint(latitude=15.4909, longitude=73.8278),
        aliases=["Goa India", "Goa, India"], best_months=[11, 12, 1, 2, 3],
        description="SYNTHETIC DEV RECORD. Approximate centre (Panaji).", **common("destination"))

    rng = random.Random(f"{seed}:places")
    places = []
    for s in PLACES:
        lo, hi = s.fee
        fee = 0.0 if hi == 0 else float(_round_to(rng.uniform(lo, hi), 10))
        rating = round(rng.uniform(3.7, 4.7), 1)
        places.append(Place(
            id=f"{DEST_ID}_{s.slug}", destination_id=DEST_ID, name=s.name, category=s.cat, tags=list(s.tags),
            location=GeoPoint(latitude=s.lat, longitude=s.lng),
            rating=None if "rating" in s.unknown else rating,
            rating_count=None if "rating" in s.unknown else int(s.pop * rng.uniform(2000, 20000)),
            popularity=round(min(1, max(0, s.pop + rng.uniform(-.05, .05))), 2),
            crowd_level=round(min(1, max(0, s.crowd + rng.uniform(-.05, .05))), 2),
            avg_visit_minutes=max(15, _round_to(s.visit * rng.uniform(.9, 1.1), 15)),
            entry_fee_inr=None if "fee" in s.unknown else fee, intensity=s.intensity,
            opening_hours=None if "hours" in s.unknown else _clock_hours(s.hours),
            closed_months=list(s.closed), best_months=list(s.best), best_times_of_day=list(s.tod),
            family_friendly=s.family, wheelchair_accessible=s.wheel,
            description="SYNTHETIC DEV RECORD: real landmark name/approx. location; all other attributes are "
                        "generated and NOT verified.", **common("place")))

    rr = random.Random(f"{seed}:restaurants")
    restaurants = []
    for area, kinds in RESTAURANT_PLAN.items():
        aname, alat, alng = AREAS[area]
        for k in kinds:
            label, cuisines, diet, serves, (plo, phi), hours = ARCH[k]
            restaurants.append(Restaurant(
                id=f"{DEST_ID}_rest_{area}_{k}", destination_id=DEST_ID, name=f"DEV {label} - {aname}",
                location=GeoPoint(latitude=round(alat + rr.uniform(-.004, .004), 5),
                                  longitude=round(alng + rr.uniform(-.004, .004), 5)),
                cuisines=list(cuisines), dietary_options=list(diet), serves=list(serves),
                avg_price_per_person_inr=float(_round_to(rr.uniform(plo, phi), 10)),
                rating=round(rr.uniform(3.5, 4.6), 1), opening_hours=_clock_hours(hours), **common("restaurant")))

    hr = random.Random(f"{seed}:hotels")
    hotels = []
    for area, cats in HOTEL_PLAN.items():
        aname, alat, alng = AREAS[area]
        for cat in cats:
            (plo, phi), occ, (rlo, rhi), amen = HOTEL_CAT[cat]
            hotels.append(Hotel(
                id=f"{DEST_ID}_hotel_{area}_{cat.value}", destination_id=DEST_ID,
                name=f"DEV {cat.value.title()} Stay - {aname}", category=cat,
                location=GeoPoint(latitude=round(alat + hr.uniform(-.004, .004), 5),
                                  longitude=round(alng + hr.uniform(-.004, .004), 5)),
                price_per_night_inr=float(_round_to(hr.uniform(plo, phi), 100)), max_occupancy_per_room=occ,
                rating=round(hr.uniform(rlo, rhi), 1), amenities=list(amen), **common("hotel")))

    tr = random.Random(f"{seed}:transport")
    transport = []
    for origin, mode, minutes, (plo, phi) in TRANSPORT_PLAN:
        transport.append(TransportOption(
            id=f"{DEST_ID}_tr_{origin.lower()}_{mode.value}", mode=mode, origin=origin, destination="Goa",
            duration_minutes=max(5, _round_to(minutes * tr.uniform(.95, 1.05), 5)),
            price_per_person_inr=float(_round_to(tr.uniform(plo, phi), 50)), **common("transport")))

    metas = {name: DatasetMeta(dataset="goa_dev", data_source=SRC, generated_at=ts,
                               generated_by="app.data.dev_data", seed=seed, disclaimer=DISCLAIMER)
             for name in DATASET_SPECS}
    ds = DevDataset([destination], places, restaurants, hotels, transport, metas)
    report = ds.validate()
    if not report.ok:  # generator bug, not a data problem
        raise RuntimeError("dev generator produced invalid data: "
                           + "; ".join(i.message for i in report.issues if i.severity == "error"))
    return ds


def write_dev_dataset(dataset: DevDataset, out_dir: Path | str, *, force: bool = False) -> list[Path]:
    out = Path(out_dir)
    if any(part.lower() in _FORBIDDEN_DIRS for part in out.resolve().parts):
        raise ValueError(f"refusing to write synthetic data under a 'raw' directory: {out}")
    targets = {name: out / spec.filename for name, spec in DATASET_SPECS.items()}
    existing = [str(p) for p in targets.values() if p.exists()]
    if existing and not force:
        raise FileExistsError("files already exist (use force/--force to overwrite): " + ", ".join(existing))
    written = []
    for name, records in dataset.collections().items():
        write_dataset_file(targets[name], records, dataset.metas.get(name))
        written.append(targets[name])
    return written
