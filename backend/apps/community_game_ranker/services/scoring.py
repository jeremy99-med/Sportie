"""Game importance score. Pure functions only: plain values in, floats in [0, 1] out, no DB access.

The DB side (gathering inputs, saving `importance_score`) lives in `services/ranking.py`.
See `.claude/docs/importance-scoring.md`.
"""

FACTORS = ("playoff", "star_injury", "weather", "momentum", "rivalry", "status", "community")

# Starting weights (approved 2026-10-27; tune later). Weather is always 0 for the indoor leagues.
WEIGHTS: dict[str, dict[str, float]] = {
    "NFL": {"playoff": .30, "star_injury": .15, "weather": .10, "momentum": .15, "rivalry": .15, "status": .05, "community": .10},
    "NBA": {"playoff": .30, "star_injury": .25, "weather": 0, "momentum": .15, "rivalry": .10, "status": .05, "community": .10},
    "NHL": {"playoff": .30, "star_injury": .15, "weather": 0, "momentum": .20, "rivalry": .15, "status": .05, "community": .10},
    "MLB": {"playoff": .25, "star_injury": .15, "weather": .15, "momentum": .15, "rivalry": .15, "status": .05, "community": .10},
}

INDOOR_SPORTS = {"NBA", "NHL"}

# Regular-season length, and the conference rank of the last playoff (or play-in) spot.
SEASON_GAMES = {"NFL": 17, "NBA": 82, "NHL": 82, "MLB": 162}
PLAYOFF_CUTOFF = {"NFL": 7, "NBA": 8, "NHL": 8, "MLB": 6}  # NBA: middle of the 6-10 play-in bubble
# How many ranks from the cutoff a team can be and still count as in the race.
RACE_WIDTH = {"NFL": 4, "NBA": 5, "NHL": 4, "MLB": 4}
# Share of the playoff factor that applies on opening day; the rest grows as the season goes on.
EARLY_SEASON_STAKES = 0.4

# Severity of an injured star, by Injury.Status.
INJURY_SEVERITY = {"out": 1.0, "doubtful": 0.75, "questionable": 0.5}

HEAVY_PRECIP_MM = 5.0  # mm in the kickoff hour that counts as a downpour
CALM_WIND_KPH = 15.0
STORM_WIND_KPH = 50.0
SNOW_WORDS = ("snow", "sleet", "blizzard", "ice pellets")

MOMENTUM_GAMES = 5
STATUS_VALUES = {"in_progress": 1.0, "scheduled": 0.8, "delayed": 0.6, "final": 0.3, "postponed": 0.0}
VOTE_SATURATION = 10  # net votes at which the community factor is halfway to its max


def clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _team_stakes(sport, standing):
    """How much one team's playoff spot is in play: 1 at the cutoff, 0 far from it."""
    rank = (standing or {}).get("conference_rank")
    if rank is None:
        return 0.5
    return clamp(1 - abs(rank - PLAYOFF_CUTOFF[sport]) / RACE_WIDTH[sport])


def _season_progress(sport, standing):
    if not standing:
        return 0.0
    played = standing.get("wins", 0) + standing.get("losses", 0) + standing.get("ties", 0)
    return clamp(played / SEASON_GAMES[sport])


def playoff_factor(sport: str, home_standing: dict | None, away_standing: dict | None) -> float:
    """Higher when both teams sit near the playoff cutoff, and more so late in the season.

    Standings are dicts with `wins`, `losses`, `ties`, `conference_rank` (None when unknown).
    """
    stakes = (_team_stakes(sport, home_standing) + _team_stakes(sport, away_standing)) / 2
    progress = max(_season_progress(sport, home_standing), _season_progress(sport, away_standing))
    return clamp(stakes * (EARLY_SEASON_STAKES + (1 - EARLY_SEASON_STAKES) * progress))


def star_injury_factor(stars_total: int, injured_star_statuses: list[str]) -> float:
    """Share of the game's star power that is healthy. A missing star makes a game less appealing.

    `injured_star_statuses` holds the Injury.Status of each injured star (out/doubtful/questionable).
    """
    if stars_total <= 0:
        return 1.0
    lost = sum(INJURY_SEVERITY.get(status, 0.0) for status in injured_star_statuses)
    return clamp(1 - lost / stars_total)


def weather_factor(sport: str, is_indoor: bool, weather: dict | None) -> float:
    """Heavy rain, strong wind, or snow at an outdoor game adds drama. 0 indoors or without data.

    `weather` has `precip_mm`, `wind_kph`, `condition_text`.
    """
    if sport in INDOOR_SPORTS or is_indoor or not weather:
        return 0.0
    condition = (weather.get("condition_text") or "").lower()
    if any(word in condition for word in SNOW_WORDS):
        return 1.0
    rain = (weather.get("precip_mm") or 0) / HEAVY_PRECIP_MM
    wind = ((weather.get("wind_kph") or 0) - CALM_WIND_KPH) / (STORM_WIND_KPH - CALM_WIND_KPH)
    return clamp(max(rain, wind))


def momentum_factor(home_results: list[float], away_results: list[float]) -> float:
    """Average recent win rate of both teams (hot teams make better games).

    Results are most recent first: 1 = win, 0 = loss, 0.5 = tie. Only the last 5 count.
    A team with no results counts as 0.5.
    """

    def rate(results):
        recent = results[:MOMENTUM_GAMES]
        return sum(recent) / len(recent) if recent else 0.5

    return clamp((rate(home_results) + rate(away_results)) / 2)


def rivalry_factor(intensity: int | None) -> float:
    """Rivalry.intensity (1-5) scaled to [0, 1]; 0 without a rivalry."""
    return clamp((intensity or 0) / 5)


def status_factor(status: str) -> float:
    """Live games matter most; finished and postponed ones least."""
    return STATUS_VALUES.get(status, 0.0)


def community_factor(net_votes: int) -> float:
    """0.5 with no votes, approaching 1 (or 0) as net up (or down) votes grow."""
    return clamp(0.5 + 0.5 * net_votes / (abs(net_votes) + VOTE_SATURATION))


def importance(sport: str, factors: dict[str, float]) -> tuple[float, dict[str, float]]:
    """Weighted 0-100 score plus the per-factor breakdown stored in GameLog.score_breakdown.

    Missing factors count as 0.
    """
    weights = WEIGHTS[sport]
    breakdown = {name: round(clamp(factors.get(name, 0.0)), 3) for name in FACTORS}
    total = sum(weights.values())
    score = 100 * sum(weights[name] * breakdown[name] for name in FACTORS) / total
    return round(score, 2), breakdown
