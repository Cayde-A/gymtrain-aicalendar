#!/usr/bin/env python3
"""Shared Garmin transport and authentication boundary for TrainingOS.

Only Garmin-specific connection concerns belong here. Raw response
normalization and all training decisions remain in TrainingOS-owned modules.
"""

from __future__ import annotations

import contextlib
import getpass
import os
import time
from dataclasses import asdict, dataclass, replace
from importlib import metadata
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOKENSTORE = ROOT / "tokens" / "garmin"
V03_TOKENSTORE = ROOT / "tokens" / "garmin-v03"
DEFAULT_PERSONAL_API_KEY_FILE = Path("~/.config/garmin/connect-personal-api-key")
DEFAULT_PERSONAL_BEARER_CACHE_FILE = Path(
    "~/.config/garmin/connect-personal-api-bearer-token.json"
)
LEGACY_SOURCE_TOOL = "python-garminconnect"
PERSONAL_SOURCE_TOOL = "garmin-connect-personal-api-python"
# Backward-compatible name for the write provider. Read provenance is resolved
# from the selected client at runtime.
SOURCE_TOOL = LEGACY_SOURCE_TOOL
CAPABILITY_METHODS = {
    "daily_summary": ("get_stats", "get_user_summary"),
    "sleep": ("get_sleep_data", "get_sleep"),
    "hrv": ("get_hrv_data", "get_hrv"),
    "body_battery": ("get_body_battery", "get_body_battery_events"),
    "training_readiness": ("get_training_readiness", "get_training_readiness_data"),
    "activities": ("get_activities_by_date",),
    "activity_details": ("get_activity", "get_activity_details"),
    "activity_sets": ("get_activity_exercise_sets",),
    "activity_workouts": ("get_activity_workouts",),
    "activity_download": ("download_activity",),
    "workout_upload": ("upload_strength_workout", "upload_workout"),
    "workout_schedule": ("schedule_workout", "get_scheduled_workouts", "unschedule_workout"),
    "workout_device_push": ("push_workout_to_device",),
}


class GarminPersonalReadClient:
    """Compatibility adapter for Garmin's official, pull-only Personal API."""

    source_tool = PERSONAL_SOURCE_TOOL
    read_only = True

    def __init__(self, client: Any):
        self._client = client

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()

    def get_stats(self, calendar_date: str) -> Any:
        return self._client.get_daily_summaries(calendar_date, calendar_date)

    def get_user_summary(self, calendar_date: str) -> Any:
        return self.get_stats(calendar_date)

    def get_sleep_data(self, calendar_date: str) -> Any:
        return self._client.get_daily_sleep(calendar_date)

    def get_sleep(self, calendar_date: str) -> Any:
        return self.get_sleep_data(calendar_date)

    def get_hrv_data(self, calendar_date: str) -> Any:
        return self._client.get_daily_hrv(calendar_date)

    def get_hrv(self, calendar_date: str) -> Any:
        return self.get_hrv_data(calendar_date)

    def get_body_battery(self, calendar_date: str) -> Any:
        return self._client.get_daily_body_battery(calendar_date, calendar_date)

    def get_activities_by_date(
        self,
        start_date: str,
        end_date: str,
        activity_type: str | None = None,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        offset = 0
        page_size = 100
        while True:
            page = self._client.search_activities(
                start=offset,
                limit=page_size,
                start_date=start_date,
                end_date=end_date,
                activity_type=activity_type,
            )
            if isinstance(page, dict):
                page = page.get("activityList") or page.get("activities") or page.get("data") or []
            if not isinstance(page, list):
                break
            items = [item for item in page if isinstance(item, dict)]
            records.extend(items)
            if len(items) < page_size:
                break
            offset += len(items)
        return records

    def get_activity(self, activity_id: str | int) -> Any:
        return self._client.get_activity(activity_id)

    def get_activity_details(self, activity_id: str | int) -> Any:
        return self.get_activity(activity_id)

    def get_activity_exercise_sets(self, activity_id: str | int) -> Any:
        details = self._client.get_activity(activity_id)
        if not isinstance(details, dict):
            return None
        exercise_sets = (
            details.get("summarizedExerciseSets")
            or details.get("exerciseSets")
            or details.get("activityExerciseSets")
        )
        return {"exerciseSets": exercise_sets} if exercise_sets else None

    def get_activity_workouts(self, activity_id: str | int) -> Any:
        return self._client.get_activity_workouts(activity_id)

    def download_activity(self, activity_id: str | int) -> bytes:
        return self._client.download_activity(activity_id)


class ErrorCode:
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    SCHEMA = "schema"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    PROVIDER_OUTAGE = "provider_outage"
    CONFIRMATION_FAILED = "confirmation_failed"
    AMBIGUOUS_WRITE = "ambiguous_write"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProviderFailure:
    code: str
    message: str
    retryable: bool
    operation: str | None = None
    status_code: int | None = None
    attempts: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GarminProviderError(RuntimeError):
    def __init__(self, failure: ProviderFailure):
        super().__init__(failure.message)
        self.failure = failure

    def to_dict(self) -> dict[str, Any]:
        return self.failure.to_dict()


def load_dotenv_local() -> None:
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def import_garmin_client() -> Any:
    try:
        from garminconnect import Garmin  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: garminconnect. Install with:\n"
            "  python3 -m pip install -r requirements.txt"
        ) from exc
    return Garmin


def import_personal_api() -> tuple[Any, Any, Any]:
    try:
        from garmin_personal_api import (  # type: ignore
            GarminPersonalApiClient,
            PersonalApiAuthenticator,
            resolve_api_key,
        )
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: garmin-connect-personal-api-python. Install with:\n"
            "  python3 -m pip install -r requirements.txt"
        ) from exc
    return GarminPersonalApiClient, PersonalApiAuthenticator, resolve_api_key


def package_version(source_tool: str = LEGACY_SOURCE_TOOL) -> str | None:
    package_name = (
        "garmin-connect-personal-api-python"
        if source_tool == PERSONAL_SOURCE_TOOL
        else "garminconnect"
    )
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return None


def client_source_tool(client: Any | None) -> str:
    return str(getattr(client, "source_tool", LEGACY_SOURCE_TOOL))


def detect_capabilities(client: Any) -> dict[str, bool]:
    return {
        capability: any(callable(getattr(client, method_name, None)) for method_name in method_names)
        for capability, method_names in CAPABILITY_METHODS.items()
    }


def provider_metadata(client: Any | None = None) -> dict[str, Any]:
    source_tool = client_source_tool(client)
    return {
        "source_tool": source_tool,
        "version": package_version(source_tool),
        "read_only": bool(getattr(client, "read_only", False)) if client is not None else None,
        "capabilities": detect_capabilities(client) if client is not None else None,
    }


def _status_code(exc: Exception) -> int | None:
    direct = getattr(exc, "status_code", None)
    if isinstance(direct, int):
        return direct
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def classify_error(exc: Exception, operation: str | None = None) -> ProviderFailure:
    status_code = _status_code(exc)
    message = str(exc).strip() or type(exc).__name__
    text = message.lower()

    if status_code == 429 or "too many requests" in text or "rate limit" in text:
        code, retryable = ErrorCode.RATE_LIMIT, True
    elif status_code in {401, 403} or any(
        term in text for term in ("authentication", "unauthorized", "credential", "login", "oauth", "token", "mfa")
    ):
        code, retryable = ErrorCode.AUTHENTICATION, False
    elif isinstance(exc, AttributeError) or status_code in {404, 405}:
        code, retryable = ErrorCode.CAPABILITY_UNAVAILABLE, False
    elif isinstance(exc, (KeyError, TypeError, ValueError)) or status_code in {400, 409, 422}:
        code, retryable = ErrorCode.SCHEMA, False
    elif isinstance(exc, (ConnectionError, TimeoutError)) or (status_code is not None and status_code >= 500):
        code, retryable = ErrorCode.PROVIDER_OUTAGE, True
    else:
        code, retryable = ErrorCode.UNKNOWN, False

    return ProviderFailure(
        code=code,
        message=message[:500],
        retryable=retryable,
        operation=operation,
        status_code=status_code,
    )


def execute(operation: str, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        return callback(*args, **kwargs)
    except GarminProviderError:
        raise
    except Exception as exc:
        raise GarminProviderError(classify_error(exc, operation)) from exc


def execute_with_retry(
    operation: str,
    callback: Callable[..., Any],
    *args: Any,
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
    sleeper: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> Any:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    for attempt in range(1, max_attempts + 1):
        try:
            return execute(operation, callback, *args, **kwargs)
        except GarminProviderError as exc:
            failure = replace(exc.failure, attempts=attempt)
            # Re-authentication during a rate limit usually extends the block.
            should_retry = (
                failure.retryable
                and failure.code != ErrorCode.RATE_LIMIT
                and attempt < max_attempts
            )
            if not should_retry:
                raise GarminProviderError(failure) from exc
            sleeper(base_delay_seconds * (2 ** (attempt - 1)))
    raise AssertionError("retry loop exhausted without returning or raising")


def call_first_available(client: Any, candidates: list[tuple[str, tuple[Any, ...]]]) -> dict[str, Any]:
    failures: dict[str, dict[str, Any]] = {}
    for method_name, args in candidates:
        method = getattr(client, method_name, None)
        if not callable(method):
            failures[method_name] = ProviderFailure(
                code=ErrorCode.CAPABILITY_UNAVAILABLE,
                message="method not available",
                retryable=False,
                operation=method_name,
            ).to_dict()
            continue
        try:
            return {
                "source_method": method_name,
                "ok": True,
                "data": method(*args),
            }
        except Exception as exc:  # noqa: BLE001 - try compatible endpoint variants.
            failures[method_name] = classify_error(exc, method_name).to_dict()

    overall = next(
        (failure for failure in failures.values() if failure["code"] != ErrorCode.CAPABILITY_UNAVAILABLE),
        ProviderFailure(
            code=ErrorCode.CAPABILITY_UNAVAILABLE,
            message="no compatible Garmin method is available",
            retryable=False,
            operation="call_first_available",
        ).to_dict(),
    )
    return {"ok": False, "error": overall, "failures": failures}


def has_tokens(tokenstore: Path) -> bool:
    return (
        ((tokenstore / "oauth1_token.json").exists() and (tokenstore / "oauth2_token.json").exists())
        or (tokenstore / "garmin_tokens.json").exists()
    )


def default_tokenstore() -> Path:
    configured = os.getenv("GARMINTOKENS")
    if configured:
        return Path(configured).expanduser()
    if V03_TOKENSTORE.exists():
        return V03_TOKENSTORE
    return DEFAULT_TOKENSTORE


def default_personal_api_key_file() -> Path:
    return Path(
        os.getenv("GARMIN_PERSONAL_API_KEY_FILE", str(DEFAULT_PERSONAL_API_KEY_FILE))
    ).expanduser()


def default_personal_bearer_cache_file() -> Path:
    return Path(
        os.getenv(
            "GARMIN_PERSONAL_BEARER_CACHE_FILE",
            str(DEFAULT_PERSONAL_BEARER_CACHE_FILE),
        )
    ).expanduser()


def has_personal_api_key(key_file: str | Path | None = None) -> bool:
    if os.getenv("GARMIN_PERSONAL_API_KEY", "").strip():
        return True
    path = Path(key_file).expanduser() if key_file else default_personal_api_key_file()
    try:
        return bool(path.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def login_personal_read(
    key_file: str | Path | None = None,
    bearer_cache_file: str | Path | None = None,
) -> GarminPersonalReadClient:
    GarminPersonalApiClient, PersonalApiAuthenticator, resolve_api_key = import_personal_api()
    resolved_cache_file = (
        Path(bearer_cache_file).expanduser()
        if bearer_cache_file
        else default_personal_bearer_cache_file()
    )
    try:
        configured_key_file = key_file or os.getenv("GARMIN_PERSONAL_API_KEY_FILE")
        api_key = (
            resolve_api_key(key_file=Path(configured_key_file).expanduser())
            if configured_key_file
            else resolve_api_key()
        )
        with PersonalApiAuthenticator(
            bearer_token_cache_file=resolved_cache_file
        ) as authenticator:
            token = authenticator.obtain_token(api_key)
        return GarminPersonalReadClient(GarminPersonalApiClient(token.access_token))
    except Exception as exc:
        raise GarminProviderError(classify_error(exc, "personal_api_login")) from exc


def login_read(
    email: str | None,
    password: str | None,
    tokenstore: str | Path,
    *,
    provider: str | None = None,
    personal_api_key_file: str | Path | None = None,
) -> Any:
    selected = (provider or os.getenv("GARMIN_READ_PROVIDER", "auto")).strip().lower()
    if selected not in {"auto", "personal", "legacy"}:
        raise ValueError("GARMIN_READ_PROVIDER must be auto, personal, or legacy")
    if selected == "personal" or (
        selected == "auto" and has_personal_api_key(personal_api_key_file)
    ):
        return login_personal_read(personal_api_key_file)
    return login(email, password, tokenstore)


def login(email: str | None, password: str | None, tokenstore: str | Path) -> Any:
    Garmin = import_garmin_client()
    tokenstore_path = Path(tokenstore).expanduser()

    email = email or os.getenv("GARMIN_EMAIL")
    password = password or os.getenv("GARMIN_PASSWORD")
    if not has_tokens(tokenstore_path):
        if not email:
            email = input("Garmin email: ").strip()
        if not password:
            password = getpass.getpass("Garmin password: ")

    client = Garmin(email, password) if email and password else Garmin()
    try:
        client.login(str(tokenstore_path))
    except TypeError:
        try:
            client.login()
        except Exception as exc:
            raise GarminProviderError(classify_error(exc, "login")) from exc
    except Exception as exc:
        raise GarminProviderError(classify_error(exc, "login")) from exc

    tokenstore_path.mkdir(parents=True, exist_ok=True)
    garth = getattr(client, "garth", None)
    if garth is not None:
        with contextlib.suppress(Exception):
            garth.dump(str(tokenstore_path))
    return client
