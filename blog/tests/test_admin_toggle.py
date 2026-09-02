"""The admin route is opt-in and off a non-default path — lock both in."""

from django.conf import settings
from django.urls import NoReverseMatch, reverse


def test_admin_is_disabled_by_default():
    assert settings.ADMIN_ENABLED is False
    # The route isn't mounted, so the admin namespace can't be reversed.
    try:
        reverse("admin:index")
        mounted = True
    except NoReverseMatch:
        mounted = False
    assert not mounted


def test_admin_url_default_is_not_the_scanned_path():
    assert settings.ADMIN_URL == "backoffice/"
    assert not settings.ADMIN_URL.startswith("/")
    assert settings.ADMIN_URL.endswith("/")
