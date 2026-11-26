"""Domain errors. The API layer (Phase J) maps these to HTTP responses."""


class MovaError(Exception):
    """Base class. `code` is a stable machine-readable identifier."""

    code = "mova_error"

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidTripRequestError(MovaError):
    code = "invalid_trip_request"


class NotFoundError(MovaError):
    code = "not_found"


class DataUnavailableError(MovaError):
    """Required data (places, prices, history) is missing or empty."""

    code = "data_unavailable"


class ProviderError(MovaError):
    """An external provider (routes, weather, ...) failed or returned junk."""

    code = "provider_error"


class InfeasiblePlanError(MovaError):
    """No plan satisfies the hard constraints."""

    code = "infeasible_plan"


class DataLoadError(MovaError):
    """A dataset file is missing, unreadable, or (in strict mode) contains malformed records."""

    code = "data_load_error"


class DuplicateRecordError(MovaError):
    code = "duplicate_record"


class InsufficientTrainingDataError(MovaError):
    """Not enough (or not real enough) labelled examples to train the requested model purpose."""

    code = "insufficient_training_data"


class ModelLoadError(MovaError):
    """A saved model artifact is missing, corrupt, or was trained on a different feature schema."""

    code = "model_load_error"
