# Welcome to AiiDA GUI!
[![PyPI version](https://badge.fury.io/py/aiida-gui.svg)](https://badge.fury.io/py/aiida-gui)
[![Docs status](https://readthedocs.org/projects/aiida-gui/badge)](http://aiida-gui.readthedocs.io/)
[![Unit test](https://github.com/aiidateam/aiida-gui/actions/workflows/ci.yml/badge.svg)](https://github.com/aiidateam/aiida-gui/actions/workflows/ci.yml)


Web UI to visualize and manage the AiiDA WorkGraph.


## Installation

```bash
pip install aiida-gui
````

## Usage

Start the AiiDA GUI server with the following command:

```bash
aiida-gui start
```

Open `http://localhost:8000` to access the AiiDA GUI in your web browser.

Stop the AiiDA GUI server with the following command:

```bash
aiida-gui stop
```

## Security settings

The backend only accepts same-origin requests: the React frontend is served by
the same server that hosts the API, and requests with a foreign `Origin`
(state-changing methods) or `Host` header are rejected. This blocks
cross-site request forgery and DNS-rebinding attacks against the local server.

The behavior can be adjusted with environment variables:

- `AIIDA_GUI_ALLOWED_ORIGINS`: comma-separated list of origins that may make
  cross-origin requests to the backend, e.g.
  `AIIDA_GUI_ALLOWED_ORIGINS=http://localhost:3000`. Empty (default) means
  cross-origin requests are not allowed. Needed if you serve the frontend from
  a development server that proxies to the backend *and* rewrites the `Host`
  header. Only exact origins are supported; wildcards are not.
- `AIIDA_GUI_ALLOWED_HOSTS`: comma-separated list of accepted `Host` header
  values (defaults to `localhost,127.0.0.1,0.0.0.0`). Extend this if you bind
  the server to another address, e.g.
  `AIIDA_GUI_ALLOWED_HOSTS=localhost,127.0.0.1,myhost.example.com`.
- `AIIDA_GUI_PROFILE`: the AiiDA profile to load (empty for the default one).
