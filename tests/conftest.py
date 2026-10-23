import pytest


@pytest.fixture(autouse=True)
def plain_static_storage(settings):
    # The production storage needs `collectstatic` to have run first.
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
