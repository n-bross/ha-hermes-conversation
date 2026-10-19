# Hermes Home Assistant Conversation Integration

A HACS-installable Home Assistant custom integration that exposes a native Assist conversation agent named **Hermes**, forwarding requests to the real Hermes Agent running on the user's own machine.

## What it does

- Adds a selectable Assist agent called **Hermes** in Home Assistant.
- Every voice or text request is sent to a small external HTTP bridge.
- The bridge shells out to the existing `hermes` CLI/profile, so memories, skills, and tools remain inside Hermes.
- Conversation continuity across follow-ups in the same HA conversation is preserved via a SQLite session map.

## Architecture

```text
Home Assistant  <--HTTP JSON-->  Hermes bridge  <--subprocess-->  Hermes CLI/profile
```

The bridge is deliberately external: it runs where Hermes runs and never inside the HA Python process. This keeps Hermes memory, tools, and skills intact without reimplementing them.

## Repository layout

```text
ha-hermes-conversation/
├── custom_components/hermes_conversation/   HA custom integration
├── bridge/                                   FastAPI bridge service
├── tests/                                    pytest suite
├── scripts/                                  Run/install helpers
└── examples/                                 Config samples
```

## Installation

### 1. Install the bridge where Hermes runs

```bash
cd bridge
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export HERMES_BRIDGE_TOKEN="change-me-now"
export HERMES_PROFILE="default"
# HERMES_BIN defaults to "hermes" on PATH
python -m uvicorn app:app --host 127.0.0.1 --port 8787
```

Or use the provided helper:

```bash
bash scripts/run_bridge.sh
```

Copy `examples/bridge.env.example` to a real env file and source it before starting the bridge.

### 2. Install the HA integration via HACS

1. Open HACS → Custom repositories.
2. Add `https://github.com/n-bross/ha-hermes-conversation` as an **Integration**.
3. Download it.
4. Restart Home Assistant.
5. Add the integration in **Settings → Devices & services → Add integration → Hermes Conversation**.
6. Enter:
   - Bridge URL, e.g. `http://127.0.0.1:8787`
   - Bearer token matching `HERMES_BRIDGE_TOKEN`
   - Hermes profile name (default `default`)
   - Request timeout (default `30`)

### 3. Select Hermes as Assist agent

1. Go to **Settings → Voice assistants → [your pipeline]**.
2. Under **Conversation agent**, pick **Hermes**.
3. Try a text request in the Assist dialog.

## MVP limitations

- **All requests go to Hermes.** Fast-path local routing for simple device control is planned for a future release.
- The bridge must be started and reachable separately from Home Assistant.
- Session mapping is local SQLite on the bridge host; if the bridge database is deleted, follow-up conversations start fresh Hermes sessions.

## Development

Run tests:

```bash
pip install -r requirements_dev.txt
pytest -q
```

Run the bridge locally:

```bash
cd bridge
HERMES_BRIDGE_TOKEN=test uvicorn app:app --host 127.0.0.1 --port 8787
```

Health check:

```bash
curl http://127.0.0.1:8787/health
```

## Security notes

- Bind the bridge to `127.0.0.1` unless you have a trusted reverse proxy / Tailnet.
- Keep `HERMES_BRIDGE_TOKEN` secret; it is the only authentication between HA and the bridge.
- The bridge builds Hermes argument arrays and never uses `shell=True`.

## License

MIT
