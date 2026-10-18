# Sportie database diagram: Community Game Ranker

Generated from `backend/apps/community_game_ranker/models.py` (migration `0001_initial_ranker_models`).

```mermaid
erDiagram
    %% ---- django.contrib.auth ----
    User {
        int id PK
        string username
        string email
    }

    %% ---- Community Game Ranker ----
    Sport {
        int id PK
        string code UK "NFL | NBA | NHL | MLB"
        string name
        bool is_outdoor_default
    }
    Team {
        int id PK
        int sport_id FK
        string name
        string abbreviation "unique per sport"
        json external_ids
    }
    Stadium {
        int id PK
        int home_team_id FK "nullable: neutral site"
        string name
        decimal latitude
        decimal longitude
        bool is_indoor
    }
    Player {
        int id PK
        int team_id FK "nullable: free agent"
        string name
        string position
        bool is_star
    }
    GameLog {
        int id PK
        int sport_id FK
        int home_team_id FK
        int away_team_id FK
        int stadium_id FK "nullable"
        datetime scheduled_at
        string status
        float importance_score "nullable"
        json score_breakdown
    }
    Injury {
        int id PK
        int player_id FK
        int game_id FK
        string status "out | doubtful | questionable"
        datetime reported_at
    }
    WeatherCondition {
        int id PK
        int game_id FK,UK
        float temp_c
        float precip_mm
        float wind_kph
    }
    Rivalry {
        int id PK
        int team_a_id FK "team_a_id < team_b_id"
        int team_b_id FK
        int intensity "1-5"
        string name
    }
    CommunityVote {
        int id PK
        int user_id FK
        int game_id FK
        int value "+1 | -1"
        string category "enjoyment | competitiveness | officiating"
    }
    ExternalAPIMetadata {
        int id PK
        string provider "balldontlie | sportsdata | weatherapi"
        string endpoint
        string params_hash "sha256"
        int status_code
    }

    Sport ||--o{ Team : "has"
    Sport ||--o{ GameLog : "categorizes"
    Team |o--o{ Stadium : "plays home at"
    Team |o--o{ Player : "rosters"
    Team ||--o{ GameLog : "hosts (home)"
    Team ||--o{ GameLog : "visits (away)"
    Stadium |o--o{ GameLog : "venue for"
    Team ||--o{ Rivalry : "is team_a"
    Team ||--o{ Rivalry : "is team_b"
    Player ||--o{ Injury : "suffers"
    GameLog ||--o{ Injury : "affected by"
    GameLog ||--o| WeatherCondition : "has forecast"
    GameLog ||--o{ CommunityVote : "receives"
    User ||--o{ CommunityVote : "casts"

    %% ---- Video Analyzer ----
    %% Not shown: video_analyzer/models.py has no models yet.
```

**Legend.** `||` = exactly one, `|o` = zero or one (nullable FK), `o{` = zero or many, `o|` = optional one-to-one.
`ExternalAPIMetadata` stands alone: it's a response cache and audit log keyed by (provider, endpoint, params_hash), with no FKs.
Unique constraints not drawn: Team (sport, abbreviation), Injury (player, game), Rivalry (team_a, team_b), CommunityVote (user, game, category).
