$remote_host = "root@10.20.31.106"
$remote_dir = "/home/Solo_PIXI_MP_RealTime_DashBoard"

Write-Host "Deploying updated files to $remote_host..."

# Copy changed source files
scp .\app\uploader.py  "$remote_host`:$remote_dir/app/uploader.py"
scp .\app\main.py      "$remote_host`:$remote_dir/app/main.py"
scp .\frontend\index.html "$remote_host`:$remote_dir/frontend/index.html"
scp .\frontend\style.css  "$remote_host`:$remote_dir/frontend/style.css"
scp .\frontend\dashboard.js "$remote_host`:$remote_dir/frontend/dashboard.js"

Write-Host "Files deployed. Rebuilding Docker image on remote..."

# Rebuild image and restart container (no docker-compose on this host)
$rebuild = @'
set -e
cd /home/Solo_PIXI_MP_RealTime_DashBoard
docker stop pixi-dash 2>/dev/null || true
docker rm   pixi-dash 2>/dev/null || true
docker build --no-cache -t pixi-dashboard .
docker run -d --name pixi-dash \
  --restart unless-stopped \
  --memory 256m \
  -p 8080:8080 \
  -v /home/Solo_PIXI_MP_RealTime_DashBoard/rawlogs:/app/rawlogs:rw \
  -v /home/Solo_PIXI_MP_RealTime_DashBoard/config:/app/config:rw \
  -v /run/media/nvme0n1p1:/run/media/nvme0n1p1:rw \
  pixi-dashboard
echo "Container started OK"
'@

ssh $remote_host $rebuild

Write-Host ""
Write-Host "Docker container restarted successfully."
Write-Host ""
Write-Host "NOTE: Chromium kiosk will reload when its SSE connection reconnects."
Write-Host "      If the page still shows old JS, manually reload Chromium or"
Write-Host "      restart the kiosk service on the remote machine."
