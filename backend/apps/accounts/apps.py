from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate, post_save


def _sync_groups(sender, **kwargs):
    from .services.groups import sync_groups

    sync_groups()


def _add_new_user_to_default_group(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        from .services.groups import add_to_default_group

        add_to_default_group(instance)


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"

    def ready(self):
        # This app is last in INSTALLED_APPS, so every other app's permissions exist by the
        # time its post_migrate signal fires.
        post_migrate.connect(_sync_groups, sender=self)
        post_save.connect(_add_new_user_to_default_group, sender=settings.AUTH_USER_MODEL)
