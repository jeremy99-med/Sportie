# External APIs (Community Game Ranker)

The clients live in `backend/apps/community_game_ranker/integrations/`, one module per provider.
Before you depend on any URL, rate limit, or field name below, check the provider's
current docs. Values marked TODO are unverified.

| Provider | Used for | Env var | Base URL |
|---|---|---|---|
| balldontlie | NBA schedule, standings | `BALLDONTLIE_API_KEY` | TODO (verify, e.g. `https://api.balldontlie.io/v1`) |
| SportsData.io | All leagues: injuries, standings, schedules, game status | `SPORTSDATA_API_KEY` | TODO (per-league paths) |
| WeatherAPI.com | Stadium forecast by lat/lon | `WEATHERAPI_KEY` | TODO (verify, e.g. `https://api.weatherapi.com/v1`) |
| Anthropic | Playoff-implication reasoning | `ANTHROPIC_API_KEY` | Use the `claude-api` skill; never hardcode the model ID elsewhere |

Rate limits and free-tier quotas: TODO. Write them here once confirmed.

## Client pattern

```python
# integrations/weatherapi.py
import os
import requests

TIMEOUT = 10

class WeatherAPIError(Exception): ...

def get_forecast(lat: float, lon: float, when) -> dict:
    """Return a normalized dict: {temp_c, precip_mm, wind_kph, condition_text}."""
    resp = requests.get(..., params={"key": os.environ["WEATHERAPI_KEY"], ...}, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise WeatherAPIError(resp.status_code, resp.text[:200])
    return _normalize(resp.json())
```

- Always set a `timeout`. Raise a provider-specific exception on non-200 responses.
- Return **normalized** dicts. Code outside the client should never see raw provider JSON.
- The client does no ORM work. Caching and upserts go in `services/ingest.py`, which writes
  `ExternalAPIMetadata` and checks it before calling the API (to save quota).
- Read keys from `os.environ`, and add each key to `backend/.env.example`.

## Testing

- Patch `requests.get` (or use the `responses` library if it's added) with recorded sample
  payloads saved in `tests/fixtures/<provider>/*.json`.
- Each provider needs one success test (normalized output) and one invalid-request test
  (raises the provider exception).
