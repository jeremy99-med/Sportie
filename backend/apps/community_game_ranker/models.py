import hashlib
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Sport(models.Model):
    class Code(models.TextChoices):
        NFL = "NFL", "NFL"
        NBA = "NBA", "NBA"
        NHL = "NHL", "NHL"
        MLB = "MLB", "MLB"

    code = models.CharField(max_length=3, choices=Code.choices, unique=True)
    name = models.CharField(max_length=100)
    is_outdoor_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class Team(models.Model):
    sport = models.ForeignKey(Sport, on_delete=models.PROTECT, related_name="teams")
    name = models.CharField(max_length=100)
    abbreviation = models.CharField(max_length=10)
    city = models.CharField(max_length=100, blank=True)
    # Provider-specific IDs, e.g. {"balldontlie": 14, "sportsdata": "LAL"}.
    external_ids = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["sport", "abbreviation"]
        constraints = [
            models.UniqueConstraint(
                fields=["sport", "abbreviation"], name="unique_team_abbreviation_per_sport"
            ),
        ]

    def __str__(self):
        return f"{self.abbreviation} ({self.sport.code})"


class Stadium(models.Model):
    # Nullable so neutral-site venues (e.g. international series games) can exist.
    home_team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, null=True, blank=True, related_name="stadiums"
    )
    name = models.CharField(max_length=150)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    is_indoor = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(latitude__gte=-90, latitude__lte=90), name="stadium_latitude_range"
            ),
            models.CheckConstraint(
                condition=Q(longitude__gte=-180, longitude__lte=180),
                name="stadium_longitude_range",
            ),
        ]

    def __str__(self):
        return self.name


class Player(models.Model):
    # Nullable for free agents.
    team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, null=True, blank=True, related_name="players"
    )
    name = models.CharField(max_length=150)
    position = models.CharField(max_length=20, blank=True)
    is_star = models.BooleanField(default=False)
    external_ids = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        team = self.team.abbreviation if self.team_id else "FA"
        return f"{self.name} ({team})"


class GameLog(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        IN_PROGRESS = "in_progress", "In progress"
        FINAL = "final", "Final"
        DELAYED = "delayed", "Delayed"
        POSTPONED = "postponed", "Postponed"

    sport = models.ForeignKey(Sport, on_delete=models.PROTECT, related_name="games")
    home_team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="home_games")
    away_team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="away_games")
    stadium = models.ForeignKey(
        Stadium, on_delete=models.SET_NULL, null=True, blank=True, related_name="games"
    )
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    # Null until the game starts.
    home_score = models.PositiveSmallIntegerField(null=True, blank=True)
    away_score = models.PositiveSmallIntegerField(null=True, blank=True)
    # Null until the scoring service has run.
    importance_score = models.FloatField(null=True, blank=True)
    score_breakdown = models.JSONField(default=dict, blank=True)
    # Year the season started, e.g. 2026 for the 2026-27 NBA season.
    season = models.PositiveSmallIntegerField()
    # Only NFL has weeks.
    week = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["scheduled_at"]
        indexes = [
            models.Index(fields=["sport", "scheduled_at"], name="gamelog_sport_sched_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(home_team=F("away_team")), name="gamelog_home_away_differ"
            ),
        ]

    def __str__(self):
        return (
            f"{self.away_team.abbreviation} @ {self.home_team.abbreviation} "
            f"({self.sport.code}, {self.scheduled_at:%Y-%m-%d})"
        )

    def clean(self):
        errors = {}
        for side in ("home_team", "away_team"):
            team = getattr(self, side) if getattr(self, f"{side}_id") else None
            if team and self.sport_id and team.sport_id != self.sport_id:
                errors[side] = "Team must belong to the game's sport."
        if errors:
            raise ValidationError(errors)


class Injury(models.Model):
    class Status(models.TextChoices):
        OUT = "out", "Out"
        DOUBTFUL = "doubtful", "Doubtful"
        QUESTIONABLE = "questionable", "Questionable"

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="injuries")
    game = models.ForeignKey(GameLog, on_delete=models.CASCADE, related_name="injuries")
    status = models.CharField(max_length=20, choices=Status.choices)
    description = models.TextField(blank=True)
    reported_at = models.DateTimeField()

    class Meta:
        ordering = ["-reported_at"]
        constraints = [
            models.UniqueConstraint(fields=["player", "game"], name="unique_injury_per_player_game"),
        ]

    def __str__(self):
        return f"{self.player.name}: {self.get_status_display()}"


class WeatherCondition(models.Model):
    game = models.OneToOneField(GameLog, on_delete=models.CASCADE, related_name="weather")
    temp_c = models.FloatField()
    precip_mm = models.FloatField(default=0)
    wind_kph = models.FloatField(default=0)
    condition_text = models.CharField(max_length=100, blank=True)
    fetched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(precip_mm__gte=0), name="weather_precip_nonnegative"),
            models.CheckConstraint(condition=Q(wind_kph__gte=0), name="weather_wind_nonnegative"),
        ]

    def __str__(self):
        return f"{self.temp_c:.0f}°C, {self.condition_text or 'unknown'}"


class Rivalry(models.Model):
    # Stored normalized so team_a_id < team_b_id; save() handles the swap.
    team_a = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="rivalries_as_a")
    team_b = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="rivalries_as_b")
    intensity = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    name = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name_plural = "rivalries"
        constraints = [
            models.UniqueConstraint(fields=["team_a", "team_b"], name="unique_rivalry_pair"),
            models.CheckConstraint(
                condition=Q(team_a__lt=F("team_b")), name="rivalry_team_order_normalized"
            ),
            models.CheckConstraint(
                condition=Q(intensity__gte=1, intensity__lte=5), name="rivalry_intensity_range"
            ),
        ]

    def __str__(self):
        label = f"{self.team_a.abbreviation} vs {self.team_b.abbreviation}"
        return f"{self.name} ({label})" if self.name else label

    def save(self, *args, **kwargs):
        if self.team_a_id and self.team_b_id and self.team_a_id > self.team_b_id:
            self.team_a, self.team_b = self.team_b, self.team_a
        super().save(*args, **kwargs)

    @classmethod
    def between(cls, team1, team2):
        """Return the rivalry for two teams in either order, or None."""
        a, b = sorted([team1.pk, team2.pk])
        return cls.objects.filter(team_a_id=a, team_b_id=b).first()


class ExternalAPIMetadata(models.Model):
    class Provider(models.TextChoices):
        BALLDONTLIE = "balldontlie", "balldontlie"
        SPORTSDATA = "sportsdata", "SportsData.io"
        WEATHERAPI = "weatherapi", "WeatherAPI"

    provider = models.CharField(max_length=20, choices=Provider.choices)
    endpoint = models.CharField(max_length=255)
    params_hash = models.CharField(max_length=64)  # sha256 hex digest
    # Null when the request failed without a JSON body.
    response = models.JSONField(null=True, blank=True)
    fetched_at = models.DateTimeField(default=timezone.now)
    status_code = models.PositiveSmallIntegerField()

    class Meta:
        verbose_name = "external API metadata"
        verbose_name_plural = "external API metadata"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "endpoint", "params_hash"], name="unique_api_cache_key"
            ),
        ]

    def __str__(self):
        return f"{self.provider} {self.endpoint} [{self.status_code}]"

    @staticmethod
    def hash_params(params):
        """Stable sha256 of a params dict, independent of key order."""
        payload = json.dumps(params or {}, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode()).hexdigest()


class CommunityVote(models.Model):
    class Value(models.IntegerChoices):
        UP = 1, "Upvote"
        DOWN = -1, "Downvote"

    class Category(models.TextChoices):
        ENJOYMENT = "enjoyment", "Enjoyment"
        COMPETITIVENESS = "competitiveness", "Competitiveness"
        OFFICIATING = "officiating", "Officiating"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="game_votes"
    )
    game = models.ForeignKey(GameLog, on_delete=models.CASCADE, related_name="votes")
    value = models.SmallIntegerField(choices=Value.choices)
    category = models.CharField(max_length=20, choices=Category.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "game", "category"], name="unique_vote_per_user_game_category"
            ),
            models.CheckConstraint(condition=Q(value__in=[1, -1]), name="vote_value_plus_minus_one"),
        ]

    def __str__(self):
        sign = "+1" if self.value == self.Value.UP else "-1"
        return f"{self.user} {sign} {self.category} on game {self.game_id}"
