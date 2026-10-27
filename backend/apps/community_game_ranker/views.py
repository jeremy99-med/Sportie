from datetime import date, datetime

from django.db.models import IntegerField, OuterRef, Prefetch, Subquery, Value
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from .models import CommunityVote, GameLog, Injury, Rivalry, Sport
from .serializers import GameSerializer, VoteSerializer
from .services import ranking, votes


def _today_eastern():
    return datetime.now(ranking.SCHEDULE_TZ).date()


class GameViewSet(viewsets.ReadOnlyModelViewSet):
    """Ranked games. List: `?date=YYYY-MM-DD` (US Eastern, default today) and optional `?sport=NBA`.

    POST `<id>/vote/` with {"value": 1 | -1}: same value again removes the vote, the opposite
    value flips it.
    """

    serializer_class = GameSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    throttle_scope = None  # reads aren't throttled; the vote action sets its own scope

    def get_queryset(self):
        qs = GameLog.objects.all()
        if self.action == "list":
            qs = ranking.games_on(self._requested_date(), self._requested_sport())
        user = self.request.user
        my_vote = (
            Subquery(
                CommunityVote.objects.filter(game=OuterRef("pk"), user=user).values("value")[:1]
            )
            if user.is_authenticated
            else Value(None, output_field=IntegerField())
        )
        star_injuries = Injury.objects.filter(player__is_star=True).select_related("player__team")
        return (
            ranking.ranked_games(qs)
            .annotate(my_vote=my_vote)
            .select_related("sport", "home_team", "away_team", "stadium", "weather")
            .prefetch_related(Prefetch("injuries", queryset=star_injuries, to_attr="star_injuries"))
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["rivalries"] = {(r.team_a_id, r.team_b_id): r for r in Rivalry.objects.all()}
        return context

    def _requested_date(self):
        raw = self.request.query_params.get("date")
        if not raw:
            return _today_eastern()
        try:
            return date.fromisoformat(raw)
        except ValueError:
            raise ValidationError({"date": "Use YYYY-MM-DD."}) from None

    def _requested_sport(self):
        sport = self.request.query_params.get("sport")
        if sport and sport not in Sport.Code.values:
            raise ValidationError({"sport": f"Use one of {', '.join(Sport.Code.values)}."})
        return sport

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated], throttle_scope="votes")
    def vote(self, request, pk=None):
        serializer = VoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        game = self.get_object()
        return Response(votes.cast_vote(request.user, game, serializer.validated_data["value"]))
