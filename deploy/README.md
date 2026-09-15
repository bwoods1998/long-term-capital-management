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
