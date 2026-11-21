import asyncio
import os
from time import monotonic
from xml.etree import ElementTree

import aiohttp

from deadlock.ids import account_id, steam_id64

DEADLOCK_API = "https://api.deadlock-api.com/v1"
API_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError, ValueError)


def api_error_message(error: Exception) -> str:
    if isinstance(error, aiohttp.ClientResponseError) and error.status == 429:
        return "The Deadlock API is rate-limiting requests. Try again shortly."
    return "The Deadlock API is temporarily unavailable. Try again shortly."


def fallback_profile(steam_id: int) -> dict:
    return {
        "account_id": account_id(steam_id),
        "personaname": "Steam player",
        "profileurl": f"https://steamcommunity.com/profiles/{steam_id}",
        "avatarfull": None,
    }


async def resolve_vanity(vanity: str) -> int:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        async with session.get(
            f"https://steamcommunity.com/id/{vanity}/",
            params={"xml": "1"},
            allow_redirects=False,
        ) as response:
            response.raise_for_status()
            try:
                profile = ElementTree.fromstring(await response.text())
                resolved = int(profile.findtext("steamID64") or "")
            except (ElementTree.ParseError, ValueError) as error:
                raise ValueError("Steam couldn't resolve that profile. Try your numeric Friend Code.") from error
    return steam_id64(resolved)


def _api_session() -> aiohttp.ClientSession:
    headers = {"Accept": "application/json", "User-Agent": "CAA-Bot/1.0"}
    api_key = os.getenv("DEADLOCK_API_KEY")
    if api_key:
        headers["X-API-KEY"] = api_key
    return aiohttp.ClientSession(
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=12),
        raise_for_status=True,
    )


async def _get_json(session, path: str, *, params=None, expected=list):
    async with session.get(f"{DEADLOCK_API}/{path}", params=params, allow_redirects=False) as response:
        payload = await response.json()
    if not isinstance(payload, expected):
        raise ValueError("Unexpected Deadlock API response")
    return payload


async def _get_optional_json(session, path: str, *, params=None, expected=list):
    try:
        return await _get_json(session, path, params=params, expected=expected)
    except API_ERRORS:
        return None


async def _get_recent_mvps(session, player_account_id: int, recent: list[dict]) -> set[int]:
    if not recent:
        return set()
    matches = await _get_optional_json(
        session,
        "matches/metadata",
        params={
            "match_ids": ",".join(str(match["match_id"]) for match in recent),
            "include_player_info": "true",
            "include_player_items": "false",
            "player_kda_only": "true",
        },
    )
    return {
        match["match_id"]
        for match in matches or []
        if any(
            player.get("account_id") == player_account_id and player.get("mvp_rank") == 1
            for player in match.get("players") or []
        )
    }


class DeadlockClient:
    def __init__(self):
        self._heroes: dict[int, str] = {}
        self._ranks: dict[int, dict] = {}
        self._assets_expire_at = 0.0
        self._assets_lock = asyncio.Lock()

    async def _get_assets(self, session) -> tuple[dict[int, str], dict[int, dict]]:
        async with self._assets_lock:
            if monotonic() >= self._assets_expire_at:
                heroes, ranks = await asyncio.gather(
                    _get_optional_json(session, "assets/heroes"),
                    _get_optional_json(session, "assets/ranks"),
                )
                if heroes:
                    self._heroes = {hero["id"]: hero["name"] for hero in heroes}
                if ranks:
                    self._ranks = {rank["tier"]: rank for rank in ranks}
                self._assets_expire_at = monotonic() + (3600 if heroes and ranks else 60)
            return self._heroes, self._ranks

    async def lookup_steam_profile(self, steam_id: int, *, refresh_missing: bool = False) -> dict | None:
        async with _api_session() as session:
            params = {"account_ids": steam_id}
            profiles = await _get_json(session, "players/steam", params=params)
            if not profiles and refresh_missing:
                params["refresh"] = "true"
                profiles = await _get_json(session, "players/steam", params=params)
        target_id = account_id(steam_id)
        return next((profile for profile in profiles if profile["account_id"] == target_id), None)

    async def get_player_data(self, profile: dict) -> tuple[list[dict], dict[int, str], dict[int, dict], dict | None, set[int]]:
        player_account_id = profile["account_id"]
        async with _api_session() as session:
            history = await _get_json(session, f"players/{player_account_id}/match-history")
            matches = sorted(history, key=lambda match: match["start_time"], reverse=True)
            rank, (heroes, ranks), mvp_matches = await asyncio.gather(
                _get_optional_json(session, f"players/{player_account_id}/rank", expected=dict),
                self._get_assets(session),
                _get_recent_mvps(session, player_account_id, matches[:5]),
            )
        return matches, heroes, ranks, rank, mvp_matches

    async def get_match_data(self, match_id: int) -> tuple[dict, dict[int, str]]:
        path = f"matches/{match_id}/metadata"
        async with _api_session() as session:
            try:
                payload = await _get_json(session, path, expected=dict)
            except aiohttp.ClientResponseError as error:
                if error.status != 404:
                    raise
                payload = await _get_json(session, path, params={"is_custom": "true"}, expected=dict)
            match = payload.get("match_info")
            if not isinstance(match, dict) or not isinstance(match.get("players"), list):
                raise ValueError("Unexpected Deadlock match response")
            heroes, _ = await self._get_assets(session)
        return match, heroes
