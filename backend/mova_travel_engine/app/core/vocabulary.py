"""Controlled tag vocabulary.

The recommendation model (Phase C) needs a stable tag space, but the frontend
sends free text ("Beach", "water sports"). We normalise free text onto this
vocabulary. Unknown tags are KEPT (never silently dropped); later phases report
them as assumptions ("tag xyz is not recognised and was ignored by the model").
"""

CANONICAL_TAGS = frozenset(
    {
        "beaches", "food", "nature", "history", "culture", "nightlife", "clubs",
        "crowds", "adventure", "shopping", "religious", "wildlife", "wellness",
        "photography", "markets", "water_sports", "hiking", "waterfalls",
        "museums", "architecture", "relaxation", "scenic_views",
        "local_experiences",
    }
)

# key = normalised form (lowercase, underscores) -> canonical tag
TAG_SYNONYMS = {
    "beach": "beaches", "seaside": "beaches", "coast": "beaches",
    "foodie": "food", "cuisine": "food", "eating": "food", "restaurants": "food",
    "natural": "nature", "outdoors": "nature",
    "temple": "religious", "temples": "religious", "spiritual": "religious",
    "heritage": "history", "historical": "history",
    "night_life": "nightlife", "party": "nightlife", "parties": "nightlife",
    "club": "clubs", "crowd": "crowds", "crowded": "crowds",
    "trek": "hiking", "trekking": "hiking",
    "waterfall": "waterfalls", "museum": "museums", "market": "markets",
    "watersports": "water_sports", "wild_life": "wildlife",
    "spa": "wellness", "yoga": "wellness", "photo": "photography",
    "views": "scenic_views", "viewpoints": "scenic_views", "relax": "relaxation",
}
