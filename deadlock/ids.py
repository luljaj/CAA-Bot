import re
from urllib.parse import urlsplit

STEAM_ID64_BASE = 76561197960265728
MAX_ACCOUNT_ID = 2**32 - 1


def steam_id64(number: int) -> int:
    if 0 < number <= MAX_ACCOUNT_ID:
        return STEAM_ID64_BASE + number
    if STEAM_ID64_BASE < number <= STEAM_ID64_BASE + MAX_ACCOUNT_ID:
        return number
    raise ValueError("Enter a valid Steam Friend Code or Steam profile link.")


def account_id(number: int) -> int:
    return steam_id64(number) - STEAM_ID64_BASE


def parse_steam_reference(reference: str) -> int | str:
    """Return a SteamID64 or the vanity slug from a Steam Community profile."""
    reference = reference.strip().removeprefix("<").removesuffix(">")
    if re.fullmatch(r"[0-9]{1,17}", reference):
        return steam_id64(int(reference))

    url = urlsplit(reference if "://" in reference else f"https://{reference}")
    if url.scheme not in ("https", "http") or url.netloc.lower() != "steamcommunity.com":
        raise ValueError("Enter a Steam Friend Code or a steamcommunity.com profile link.")

    numeric = re.fullmatch(r"/profiles/([0-9]{17})/?", url.path)
    if numeric:
        return steam_id64(int(numeric[1]))

    vanity = re.fullmatch(r"/id/([A-Za-z0-9_-]{1,64})/?", url.path)
    if vanity:
        return vanity[1]
    raise ValueError("Enter a Steam profile link from the player's Steam Community page.")
