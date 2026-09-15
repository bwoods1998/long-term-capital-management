# Running the floor on this machine

```sh
cp deploy/ltcm.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ltcm.service
systemctl --user status ltcm.service
journalctl --user -u ltcm.service -f
```

Stop new orders immediately without stopping the service: `python3 -m ltcm kill`.
Stop everything: `systemctl --user stop ltcm.service`.
The host keep-awake service from `~/Work/agent-host` keeps the laptop from sleeping on AC.

## Going live

The floor starts in paper mode. Real capital is an owner decision, recorded as a public event:

```sh
# enable venues in ltcm/config.json:  "live_venues": ["kalshi", "coinbase"]
.venv/bin/python -m ltcm promote kalshi-01 --to live --reason "first live sleeve"
.venv/bin/python -m ltcm promote crypto-01 --to live --reason "first live sleeve"
systemctl --user restart ltcm.service
```

Each desk's `capital.usd` in its manifest is its live sleeve. `python3 -m ltcm promote <desk> --to paper`
sends a desk back to paper.
