import pytest

from apps.community_game_ranker.services import scoring
from apps.community_game_ranker.services.scoring import (
    FACTORS,
    WEIGHTS,
    community_factor,
    importance,
    momentum_factor,
    playoff_factor,
    rivalry_factor,
    star_injury_factor,
    status_factor,
    weather_factor,
)


def standing(rank, played=70, ties=0):
    return {"wins": played // 2, "losses": played - played // 2 - ties, "ties": ties, "conference_rank": rank}


# Weights


def test_every_sport_weights_every_factor():
    for sport, weights in WEIGHTS.items():
        assert set(weights) == set(FACTORS), sport
        assert sum(weights.values()) > 0


def test_weather_weight_is_zero_for_indoor_leagues():
    assert WEIGHTS["NBA"]["weather"] == 0
    assert WEIGHTS["NHL"]["weather"] == 0


# Playoff


def test_playoff_bubble_teams_late_in_season_score_highest():
    bubble = playoff_factor("NBA", standing(8), standing(9))
    leader_vs_cellar = playoff_factor("NBA", standing(1), standing(15))
    # Ranks 8 and 9 -> stakes (1 + 0.8) / 2 = 0.9, scaled by 70/82 of the season played.
    assert bubble == pytest.approx(0.9 * (0.4 + 0.6 * 70 / 82))
    assert leader_vs_cellar < 0.3
    assert bubble > leader_vs_cellar


def test_playoff_stakes_grow_as_the_season_goes_on():
    early = playoff_factor("NFL", standing(7, played=1), standing(7, played=1))
    late = playoff_factor("NFL", standing(7, played=16), standing(7, played=16))
    assert early < late
    assert early == pytest.approx(scoring.EARLY_SEASON_STAKES + 0.6 / 17, abs=0.01)


def test_playoff_missing_standings_is_neutral_and_low():
    assert playoff_factor("NBA", None, None) == pytest.approx(0.5 * scoring.EARLY_SEASON_STAKES)


def test_playoff_stays_in_range():
    for rank in range(1, 20):
        assert 0 <= playoff_factor("NFL", standing(rank, played=17), standing(rank)) <= 1


# Star injury


def test_star_injury_healthy_or_no_stars_is_full():
    assert star_injury_factor(6, []) == 1.0
    assert star_injury_factor(0, ["out"]) == 1.0


def test_star_injury_missing_star_lowers_appeal_by_severity():
    assert star_injury_factor(4, ["out"]) == pytest.approx(0.75)
    assert star_injury_factor(4, ["questionable"]) == pytest.approx(0.875)
    assert star_injury_factor(4, ["out"]) < star_injury_factor(4, ["doubtful"]) < star_injury_factor(
        4, ["questionable"]
    )


def test_star_injury_clamps_and_ignores_unknown_status():
    assert star_injury_factor(1, ["out", "out"]) == 0.0
    assert star_injury_factor(2, ["probable"]) == 1.0


# Weather


SNOW = {"precip_mm": 1, "wind_kph": 10, "condition_text": "Moderate snow"}


@pytest.mark.parametrize("sport", ["NBA", "NHL"])
def test_weather_never_counts_for_indoor_leagues(sport):
    assert weather_factor(sport, False, SNOW) == 0.0


def test_weather_zero_indoors_or_without_data():
    assert weather_factor("NFL", True, SNOW) == 0.0
    assert weather_factor("NFL", False, None) == 0.0


def test_weather_snow_rain_and_wind_raise_it():
    assert weather_factor("NFL", False, SNOW) == 1.0
    assert weather_factor("NFL", False, {"precip_mm": 2.5, "wind_kph": 0}) == pytest.approx(0.5)
    assert weather_factor("MLB", False, {"precip_mm": 0, "wind_kph": 50}) == 1.0
    assert weather_factor("NFL", False, {"precip_mm": 0, "wind_kph": 10, "condition_text": "Sunny"}) == 0.0


# Momentum


def test_momentum_hot_teams_score_higher():
    assert momentum_factor([1, 1, 1, 1, 1], [1, 1, 1, 1, 1]) == 1.0
    assert momentum_factor([0, 0, 0], [0, 0]) == 0.0
    assert momentum_factor([1, 0], [0.5]) == pytest.approx(0.5)


def test_momentum_without_results_is_neutral():
    assert momentum_factor([], []) == 0.5


def test_momentum_only_counts_last_five():
    assert momentum_factor([1, 1, 1, 1, 1, 0, 0, 0], [1] * 5) == 1.0


# Rivalry, status, community


def test_rivalry_scales_intensity():
    assert rivalry_factor(None) == 0.0
    assert rivalry_factor(3) == pytest.approx(0.6)
    assert rivalry_factor(5) == 1.0


def test_status_live_games_matter_most():
    assert status_factor("in_progress") > status_factor("scheduled") > status_factor("final")
    assert status_factor("postponed") == 0.0
    assert status_factor("unknown") == 0.0


def test_community_votes_move_factor_from_neutral():
    assert community_factor(0) == 0.5
    assert community_factor(10) == pytest.approx(0.75)
    assert community_factor(-10) == pytest.approx(0.25)
    assert 0.99 < community_factor(10_000) <= 1.0


# Combiner


def test_importance_bounds_and_breakdown():
    assert importance("NFL", {f: 1.0 for f in FACTORS}) == (100.0, {f: 1.0 for f in FACTORS})
    score, breakdown = importance("NFL", {})
    assert score == 0.0 and set(breakdown) == set(FACTORS)


def test_importance_weather_has_no_effect_on_nba_but_does_on_nfl():
    base = {f: 0.5 for f in FACTORS}
    stormy = {**base, "weather": 1.0}
    assert importance("NBA", stormy)[0] == importance("NBA", base)[0]
    assert importance("NFL", stormy)[0] > importance("NFL", base)[0]


def test_importance_clamps_out_of_range_factors():
    assert importance("NBA", {"playoff": 7.0})[1]["playoff"] == 1.0
