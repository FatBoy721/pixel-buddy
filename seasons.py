"""Which holiday is it, and how close? Pure date logic, no Qt.

Each season builds up: the whole month (light), a countdown week (more),
then the day itself (full)."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Season:
    month: int
    countdown_from: int  # day of month the countdown level starts
    day: int             # the holiday itself


SEASONS = {"halloween": Season(month=10, countdown_from=25, day=31)}
ACTIVITY_CHANCE = {"month": 0.5, "countdown": 0.75, "day": 1.0}
# Outfits rotate daily through the season month (day 1 = first look).
LOOKS = {"halloween": ("witch", "slasher", "hockey", "screamer")}


def current(today, override="auto"):
    """-> (season name, level, days left, look). (None, None, 0, None) when no season applies.
    override: "auto", "off", a season name (forced = level "day", look by date),
    or "season/look" to force one outfit (for testing)."""
    if override == "off":
        return None, None, 0, None
    forced, _, look = override.partition("/")
    if forced in SEASONS:
        looks = LOOKS[forced]
        return forced, "day", 0, look if look in looks else looks[(today.day - 1) % len(looks)]
    for name, s in SEASONS.items():
        left = s.day - today.day
        if today.month == s.month and left >= 0:
            level = "day" if left == 0 else "countdown" if today.day >= s.countdown_from else "month"
            looks = LOOKS[name]
            return name, level, left, looks[(today.day - 1) % len(looks)]
    return None, None, 0, None


if __name__ == "__main__":
    assert current(date(2026, 10, 1)) == ("halloween", "month", 30, "witch")
    assert current(date(2026, 10, 2)) == ("halloween", "month", 29, "slasher")
    assert current(date(2026, 10, 3))[3] == "hockey"
    assert current(date(2026, 10, 4))[3] == "screamer"
    assert current(date(2026, 10, 5))[3] == "witch"
    assert current(date(2026, 10, 24)) == ("halloween", "month", 7, "screamer")
    assert current(date(2026, 10, 25)) == ("halloween", "countdown", 6, "witch")
    assert current(date(2026, 10, 30)) == ("halloween", "countdown", 1, "slasher")
    assert current(date(2026, 10, 31)) == ("halloween", "day", 0, "hockey")
    assert current(date(2026, 11, 1)) == (None, None, 0, None)
    assert current(date(2026, 9, 30)) == (None, None, 0, None)
    assert current(date(2026, 10, 31), "off") == (None, None, 0, None)
    assert current(date(2026, 7, 4), "halloween") == ("halloween", "day", 0, "screamer")
    assert current(date(2026, 7, 4), "halloween/slasher") == ("halloween", "day", 0, "slasher")
    assert current(date(2026, 7, 4), "halloween/bogus") == ("halloween", "day", 0, "screamer")
    assert current(date(2026, 7, 4), "nonsense") == (None, None, 0, None)
    print("seasons ok")
