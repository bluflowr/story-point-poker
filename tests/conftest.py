import pytest

from rooms import limits


@pytest.fixture(autouse=True)
def plain_static_storage(settings):
    # The production storage needs `collectstatic` to have run first.
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    limits.reset_all()
    yield
    limits.reset_all()
