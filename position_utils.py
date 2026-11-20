"""Shared Discord position selection and nonblocking registration hook."""
import logging

EXCLUDED_POSITION_ROLES = frozenset({"Content Creator", "Event Winner", "Server Booster"})


def position_role(member):
    """Select Discord's highest eligible role without mutating member.roles."""
    return next(
        (role for role in reversed(member.roles) if role.name not in EXCLUDED_POSITION_ROLES),
        member.guild.default_role,
    )


def schedule_position_sync(bot, user_id):
    try:
        cog = bot.get_cog("Positions")
        if cog is not None:
            cog.queue_member(user_id)
    except Exception:
        # Registration has already succeeded; background upkeep must not fail its UI.
        logging.getLogger(__name__).exception("Could not schedule position for %s", user_id)
