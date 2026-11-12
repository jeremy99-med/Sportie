from collections import defaultdict

from django.db import transaction

from apps.community_game_ranker.models import Player, Team

MAX_STARS_PER_TEAM = 5
# Minimum games played before a player can be picked as a star, per sport.
MIN_GAMES = {"NBA": 5, "NFL": 4}
# Positions that score fantasy points but never draw viewers. Use "always" overrides to add anyone.
NON_STAR_POSITIONS = {"NFL": {"K", "P", "LS"}}


class StarListError(ValueError): ...


def pick_stars(player_stats, per_team=3, min_games=5):
    """Pick each team's top players by metric. Pure: no DB access.

    `player_stats` is an iterable of dicts with `name`, `team_abbreviation`, `games` and `metric`
    (the SportsData client computes the metric: NBA points+rebounds+assists per game, NFL season
    fantasy points). Returns {team_abbreviation: [names, best first]}.
    """
    per_team = min(per_team, MAX_STARS_PER_TEAM)
    by_team = defaultdict(list)
    for row in player_stats:
        team = row.get("team_abbreviation")
        if not team or (row.get("games") or 0) < min_games:
            continue
        by_team[team].append(row)
    picked = {}
    for team, rows in by_team.items():
        rows.sort(key=lambda r: (-(r.get("metric") or 0), r["name"]))
        names = []
        for row in rows:
            if row["name"] not in names:
                names.append(row["name"])
            if len(names) == per_team:
                break
        picked[team] = names
    return picked


def _entry(entry):
    """An override entry is "Name" or {"name": ..., "team": "ABBR"}."""
    if isinstance(entry, str):
        return entry, None
    if isinstance(entry, dict) and entry.get("name"):
        return entry["name"], entry.get("team")
    raise StarListError(f"Bad override entry {entry!r}; use a name or {{'name', 'team'}}.")


def _validate_overrides(overrides):
    for sport_code, spec in overrides.items():
        if not isinstance(spec, dict) or not set(spec) <= {"always", "never"}:
            raise StarListError(
                f"{sport_code}: overrides must look like {{'always': [...], 'never': [...]}}."
            )


def _resolve_always(sport_code, entries):
    """Map each `always` entry to (team, name), looking bare names up among the sport's players."""
    resolved = []
    for entry in entries:
        name, abbreviation = _entry(entry)
        if abbreviation is None:
            matches = list(
                Player.objects.filter(team__sport__code=sport_code, name=name).select_related("team")
            )
            if len(matches) != 1:
                raise StarListError(
                    f"{sport_code} '{name}': name matches {len(matches)} players; "
                    "give {'name', 'team'} instead."
                )
            team = matches[0].team
        else:
            try:
                team = Team.objects.get(sport__code=sport_code, abbreviation=abbreviation)
            except Team.DoesNotExist:
                raise StarListError(f"Unknown team {sport_code} {abbreviation}.") from None
        resolved.append((team, name))
    return resolved


@transaction.atomic
def sync_stars(computed=None, overrides=None):
    """Set `is_star` from computed picks, then apply the overrides.

    `computed` is {sport_code: {team_abbreviation: [names, best first]}} (e.g. from `pick_stars`).
    `overrides` is {sport_code: {"always": [...], "never": [...]}}. Per team the final list is
    always-names first, then computed names (never-names removed), capped at 5. Teams without
    computed picks start from their current stars, so an overrides-only run does not wipe the
    stars of other teams. Anyone on a touched team who is not in the final list loses `is_star`.
    Returns (marked, cleared) counts.
    """
    computed = computed or {}
    overrides = overrides or {}
    _validate_overrides(overrides)

    marked = cleared = 0
    for sport_code in set(computed) | set(overrides):
        teams = dict(computed.get(sport_code, {}))
        spec = overrides.get(sport_code, {})
        never = {_entry(e)[0] for e in spec.get("never", [])}
        always = defaultdict(list)
        for team, name in _resolve_always(sport_code, spec.get("always", [])):
            always[team.abbreviation].append(name)

        team_abbrs = set(teams) | set(always)
        for abbreviation in sorted(team_abbrs):
            if len(teams.get(abbreviation, [])) > MAX_STARS_PER_TEAM:
                raise StarListError(
                    f"{sport_code} {abbreviation} lists {len(teams[abbreviation])} stars "
                    f"(max {MAX_STARS_PER_TEAM})."
                )
            if len(always[abbreviation]) > MAX_STARS_PER_TEAM:
                raise StarListError(
                    f"{sport_code} {abbreviation} has more than {MAX_STARS_PER_TEAM} 'always' stars."
                )
            try:
                team = Team.objects.get(sport__code=sport_code, abbreviation=abbreviation)
            except Team.DoesNotExist:
                raise StarListError(f"Unknown team {sport_code} {abbreviation}.") from None

            if abbreviation in teams:
                base = teams[abbreviation]
            else:
                base = list(
                    team.players.filter(is_star=True).order_by("name").values_list("name", flat=True)
                )
            final = []
            for name in [*always[abbreviation], *base]:
                if name not in final and name not in never:
                    final.append(name)
            final = final[:MAX_STARS_PER_TEAM]

            for name in final:
                Player.objects.update_or_create(team=team, name=name, defaults={"is_star": True})
            marked += len(final)
            cleared += (
                Player.objects.filter(team=team, is_star=True).exclude(name__in=final).update(is_star=False)
            )
        # "never" also applies to teams we did not touch (e.g. a star the stats still list).
        if never:
            cleared += Player.objects.filter(
                team__sport__code=sport_code, name__in=never, is_star=True
            ).update(is_star=False)
    return marked, cleared
