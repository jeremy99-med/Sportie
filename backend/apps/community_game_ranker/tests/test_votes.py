from datetime import datetime, timezone

import pytest
from django.contrib.auth import get_user_model

from apps.community_game_ranker.models import CommunityVote, GameLog, Sport, Team
from apps.community_game_ranker.services.votes import cast_vote

pytestmark = pytest.mark.django_db

UP, DOWN = CommunityVote.Value.UP, CommunityVote.Value.DOWN


@pytest.fixture
def game():
    nba = Sport.objects.get(code="NBA")
    return GameLog.objects.create(
        sport=nba,
        home_team=Team.objects.get(sport=nba, abbreviation="BOS"),
        away_team=Team.objects.get(sport=nba, abbreviation="LAL"),
        scheduled_at=datetime(2026, 11, 1, 23, 0, tzinfo=timezone.utc),
        season=2026,
    )


@pytest.fixture
def user():
    return get_user_model().objects.create_user(username="fan")


def test_upvote(user, game):
    assert cast_vote(user, game, UP)["my_vote"] == UP
    assert CommunityVote.objects.get(user=user, game=game).value == UP


def test_downvote(user, game):
    result = cast_vote(user, game, DOWN)
    assert result["my_vote"] == DOWN and result["net_votes"] == -1


def test_remove_vote_when_same_vote_sent_twice(user, game):
    cast_vote(user, game, UP)
    result = cast_vote(user, game, UP)
    assert result == {**result, "my_vote": None, "net_votes": 0}
    assert not CommunityVote.objects.exists()


def test_flip_vote_when_opposite_vote_sent(user, game):
    cast_vote(user, game, UP)
    result = cast_vote(user, game, DOWN)
    assert result["my_vote"] == DOWN and result["net_votes"] == -1
    assert CommunityVote.objects.count() == 1


def test_vote_rescores_the_game(user, game):
    neutral = cast_vote(user, game, UP)["importance_score"]
    cast_vote(user, game, UP)  # remove
    game.refresh_from_db()
    assert game.score_breakdown["community"] == 0.5
    assert neutral > game.importance_score


def test_net_votes_count_every_user(game):
    users = [get_user_model().objects.create_user(username=f"fan{i}") for i in range(3)]
    cast_vote(users[0], game, UP)
    cast_vote(users[1], game, UP)
    assert cast_vote(users[2], game, DOWN)["net_votes"] == 1


def test_rejects_invalid_value(user, game):
    with pytest.raises(ValueError):
        cast_vote(user, game, 2)
