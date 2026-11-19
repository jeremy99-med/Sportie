"""Claude client: ranks one day's games and explains each rank.

Thin like the other clients: plain dicts in, plain dicts out, no ORM. The DB side (building the
game summaries, the hourly schedule, saving results) is `services/ai_assist.py`.
"""

import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

# The only place the model ID lives (see .claude/docs/external-apis.md).
MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
TIMEOUT_SECONDS = 180
# On a safety decline, the API retries the same request on a fallback model it picks.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = """\
You rank a day's NFL and NBA games for Sportie, a site that tells sports fans which games are \
most worth watching today.

You get every game on the day as JSON. Each game has:
- `subscores`: the site's formula factors, each from 0 to 1. playoff = how much both teams' \
playoff position is in play this late in the season; star_injury = share of the teams' star \
power that is healthy (1 = everyone healthy); weather = how much rain, wind or snow adds to an \
outdoor game (always 0 indoors and for the NBA); momentum = both teams' recent win rate; \
rivalry = rivalry intensity; status = live games highest, finished and postponed games lowest; \
community = fan up/down votes (0.5 = no net votes).
- `formula_score`: those subscores combined into a 0-100 score.
- The facts behind the subscores: records and conference ranks, the forecast, the rivalry, the \
live score, and net votes.
- `injuries`: every reported injury on either team, each with its status and `is_star`. Only \
stars count toward the star_injury subscore, but any listed player is hurt. Never call a team \
"healthy" or "fully healthy" if it has a listed injury.
- `streak` and `recent_games_newest_first` for each team: its last finished games, the first \
entry being its most recent game. `streak` is the current run (e.g. "L1" = lost its last game, \
"W4" = won its last four). Describe recent form from these fields exactly; don't infer a streak \
from the season record.

Rank every game from 1 (most worth watching) to the number of games, using each rank once. \
Use your own judgment of the facts, not just formula_score: for example, weigh which specific \
player is out, how tight a playoff race really is, or whether a live game is close. Games from \
different leagues are ranked against each other.

For each game, write a reason of one to three sentences that a fan can read on the game's card. \
Name the concrete facts that drove the rank (players out, standings, weather, rivalry, form, \
live score). Use only the facts you were given. Do not mention betting, odds or point spreads.\
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "rankings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "game_id": {"type": "integer"},
                    "rank": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["game_id", "rank", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["rankings"],
    "additionalProperties": False,
}


class ClaudeError(Exception):
    """The ranking call failed or returned something unusable."""


def is_configured():
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def rank_games(games):
    """Ask Claude to rank `games` (JSON-safe dicts, each with an integer `id`).

    Returns `[{"game_id", "rank", "reason"}, ...]` sorted by rank, with every input game exactly
    once and ranks renumbered 1..n. Raises ClaudeError on any API failure or bad answer.
    """
    if not games:
        return []
    client = anthropic.Anthropic(timeout=TIMEOUT_SECONDS)
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": "Today's games:\n" + json.dumps(games, sort_keys=True, indent=1),
                }
            ],
        )
    except anthropic.APIStatusError as exc:
        raise ClaudeError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise ClaudeError(f"Could not reach the Anthropic API: {exc}") from exc

    if response.stop_reason == "refusal":
        category = getattr(response.stop_details, "category", None)
        raise ClaudeError(f"Claude declined to rank the games (category: {category})")
    if response.stop_reason == "max_tokens":
        raise ClaudeError("Claude's answer was cut off at max_tokens")

    text = next((block.text for block in response.content if block.type == "text"), None)
    try:
        rankings = json.loads(text)["rankings"]
    except (TypeError, ValueError, KeyError) as exc:
        raise ClaudeError("Claude's answer was not the expected JSON") from exc
    return _validated(rankings, [g["id"] for g in games])


def _validated(rankings, game_ids):
    """Every game exactly once, a non-empty reason each; ranks renumbered 1..n in Claude's order."""
    seen = [r["game_id"] for r in rankings]
    if sorted(seen) != sorted(game_ids):
        missing, extra = set(game_ids) - set(seen), set(seen) - set(game_ids)
        raise ClaudeError(
            f"Claude's ranking doesn't match the games (missing {sorted(missing)}, "
            f"unknown {sorted(extra)}, {len(seen)} entries for {len(game_ids)} games)"
        )
    if any(not r["reason"].strip() for r in rankings):
        raise ClaudeError("Claude left a game without a reason")
    ordered = sorted(rankings, key=lambda r: r["rank"])  # stable, so ties keep Claude's order
    return [
        {"game_id": r["game_id"], "rank": i, "reason": r["reason"].strip()}
        for i, r in enumerate(ordered, start=1)
    ]
