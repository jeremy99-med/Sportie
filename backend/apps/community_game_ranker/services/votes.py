from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce

from apps.community_game_ranker.models import CommunityVote
from apps.community_game_ranker.services import ranking


@transaction.atomic
def cast_vote(user, game, value):
    """Apply one vote and re-score the game.

    No vote yet -> create it. Same value again -> remove it. Opposite value -> flip it.
    Returns {"my_vote": 1 | -1 | None, "net_votes": int, "importance_score": float | None}.
    """
    if value not in CommunityVote.Value.values:
        raise ValueError(f"vote value must be one of {CommunityVote.Value.values}")

    existing = CommunityVote.objects.select_for_update().filter(user=user, game=game).first()
    if existing is None:
        try:
            with transaction.atomic():  # savepoint: a concurrent first vote may win the race
                CommunityVote.objects.create(user=user, game=game, value=value)
            my_vote = value
        except IntegrityError:
            existing = CommunityVote.objects.select_for_update().get(user=user, game=game)
    if existing is not None:
        if existing.value == value:
            existing.delete()
            my_vote = None
        else:
            existing.value = value
            existing.save(update_fields=["value"])
            my_vote = value

    score = ranking.score_game(game)
    net = game.votes.aggregate(net=Coalesce(Sum("value"), 0))["net"]
    return {"my_vote": my_vote, "net_votes": net, "importance_score": score}
