from __future__ import annotations

import discord


FOOTER_MARKER_SEPARATOR = " :: "

REGISTER_REQUEST_MARKER = "register-request"
PROMOTION_REQUEST_MARKER = "promotion-request"
PROMOTION_ALERT_MARKER = "promotion-alert"


def safe_embed_value(value: object, fallback: str = "N/A") -> str:
    if value is None:
        return fallback

    text = str(value).strip()
    return text or fallback


def build_footer_text(prefix: str, **parts: object) -> str:
    marker = ";".join([prefix, *[f"{key}={value}" for key, value in parts.items()]])
    return f"Custom Adversaries Association{FOOTER_MARKER_SEPARATOR}{marker}"


def parse_footer_marker(text: str | None) -> tuple[str | None, dict[str, str]]:
    if not text:
        return None, {}

    marker_text = text.split(FOOTER_MARKER_SEPARATOR, 1)[-1]
    pieces = marker_text.split(";")
    if not pieces:
        return None, {}

    marker_type = pieces[0] if "=" not in pieces[0] else None
    marker_values: dict[str, str] = {}
    for piece in pieces[1:]:
        if "=" not in piece:
            continue
        key, value = piece.split("=", 1)
        marker_values[key] = value

    return marker_type, marker_values


def get_embed_field(embed: discord.Embed, field_name: str) -> str | None:
    for field in embed.fields:
        if field.name == field_name:
            return field.value
    return None


def replace_embed_field(
    embed: discord.Embed,
    field_name: str,
    value: str,
    *,
    inline: bool = False,
) -> discord.Embed:
    for index, field in enumerate(embed.fields):
        if field.name == field_name:
            embed.set_field_at(index, name=field_name, value=value, inline=inline)
            return embed

    embed.add_field(name=field_name, value=value, inline=inline)
    return embed
