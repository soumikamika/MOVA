"""Project-wide sanity limits. These are input-safety bounds, not travel logic."""

MAX_TRIP_DAYS = 30
MAX_TRAVELLERS = 50
MAX_BUDGET_INR = 100_000_000  # 10 crore; guards against typos / overflow
MAX_TAGS_PER_LIST = 20
DEFAULT_CURRENCY = "INR"
DEFAULT_TIMEZONE = "Asia/Kolkata"
