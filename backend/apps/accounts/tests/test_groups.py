import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

from apps.accounts.services.groups import ADMIN, NORMAL, SUPERADMIN, sync_groups

pytestmark = pytest.mark.django_db

User = get_user_model()


def codenames(group_name):
    return set(Group.objects.get(name=group_name).permissions.values_list("codename", flat=True))


def test_migrate_creates_the_three_groups():
    assert set(Group.objects.values_list("name", flat=True)) == {NORMAL, ADMIN, SUPERADMIN}


def test_superadmin_has_every_permission():
    assert Group.objects.get(name=SUPERADMIN).permissions.count() == Permission.objects.count()


def test_normal_can_read_games_and_vote_but_not_edit_games():
    perms = codenames(NORMAL)
    assert {"view_gamelog", "view_team", "add_communityvote", "delete_communityvote"} <= perms
    assert "change_gamelog" not in perms
    assert "view_externalapimetadata" not in perms
    assert not any(p.endswith("_user") for p in perms)


def test_admin_manages_feature_data_but_not_users():
    perms = codenames(ADMIN)
    assert {"change_gamelog", "delete_communityvote", "view_externalapimetadata"} <= perms
    assert "view_user" in perms
    assert not {"add_user", "change_user", "delete_user", "change_group"} & perms


def test_sync_groups_is_idempotent_and_resets_manual_edits():
    normal = Group.objects.get(name=NORMAL)
    normal.permissions.add(Permission.objects.get(codename="delete_user"))

    sync_groups()
    sync_groups()

    assert Group.objects.filter(name=NORMAL).count() == 1
    assert "delete_user" not in codenames(NORMAL)


def test_new_user_joins_normal():
    user = User.objects.create_user("fan", password="pw-12345-test")
    assert list(user.groups.values_list("name", flat=True)) == [NORMAL]


def test_new_superuser_joins_superadmin():
    user = User.objects.create_superuser("boss", password="pw-12345-test")
    assert list(user.groups.values_list("name", flat=True)) == [SUPERADMIN]


def test_updating_a_user_does_not_change_groups():
    user = User.objects.create_user("fan", password="pw-12345-test")
    user.groups.clear()
    user.email = "fan@example.com"
    user.save()
    assert not user.groups.exists()
