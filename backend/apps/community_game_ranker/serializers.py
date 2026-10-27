from rest_framework import serializers

from .models import CommunityVote, GameLog, Injury, Stadium, Team, WeatherCondition


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ["id", "abbreviation", "name", "city"]


class StadiumSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stadium
        fields = ["name", "is_indoor"]


class WeatherSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeatherCondition
        fields = ["temp_c", "precip_mm", "wind_kph", "condition_text", "fetched_at"]


class StarInjurySerializer(serializers.ModelSerializer):
    player = serializers.CharField(source="player.name")
    team = serializers.CharField(source="player.team.abbreviation", default=None)

    class Meta:
        model = Injury
        fields = ["player", "team", "status", "status_estimated", "description"]


class GameSerializer(serializers.ModelSerializer):
    """One ranked game. Expects the queryset from `GameViewSet.get_queryset` (annotations,
    prefetched star injuries) and `rivalries` ({(team_a_id, team_b_id): Rivalry}) in the context."""

    sport = serializers.CharField(source="sport.code")
    home_team = TeamSerializer()
    away_team = TeamSerializer()
    stadium = StadiumSerializer(allow_null=True)
    weather = serializers.SerializerMethodField()
    star_injuries = StarInjurySerializer(many=True, read_only=True)
    rivalry = serializers.SerializerMethodField()
    net_votes = serializers.IntegerField(read_only=True)
    my_vote = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = GameLog
        fields = [
            "id",
            "sport",
            "season",
            "week",
            "scheduled_at",
            "status",
            "home_team",
            "away_team",
            "home_score",
            "away_score",
            "stadium",
            "importance_score",
            "score_breakdown",
            "weather",
            "star_injuries",
            "rivalry",
            "net_votes",
            "my_vote",
        ]
        read_only_fields = fields

    def get_weather(self, game):
        weather = getattr(game, "weather", None)  # reverse one-to-one: missing raises otherwise
        return WeatherSerializer(weather).data if weather else None

    def get_rivalry(self, game):
        pair = tuple(sorted((game.home_team_id, game.away_team_id)))
        rivalry = self.context.get("rivalries", {}).get(pair)
        if rivalry is None:
            return None
        return {"name": rivalry.name, "intensity": rivalry.intensity}


class VoteSerializer(serializers.Serializer):
    value = serializers.ChoiceField(choices=CommunityVote.Value.choices)
