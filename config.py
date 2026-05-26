import os
from datetime import datetime
from zoneinfo import ZoneInfo

import discord


SERVER_ICON = "https://images-ext-1.discordapp.net/external/8zvqGh0uPdc05QkNHhjjb2Fk5mWJo9347j8ifJcT8k8/%3Fsize%3D256/https/cdn.discordapp.com/icons/938810131800543333/9cec5b222e8564fb73c3ca1f9c9944fd.png?format=webp&quality=lossless&width=512&height=512"

ENTRY_REVIEW_CHANNEL_ID = int(os.getenv("ENTRY_REVIEW_CHANNEL_ID", "1382493785400934410"))
PROMOTION_REVIEW_CHANNEL_ID = int(
    os.getenv("PROMOTION_REVIEW_CHANNEL_ID", str(ENTRY_REVIEW_CHANNEL_ID))
)

INTERN_ROLE_ID = int(os.getenv("INTERN_ROLE_ID")) if os.getenv("INTERN_ROLE_ID") else None
INTERN_ROLE_NAME = os.getenv("INTERN_ROLE_NAME", "Intern")

EMPLOYEE_ROLE_ID = (
    int(os.getenv("EMPLOYEE_ROLE_ID")) if os.getenv("EMPLOYEE_ROLE_ID") else None
)
EMPLOYEE_ROLE_NAME = os.getenv("EMPLOYEE_ROLE_NAME", "Employee")

PROMOTION_ROLLOUT_CUTOFF = os.getenv(
    "PROMOTION_ROLLOUT_CUTOFF",
    "2026-05-26T00:00:00-04:00",
)


def get_role(
    guild: discord.Guild,
    *,
    role_id: int | None = None,
    role_name: str | None = None,
) -> discord.Role | None:
    if role_id:
        role = guild.get_role(role_id)
        if role is not None:
            return role
    if role_name:
        return discord.utils.get(guild.roles, name=role_name)
    return None


def get_intern_role(guild: discord.Guild) -> discord.Role | None:
    return get_role(guild, role_id=INTERN_ROLE_ID, role_name=INTERN_ROLE_NAME)


def get_employee_role(guild: discord.Guild) -> discord.Role | None:
    return get_role(guild, role_id=EMPLOYEE_ROLE_ID, role_name=EMPLOYEE_ROLE_NAME)


def get_promotion_rollout_cutoff() -> datetime:
    raw_value = PROMOTION_ROLLOUT_CUTOFF.strip()
    if raw_value.endswith("Z"):
        raw_value = f"{raw_value[:-1]}+00:00"

    cutoff = datetime.fromisoformat(raw_value)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=ZoneInfo("America/New_York"))

    return cutoff.astimezone(ZoneInfo("America/New_York"))
