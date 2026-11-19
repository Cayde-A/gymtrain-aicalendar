#!/usr/bin/env python3
"""Value-free Garmin provider health recheck and fallback recommendation."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Callable

try:
    from . import garmin_provider
    from .gccli_adapter import GccliAdapter
except ImportError:  # pragma: no cover - supports direct script execution.
    import garmin_provider  # type: ignore
    from gccli_adapter import GccliAdapter  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "exports" / "garmin" / "normalized" / "provider_recheck_report.json"


def safe_probe(name: str, callback: Callable[[], Any]) -> dict[str, Any]:
    try:
        payload = callback()
        return {
            "name": name,
            "ok": True,
            "result_type": type(payload).__name__,
            "top_level_fields": len(payload) if isinstance(payload, dict) else None,
            "records": len(payload) if isinstance(payload, list) else None,
        }
    except garmin_provider.GarminProviderError as exc:
        return {"name": name, "ok": False, "error": exc.to_dict()}
    except Exception as exc:  # noqa: BLE001 - diagnostics must classify transport failures.
        return {
            "name": name,
            "ok": False,
            "error": garmin_provider.classify_error(exc, name).to_dict(),
        }


def python_status(date_text: str, live: bool) -> dict[str, Any]:
    tokenstore = garmin_provider.default_tokenstore()
    status: dict[str, Any] = {
        "source_tool": garmin_provider.SOURCE_TOOL,
        "version": garmin_provider.package_version(),
        "token_cache_present": garmin_provider.has_tokens(tokenstore),
        "probes": [],
    }
    if not live:
        status["status"] = "configured" if status["token_cache_present"] else "authentication_required"
        return status
    if not status["token_cache_present"]:
        status["status"] = "authentication_required"
        return status
    try:
        client = garmin_provider.login(None, None, tokenstore)
    except garmin_provider.GarminProviderError as exc:
        status["status"] = "failed"
        status["error"] = exc.to_dict()
        return status
    status["capabilities"] = garmin_provider.detect_capabilities(client)
    status["probes"] = [
        safe_probe("python_daily_summary", lambda: client.get_stats(date_text)),
        safe_probe(
            "python_recent_activities",
            lambda: client.get_activities_by_date(date_text, date_text),
        ),
    ]
    status["status"] = "healthy" if all(item["ok"] for item in status["probes"]) else "failed"
    return status


def personal_status(date_text: str, live: bool) -> dict[str, Any]:
    configured = garmin_provider.has_personal_api_key()
    status: dict[str, Any] = {
        "source_tool": garmin_provider.PERSONAL_SOURCE_TOOL,
        "version": garmin_provider.package_version(garmin_provider.PERSONAL_SOURCE_TOOL),
        "api_key_configured": configured,
        "probes": [],
    }
    if not configured:
        status["status"] = "authentication_required"
        return status
    if not live:
        status["status"] = "configured"
        return status
    try:
        client = garmin_provider.login_personal_read()
    except garmin_provider.GarminProviderError as exc:
        status["status"] = "failed"
        status["error"] = exc.to_dict()
        return status
    status["capabilities"] = garmin_provider.detect_capabilities(client)
    status["probes"] = [
        safe_probe("personal_daily_summary", lambda: client.get_stats(date_text)),
        safe_probe(
            "personal_recent_activities",
            lambda: client.get_activities_by_date(date_text, date_text),
        ),
    ]
    status["status"] = "healthy" if all(item["ok"] for item in status["probes"]) else "failed"
    return status


def gccli_status(date_text: str, live: bool, adapter: GccliAdapter | None = None) -> dict[str, Any]:
    adapter = adapter or GccliAdapter()
    status: dict[str, Any] = {"source_tool": "gccli", "probes": []}
    try:
        status.update(adapter.metadata())
        auth_probe = safe_probe("gccli_auth", adapter.auth_status)
        status["authenticated"] = auth_probe["ok"]
        if not auth_probe["ok"]:
            status["status"] = "authentication_required"
            status["error"] = auth_probe["error"]
            return status
    except garmin_provider.GarminProviderError as exc:
        status["status"] = "failed"
        status["error"] = exc.to_dict()
        return status
    if not live:
        status["status"] = "configured"
        return status
    status["probes"] = [
        safe_probe("gccli_daily_summary", lambda: adapter.run_json("daily_summary", ["health", "summary", date_text])),
        safe_probe("gccli_recent_activities", lambda: adapter.activities(limit=1)),
    ]
    status["status"] = "healthy" if all(item["ok"] for item in status["probes"]) else "failed"
    return status


def error_codes(status: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    if isinstance(status.get("error"), dict) and status["error"].get("code"):
        codes.add(str(status["error"]["code"]))
    for probe in status.get("probes", []):
        error = probe.get("error") if isinstance(probe, dict) else None
        if isinstance(error, dict) and error.get("code"):
            codes.add(str(error["code"]))
    return codes


def recommendation(
    primary: dict[str, Any],
    secondary: dict[str, Any],
    *,
    fallback_action: str = "use_gccli_read_fallback",
) -> dict[str, str]:
    primary_codes = error_codes(primary)
    secondary_codes = error_codes(secondary)
    all_codes = primary_codes | secondary_codes
    if garmin_provider.ErrorCode.RATE_LIMIT in all_codes:
        return {
            "action": "wait_without_reauthentication",
            "reason": "rate_limit",
        }
    usable_states = {"healthy", "configured"}
    if primary.get("status") in usable_states and secondary.get("status") in usable_states:
        return {"action": "continue_primary", "reason": "both_read_paths_healthy"}
    if primary.get("status") not in usable_states and secondary.get("status") in usable_states:
        return {"action": fallback_action, "reason": "primary_read_failed"}
    if garmin_provider.ErrorCode.AUTHENTICATION in all_codes or "authentication_required" in {
        primary.get("status"), secondary.get("status")
    }:
        return {"action": "user_login_required", "reason": "authentication"}
    if garmin_provider.ErrorCode.SCHEMA in all_codes:
        return {"action": "inspect_same_source_release_and_schema", "reason": "schema_change"}
    if primary.get("status") == "failed" and secondary.get("status") == "failed":
        return {"action": "check_garmin_outage_and_export_fallback", "reason": "both_live_reads_failed"}
    return {"action": "complete_live_recheck", "reason": "no_live_probe_result"}


def build_report(date_text: str, live: bool) -> dict[str, Any]:
    official = personal_status(date_text, live)
    legacy = python_status(date_text, live)
    gccli = gccli_status(date_text, live)
    fallback = legacy if legacy.get("status") in {"healthy", "configured"} else gccli
    fallback_action = (
        "use_legacy_read_fallback" if fallback is legacy else "use_gccli_read_fallback"
    )
    return {
        "status": "completed",
        "date": date_text,
        "live_probes": live,
        "contains_personal_values": False,
        "primary": official,
        "official": official,
        "legacy": legacy,
        "secondary": gccli,
        "recommendation": recommendation(
            official,
            fallback,
            fallback_action=fallback_action,
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recheck Garmin read providers without exposing values.")
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument("--live", action="store_true", help="Run one summary and one activity-list read per provider.")
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.date, args.live)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Report: {output}")
    action = report["recommendation"]["action"]
    return 0 if action in {
        "continue_primary",
        "use_legacy_read_fallback",
        "use_gccli_read_fallback",
        "complete_live_recheck",
    } else 2


if __name__ == "__main__":
    sys.exit(main())
