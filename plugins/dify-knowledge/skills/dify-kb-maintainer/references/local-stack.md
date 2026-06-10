# Local Dify Stack

## Common Commands

Start:
```sh
cd /Users/hujiewei/apps/dify
colima start
docker compose -f docker/docker-compose.yaml --env-file docker/.env up -d
```

Status:
```sh
docker compose -f docker/docker-compose.yaml --env-file docker/.env ps --status running
curl -sS -I --max-time 10 http://localhost:8080
```

Restart API after local container work:
```sh
docker compose -f docker/docker-compose.yaml --env-file docker/.env restart api
```

## URL Checks

Check current LAN IP:
```sh
ipconfig getifaddr en0 2>/dev/null || true
ipconfig getifaddr en1 2>/dev/null || true
```

Check URL envs:
```sh
rg -n '^(CONSOLE_API_URL|APP_API_URL|APP_WEB_URL|CONSOLE_WEB_URL|SERVICE_API_URL|FILES_URL|NEXT_PUBLIC_SOCKET_URL)=' docker/.env
```
