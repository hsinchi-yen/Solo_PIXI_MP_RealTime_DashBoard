# systemd units for IMX8MP deployment

This folder contains production unit files for the remote embedded host.

## Install pixi-dash.service

```bash
sudo cp deploy/systemd/pixi-dash.service /etc/systemd/system/pixi-dash.service
sudo systemctl daemon-reload
sudo systemctl enable pixi-dash.service
sudo systemctl restart pixi-dash.service
```

## Verify

```bash
systemctl status pixi-dash.service --no-pager
systemctl status docker.service --no-pager
docker ps --filter name=pixi-dash
curl -sS -m 5 http://127.0.0.1:8080/api/snapshot | head -c 300 && echo
```

## Notes

- `chromium-kiosk.service` already depends on `pixi-dash.service` on this target host.
- Keep container restart policy as `unless-stopped`.
