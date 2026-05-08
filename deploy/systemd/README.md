# systemd units for IMX8MP deployment

This folder contains production unit files and drop-ins for the remote embedded host.

Current deployment model:

- `docker build` / `docker run` create the image and container
- `pixi-dash.service` starts the existing `pixi-dash` container at boot
- `chromium-kiosk.service` waits for the dashboard service
- `wait-online-any.conf` and `docker-no-network-online.conf` reduce boot delay caused by `network-online.target`

## Install production units

```bash
sudo mkdir -p /etc/systemd/system/systemd-networkd-wait-online.service.d
sudo mkdir -p /etc/systemd/system/docker.service.d

sudo cp deploy/systemd/pixi-dash.service /etc/systemd/system/pixi-dash.service
sudo cp deploy/systemd/wait-online-any.conf /etc/systemd/system/systemd-networkd-wait-online.service.d/any.conf
sudo cp deploy/systemd/docker-no-network-online.conf /etc/systemd/system/docker.service.d/no-network-online.conf

sudo systemctl daemon-reload
sudo systemctl enable pixi-dash.service
sudo systemctl restart systemd-networkd-wait-online.service
sudo systemctl restart docker.service
sudo systemctl restart pixi-dash.service
```

## Verify service chain

```bash
systemctl status pixi-dash.service --no-pager
systemctl status docker.service --no-pager
systemctl cat systemd-networkd-wait-online.service
systemctl show docker.service -p After -p Wants
docker ps --filter name=pixi-dash
curl -sS -m 5 http://127.0.0.1:8080/api/snapshot | head -c 300 && echo
```

## Verify boot performance

```bash
systemd-analyze time
systemd-analyze blame | head -10
systemd-analyze critical-chain --no-pager | head -30
```

Expected result on `tep-imx8mp` after these drop-ins:

- total boot around 20 seconds
- `systemd-networkd-wait-online.service` no longer waits 120 seconds for `eth1`
- `docker.service` starts in about 1.6 to 1.8 seconds
- `pixi-dash` container is already up when kiosk launches

## Notes

- `chromium-kiosk.service` already depends on `pixi-dash.service` on this target host.
- Keep container restart policy as `unless-stopped`.
- `wait-online-any.conf` is needed because `eth1` is configured but has no carrier on this target.
- `docker-no-network-online.conf` is a belt-and-suspenders safeguard so Docker is not blocked by a failing `network-online.target`.
