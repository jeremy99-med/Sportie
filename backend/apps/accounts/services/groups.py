from django.contrib.auth.models import Group, Permission
from django.db.models import Q

NORMAL = "Normal"
ADMIN = "Admin"
SUPERADMIN = "Superadmin"

FEATURE_APPS = ["community_game_ranker", "video_analyzer"]

# Ranker models a Normal user may read but not change.
RANKER_READ_ONLY_MODELS = [
    "sport",
    "team",
    "stadium",
    "player",
    "teamstanding",
    "gamelog",
    "injury",
    "weathercondition",
    "rivalry",
]


def normal_permissions():
    """Read the ranker data and manage votes (views must still limit edits to the user's own)."""
    return Permission.objects.filter(
        Q(content_type__app_label="community_game_ranker")
        & (
            Q(codename__in=[f"view_{model}" for model in RANKER_READ_ONLY_MODELS])
            | Q(content_type__model="communityvote")
        )
    )


def admin_permissions():
    """Full control of both features' data, read-only access to users, groups, and admin history."""
    return Permission.objects.filter(
        Q(content_type__app_label__in=FEATURE_APPS)
        | Q(content_type__app_label="auth", codename__in=["view_user", "view_group"])
        | Q(content_type__app_label="admin", codename="view_logentry")
    )


def sync_groups():
    """Create the three groups and reset their permissions to the definitions above.

    Safe to run repeatedly. Runs after every `migrate`, so Superadmin picks up new models'
    permissions automatically, and manual permission edits in the admin site get overwritten.
    """
    definitions = {
        NORMAL: normal_permissions(),
        ADMIN: admin_permissions(),
        SUPERADMIN: Permission.objects.all(),
    }
    for name, permissions in definitions.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.set(permissions)


def add_to_default_group(user):
    """Put a new user in Superadmin if they're a superuser, otherwise in Normal."""
    group = Group.objects.filter(name=SUPERADMIN if user.is_superuser else NORMAL).first()
    if group:
        user.groups.add(group)
