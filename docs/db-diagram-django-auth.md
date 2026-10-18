# Sportie database diagram: Django authentication and authorization

Built-in tables from `django.contrib.auth`, `contenttypes`, `sessions` and `admin`, as enabled in
`backend/config/settings.py`. No custom `AUTH_USER_MODEL` is set, so `User` is the stock `auth.User`.

```mermaid
erDiagram
    %% ---- django.contrib.auth ----
    User {
        int id PK
        string username UK
        string email
        string password "salted hash"
        bool is_active
        bool is_staff
        bool is_superuser
        datetime last_login "nullable"
    }
    Group {
        int id PK
        string name UK
    }
    Permission {
        int id PK
        int content_type_id FK
        string codename "e.g. add_communityvote"
        string name
    }
    UserGroups {
        int id PK
        int user_id FK
        int group_id FK
    }
    UserPermissions {
        int id PK
        int user_id FK
        int permission_id FK
    }
    GroupPermissions {
        int id PK
        int group_id FK
        int permission_id FK
    }

    %% ---- django.contrib.contenttypes ----
    ContentType {
        int id PK
        string app_label
        string model
    }

    %% ---- django.contrib.sessions ----
    Session {
        string session_key PK
        text session_data "encoded; holds _auth_user_id"
        datetime expire_date
    }

    %% ---- django.contrib.admin ----
    LogEntry {
        int id PK
        int user_id FK
        int content_type_id FK "nullable"
        string object_id
        int action_flag "1 add | 2 change | 3 delete"
        datetime action_time
    }

    %% ---- Sportie link ----
    CommunityVote {
        int id PK
        int user_id FK
        int game_id FK
    }

    User ||--o{ UserGroups : "belongs via"
    Group ||--o{ UserGroups : "contains via"
    User ||--o{ UserPermissions : "granted directly"
    Permission ||--o{ UserPermissions : "assigned via"
    Group ||--o{ GroupPermissions : "granted"
    Permission ||--o{ GroupPermissions : "assigned via"
    ContentType ||--o{ Permission : "scopes"
    User ||--o{ LogEntry : "performs"
    ContentType |o--o{ LogEntry : "targets"
    User ||--o{ CommunityVote : "casts"
```

**Legend.** `UserGroups`, `UserPermissions` and `GroupPermissions` are the many-to-many join tables
(`auth_user_groups`, `auth_user_user_permissions`, `auth_group_permissions`); each pair of FKs is unique.
`Session` has no real FK to `User`: the logged-in user's id lives inside the encoded `session_data`.
A user's effective permissions are their direct permissions plus those of every group they belong to;
`is_superuser` bypasses all checks.
