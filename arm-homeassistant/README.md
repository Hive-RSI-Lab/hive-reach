# arm-homeassistant

Reads Home Assistant state and, only where the person has said so, calls services. Stdlib only.

    ha state light.desk
    ha call light.turn_on light.desk
    ha allowed            # what the config lets through

## Setup (the person does this, no agent signs up for anything)

1. In Home Assistant, make a long-lived access token (profile page). Put it in the secret box as `conn-homeassistant`.
2. Write `~/.config/h2/homeassistant.json`:

        {"url": "http://homeassistant.local:8123",
         "allow": [{"entity": "light.desk", "services": ["light.turn_on", "light.turn_off"]},
                   {"entity": "switch.*", "services": ["switch.toggle"]}],
         "dangerous": []}

## Safety

- `allow` is empty by default, so the arm is read-only until the person lists something. `domain.*` wildcards work in `allow`.
- Locks, alarm panels, sirens, valves, and anything with garage, door, gate, lock, alarm, siren or security in its name are dangerous. They are refused even if `allow` covers them, unless listed in `dangerous` with the exact entity and service. No wildcards there.
- The token is sent only as a Bearer header and never printed or put in errors. State text returned is cleaned and has mentions stripped, so a device name cannot wake an agent.

Tests: `python3 -I test_ha.py` (fake local HTTP server; no real Home Assistant was contacted).
