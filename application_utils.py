from __future__ import annotations

import asyncio
import inspect
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


APP_TIMEZONE = ZoneInfo("America/New_York")


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        raw_value = value.strip()
        if raw_value.endswith("Z"):
            raw_value = f"{raw_value[:-1]}+00:00"

        if "." in raw_value:
            prefix, suffix = raw_value.split(".", 1)
            timezone_suffix = ""
            microseconds = suffix

            for separator in ("+", "-"):
                offset_index = suffix.find(separator)
                if offset_index > 0:
                    microseconds = suffix[:offset_index]
                    timezone_suffix = suffix[offset_index:]
                    break

            microseconds = (microseconds + "000000")[:6]
            raw_value = f"{prefix}.{microseconds}{timezone_suffix}"

        parsed = datetime.fromisoformat(raw_value)
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=APP_TIMEZONE)

    return parsed.astimezone(APP_TIMEZONE)


def normalize_application_record(raw_record: Any) -> dict[str, Any] | None:
    if not raw_record:
        return None

    record = raw_record[0] if isinstance(raw_record, list) else raw_record
    if not record:
        return None

    if isinstance(record, dict):
        normalized = {
            "roblox_username": record.get("roblox_username") or record.get("username"),
            "reason": record.get("reason"),
            "inviter": record.get("inviter"),
            "inviter_id": record.get("inviter_id"),
            "created_at": parse_datetime(
                record.get("created_at")
                or record.get("submission_date")
                or record.get("created")
                or record.get("raw_date")
            ),
        }
        return normalized

    values = list(record.values()) if hasattr(record, "values") else []
    return {
        "roblox_username": values[2] if len(values) > 2 else None,
        "reason": values[3] if len(values) > 3 else None,
        "inviter": values[4] if len(values) > 4 else None,
        "created_at": parse_datetime(values[5] if len(values) > 5 else None),
        "inviter_id": values[6] if len(values) > 6 else None,
    }


async def execute_supabase(query: Any) -> Any:
    execute = query.execute
    if inspect.iscoroutinefunction(execute):
        return await execute()

    result = await asyncio.to_thread(execute)
    if inspect.isawaitable(result):
        return await result
    return result


def fetch_application_record(supabase_client: Any, user_id: int) -> dict[str, Any] | None:
    response = supabase_client.rpc("fetchapplication", params={"uid": user_id}).execute()
    return normalize_application_record(response.data)


async def fetch_application_record_async(
    supabase_client: Any,
    user_id: int,
) -> dict[str, Any] | None:
    response = await execute_supabase(
        supabase_client.rpc("fetchapplication", params={"uid": user_id})
    )
    return normalize_application_record(response.data)


def format_application_date(value: datetime | None) -> str:
    if value is None:
        return "N/A"
    return value.astimezone(APP_TIMEZONE).strftime("%Y-%m-%d %H:%M %Z")
