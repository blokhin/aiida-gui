"""Security regression tests for the API.

These test the defense-in-depth protections against cross-site attacks:
CSRF (cross-origin state-changing requests), DNS rebinding (Host header
validation), and the removal of the credential-leaking /debug endpoint.

The `client` and profile fixtures come from tests/backend/conftest.py.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.backend
def test_cross_site_write_rejected(client):
    """A state-changing request from a foreign origin must be rejected (CSRF)."""
    response = client.delete(
        "/api/process/delete/1?dry_run=true",
        headers={"Origin": "https://evil-attacker.com"},
    )
    assert response.status_code == 403


@pytest.mark.backend
def test_cross_site_simple_post_rejected(client):
    """A cross-site POST without preflight (e.g. form post) must be rejected."""
    response = client.post(
        "/api/daemon/stop",
        headers={"Origin": "https://evil-attacker.com"},
    )
    assert response.status_code == 403


@pytest.mark.backend
def test_same_origin_write_allowed(client):
    """A same-origin state-changing request must pass the origin check.

    The daemon is not running in the test profile, so the endpoint returns 400;
    the point is that it is not rejected with 403 by the origin check.
    """
    response = client.post(
        "/api/daemon/stop",
        headers={"Origin": "http://127.0.0.1:8000", "Host": "127.0.0.1:8000"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "The daemon is not running."


@pytest.mark.backend
def test_write_without_origin_allowed(client):
    """Non-browser clients (curl, scripts) send no Origin header and pass."""
    response = client.post("/api/daemon/stop")
    assert response.status_code == 400
    assert response.json()["detail"] == "The daemon is not running."


@pytest.mark.backend
def test_cross_site_preflight_not_approved(client):
    """A preflight request from a foreign origin must not be approved.

    With no `access-control-allow-origin` header in the response, the browser
    blocks the subsequent cross-origin request.
    """
    response = client.options(
        "/api/process/delete/1",
        headers={
            "Origin": "https://evil-attacker.com",
            "Access-Control-Request-Method": "DELETE",
        },
    )
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.backend
def test_foreign_host_rejected(client):
    """Requests with a foreign Host header must be rejected (DNS rebinding)."""
    response = client.get("/api", headers={"Host": "evil-attacker.com"})
    assert response.status_code == 400


@pytest.mark.backend
def test_debug_endpoint_removed(client):
    """The /debug endpoint leaked the full profile (including credentials)."""
    from aiida_gui.app.api import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/debug" not in paths


@pytest.mark.backend
def test_groupnode_members_sortfield_validated(client):
    """Invalid sort fields must be rejected before reaching the query layer."""
    response = client.get(
        "/api/groupnode/1/members-data", params={"sortField": "invalid_column"}
    )
    assert response.status_code == 422

    # A valid sort field passes validation; the group does not exist, so the
    # result is simply empty.
    response = client.get("/api/groupnode/1/members-data", params={"sortField": "pk"})
    assert response.status_code == 200
    assert response.json() == {"total": 0, "data": []}


@pytest.mark.backend
def test_task_action_contract(client):
    """The task action endpoints must accept the payload the frontend sends.

    `WorkFlowItem.tsx` posts `JSON.stringify([{name: ..., pk: ...}])`, where
    `pk` is omitted for tasks that have not run yet.
    """
    from aiida import orm

    workchain = orm.WorkChainNode().store()
    data_node = orm.Data().store()

    # No tasks provided
    response = client.post(f"/api/process/tasks/pause/{workchain.pk}", json=[])
    assert response.status_code == 400
    assert response.json()["detail"] == "No tasks provided"

    # Task without a process (pk omitted by the frontend)
    response = client.post(
        f"/api/process/tasks/pause/{workchain.pk}", json=[{"name": "pending-task"}]
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "None of the selected tasks has a process"

    # Task pk pointing at a non-process node
    response = client.post(
        f"/api/process/tasks/kill/{workchain.pk}",
        json=[{"name": "task", "pk": data_node.pk}],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == f"Node {data_node.pk} is not a process"

    # Workchain id pointing at a non-workchain node
    response = client.post(
        f"/api/process/tasks/pause/{data_node.pk}",
        json=[{"name": "task", "pk": workchain.pk}],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == f"Node {data_node.pk} is not a workchain"

    # Garbage pk fails validation instead of crashing the handler
    response = client.post(
        f"/api/process/tasks/pause/{workchain.pk}",
        json=[{"name": "task", "pk": "not-a-number"}],
    )
    assert response.status_code == 422


@pytest.mark.backend
def test_allowed_hosts_parsing():
    """Hosts parsing normalizes entries; empty falls back to defaults."""
    from aiida_gui.app.api import DEFAULT_ALLOWED_HOSTS, _parse_allowed_hosts

    assert _parse_allowed_hosts("") == DEFAULT_ALLOWED_HOSTS
    assert _parse_allowed_hosts(",,,") == DEFAULT_ALLOWED_HOSTS
    assert _parse_allowed_hosts(" LocalHost ,, 0.0.0.0 ") == ["localhost", "0.0.0.0"]


@pytest.mark.backend
def test_allowed_origins_parsing():
    """Origins parsing normalizes case and trailing slashes; empty means none."""
    from aiida_gui.app.api import _parse_allowed_origins

    assert _parse_allowed_origins("") == []
    assert _parse_allowed_origins(
        "HTTP://LocalHost:3000/, https://foo.example.com"
    ) == [
        "http://localhost:3000",
        "https://foo.example.com",
    ]


@pytest.mark.backend
def test_cors_allowlist_opt_in(set_backend_server_settings):
    """Configuring AIIDA_GUI_ALLOWED_ORIGINS allows exactly those origins.

    The middleware is wired at import time from environment settings, so this
    runs the app in a subprocess with the setting configured, against the same
    profile the test session uses.
    """
    script = textwrap.dedent(
        """
        from fastapi.testclient import TestClient
        from aiida_gui.app.api import app

        client = TestClient(
            app, headers={"Host": "localhost"}, raise_server_exceptions=False
        )
        allowed = client.post(
            "/api/daemon/stop",
            headers={"Origin": "http://localhost:3000"},
        )
        evil = client.post(
            "/api/daemon/stop",
            headers={"Origin": "https://evil-attacker.com"},
        )
        preflight = client.options(
            "/api/process/delete/1",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "DELETE",
            },
        )
        import json

        print(
            json.dumps(
                {
                    "allowed_status": allowed.status_code,
                    "evil_status": evil.status_code,
                    "preflight_status": preflight.status_code,
                    "preflight_allow_origin": preflight.headers.get(
                        "access-control-allow-origin"
                    ),
                    "preflight_allow_credentials": preflight.headers.get(
                        "access-control-allow-credentials"
                    ),
                }
            )
        )
        """
    )
    env = {**os.environ, "AIIDA_GUI_ALLOWED_ORIGINS": "http://localhost:3000"}
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])

    # The allowlisted origin passes the CSRF check (daemon not running -> 400),
    # a foreign origin is still rejected with 403.
    assert payload["allowed_status"] == 400
    assert payload["evil_status"] == 403

    # The CORS middleware is mounted and approves exactly the allowlisted
    # origin - without allowing credentials.
    assert payload["preflight_status"] == 200
    assert payload["preflight_allow_origin"] == "http://localhost:3000"
    assert payload["preflight_allow_credentials"] is None
