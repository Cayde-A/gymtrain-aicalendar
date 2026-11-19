#!/usr/bin/env python3
"""Upload an approved monthly summary through Supabase Auth and RLS."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

try:
    from . import trainingos_db, trainingos_monthly_sync_package
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_db  # type: ignore
    import trainingos_monthly_sync_package  # type: ignore


Requester = Callable[[str, str, dict[str, str], Any | None], tuple[int, Any]]


def request_json(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: Any | None = None,
) -> tuple[int, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
            return int(response.status), json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = None
        return int(exc.code), parsed


def normalized_project_url(project_url: str) -> str:
    value = project_url.rstrip("/")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("SUPABASE_URL must be an HTTPS origin without embedded credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("SUPABASE_URL must not include a path, query, or fragment")
    return value


def auth_headers(publishable_key: str, access_token: str) -> dict[str, str]:
    return {
        "apikey": publishable_key,
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "TrainingOS-local-sync/1",
    }


def set_batch_status(
    connection: Any,
    batch_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    uploaded_at = "current_timestamp" if status == "uploaded" else "null"
    connection.execute(
        f"""
        update monthly_sync_batches
        set status = ?, uploaded_at = {uploaded_at}, error_message = ?
        where id = ?
        """,
        (status, error_message, batch_id),
    )


def run_upload(
    connection: Any,
    package: dict[str, Any],
    project_url: str | None,
    publishable_key: str | None,
    access_token: str | None,
    confirmed: bool,
    requester: Requester = request_json,
) -> tuple[int, dict[str, Any]]:
    trainingos_monthly_sync_package.validate_package(package)
    digest = trainingos_monthly_sync_package.payload_hash(package)
    batch_id = trainingos_monthly_sync_package.persist_pending_package(connection, package, digest)
    if not confirmed:
        return 3, {
            "status": "needs_confirmation",
            "batch_id": batch_id,
            "payload_sha256": digest,
            "uploaded": False,
        }
    missing = [
        name
        for name, value in (
            ("SUPABASE_URL", project_url),
            ("SUPABASE_PUBLISHABLE_KEY", publishable_key),
            ("SUPABASE_ACCESS_TOKEN", access_token),
        )
        if not value
    ]
    if missing:
        return 3, {
            "status": "needs_supabase_auth",
            "missing": missing,
            "batch_id": batch_id,
            "uploaded": False,
        }
    try:
        base_url = normalized_project_url(str(project_url))
    except ValueError as exc:
        set_batch_status(connection, batch_id, "failed", "invalid_project_url")
        return 4, {"status": "invalid_configuration", "message": str(exc), "uploaded": False}
    headers = auth_headers(str(publishable_key), str(access_token))

    user_status, user = requester("GET", f"{base_url}/auth/v1/user", headers, None)
    if user_status != 200 or not isinstance(user, dict) or not user.get("id"):
        set_batch_status(connection, batch_id, "failed", f"auth_http_{user_status}")
        return 4, {
            "status": "supabase_auth_failed",
            "http_status": user_status,
            "batch_id": batch_id,
            "uploaded": False,
        }
    user_id = str(user["id"])
    query = urllib.parse.urlencode(
        {"on_conflict": "user_id,sync_month", "select": "sync_month,payload_sha256"}
    )
    table_url = f"{base_url}/rest/v1/trainingos_monthly_summaries?{query}"
    upsert_headers = dict(headers)
    upsert_headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    remote_row = {
        "user_id": user_id,
        "sync_month": package["sync_month"],
        "payload_sha256": digest,
        "schema_version": package["schema_version"],
        "summary": package,
    }
    upload_status, _ = requester("POST", table_url, upsert_headers, remote_row)
    if upload_status not in {200, 201}:
        set_batch_status(connection, batch_id, "failed", f"upload_http_{upload_status}")
        return 4, {
            "status": "supabase_upload_failed",
            "http_status": upload_status,
            "batch_id": batch_id,
            "uploaded": False,
        }

    read_query = urllib.parse.urlencode(
        {
            "user_id": f"eq.{user_id}",
            "sync_month": f"eq.{package['sync_month']}",
            "select": "sync_month,payload_sha256",
            "limit": "1",
        }
    )
    read_status, rows = requester(
        "GET",
        f"{base_url}/rest/v1/trainingos_monthly_summaries?{read_query}",
        headers,
        None,
    )
    confirmed_row = rows[0] if read_status == 200 and isinstance(rows, list) and rows else None
    if not isinstance(confirmed_row, dict) or confirmed_row.get("payload_sha256") != digest:
        set_batch_status(connection, batch_id, "failed", "readback_hash_mismatch")
        return 4, {
            "status": "supabase_readback_failed",
            "http_status": read_status,
            "batch_id": batch_id,
            "uploaded": False,
        }
    set_batch_status(connection, batch_id, "uploaded")
    return 0, {
        "status": "uploaded",
        "batch_id": batch_id,
        "sync_month": package["sync_month"],
        "payload_sha256": digest,
        "readback_confirmed": True,
        "uploaded": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload a minimized monthly summary to Supabase.")
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH))
    parser.add_argument("--month", required=True, help="Month in YYYY-MM format.")
    parser.add_argument("--push", action="store_true", help="Enable the external write path.")
    parser.add_argument("--confirm", action="store_true", help="Confirm this specific upload.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    trainingos_db.init_db(db_path)
    with trainingos_db.connect(db_path) as connection:
        package, digest, batch_id = trainingos_monthly_sync_package.create_package(
            connection, args.month
        )
        if not args.push:
            print(
                json.dumps(
                    {
                        "status": "dry_run",
                        "batch_id": batch_id,
                        "payload_sha256": digest,
                        "uploaded": False,
                    },
                    indent=2,
                )
            )
            return 0
        code, result = run_upload(
            connection,
            package,
            os.environ.get("SUPABASE_URL"),
            os.environ.get("SUPABASE_PUBLISHABLE_KEY"),
            os.environ.get("SUPABASE_ACCESS_TOKEN"),
            confirmed=args.confirm,
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
