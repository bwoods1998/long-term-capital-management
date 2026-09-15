# Running the floor on this machine

```sh
cp deploy/woodscapital.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now woodscapital.service
systemctl --user status woodscapital.service
journalctl --user -u woodscapital.service -f
```

Stop new orders immediately without stopping the service: `python3 -m woodscapital kill`.
Stop everything: `systemctl --user stop woodscapital.service`.
The host keep-awake service from `~/Work/agent-host` keeps the laptop from sleeping on AC.

## Going live

The floor starts in paper mode. Real capital is an owner decision, recorded as a public event:

```sh
# enable venues in woodscapital/config.json:  "live_venues": ["kalshi", "coinbase"]
.venv/bin/python -m woodscapital promote kalshi-01 --to live --reason "first live sleeve"
.venv/bin/python -m woodscapital promote crypto-01 --to live --reason "first live sleeve"
systemctl --user restart woodscapital.service
```

Each desk's `capital.usd` in its manifest is its live sleeve. `python3 -m woodscapital promote <desk> --to paper`
sends a desk back to paper.
