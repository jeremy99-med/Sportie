from django.contrib import admin

from .models import (
    CommunityVote,
    ExternalAPIMetadata,
    GameLog,
    Injury,
    Player,
    Rivalry,
    Sport,
    Stadium,
    Team,
    TeamStanding,
    WeatherCondition,
)


@admin.register(Sport)
class SportAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_outdoor_default")


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("abbreviation", "name", "city", "sport")
    list_filter = ("sport",)
    search_fields = ("name", "abbreviation", "city")


@admin.register(Stadium)
class StadiumAdmin(admin.ModelAdmin):
    list_display = ("name", "home_team", "is_indoor", "latitude", "longitude")
    list_filter = ("is_indoor",)


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("name", "team", "position", "is_star")
    list_filter = ("is_star", "team__sport")
    search_fields = ("name",)


@admin.register(TeamStanding)
class TeamStandingAdmin(admin.ModelAdmin):
    list_display = ("team", "season", "wins", "losses", "conference_rank")
    list_filter = ("season", "team__sport")


@admin.register(GameLog)
class GameLogAdmin(admin.ModelAdmin):
    list_display = ("__str__", "scheduled_at", "status", "importance_score")
    list_filter = ("sport", "status")
    date_hierarchy = "scheduled_at"


@admin.register(Injury)
class InjuryAdmin(admin.ModelAdmin):
    list_display = ("player", "game", "status", "reported_at")
    list_filter = ("status",)


@admin.register(WeatherCondition)
class WeatherConditionAdmin(admin.ModelAdmin):
    list_display = ("game", "temp_c", "precip_mm", "wind_kph", "condition_text")


@admin.register(Rivalry)
class RivalryAdmin(admin.ModelAdmin):
    list_display = ("__str__", "team_a", "team_b", "intensity")


@admin.register(ExternalAPIMetadata)
class ExternalAPIMetadataAdmin(admin.ModelAdmin):
    list_display = ("provider", "endpoint", "status_code", "fetched_at")
    list_filter = ("provider", "status_code")


@admin.register(CommunityVote)
class CommunityVoteAdmin(admin.ModelAdmin):
    list_display = ("user", "game", "value", "created_at")
    list_filter = ("value",)
