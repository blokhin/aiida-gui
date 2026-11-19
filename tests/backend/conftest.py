import pytest
from fastapi.testclient import TestClient
import os


@pytest.fixture(scope="module", autouse=True)
def aiida_profile(aiida_config, aiida_profile_factory):
    """Create and load a profile with RabbitMQ as broker for backend tests."""
    with aiida_profile_factory(aiida_config, broker_backend="core.rabbitmq") as profile:
        yield profile


@pytest.fixture(scope="module")
def set_backend_server_settings(aiida_profile):
    os.environ["AIIDA_GUI_PROFILE"] = aiida_profile.name


@pytest.fixture(scope="module")
def client(set_backend_server_settings):
    from aiida_gui.app.api import app

    # The app validates the `Host` header of every request, and the production
    # defaults do not include the TestClient's `Host: testserver`. Send
    # `Host: localhost` by default so the tests exercise the production
    # configuration exactly as a browser would.
    return TestClient(app, headers={"Host": "localhost"})
