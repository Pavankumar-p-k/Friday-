# Dashboard Integration

## Backend

Authenticated dashboard endpoints:

- `POST /v1/dashboard/auth/login`
- `GET /v1/dashboard/stats`
- `GET /v1/dashboard/logs`
- `GET /v1/dashboard/voice-history`
- `GET /v1/dashboard/settings`
- `PUT /v1/dashboard/settings`
- `POST /v1/dashboard/actions/execute`
- `GET /v1/dashboard/actions/history`
- `WS /v1/dashboard/ws?token=...`

Core modules:

- `friday/dashboard_auth.py` for token-based auth
- `friday/dashboard_service.py` for realtime stream, logs, and settings facade
- `friday/storage.py` extended with `voice_history`, `dashboard_logs`, `dashboard_settings`, `action_history`

## Frontend

React dashboard lives in `apps/dashboard` (Vite):

- login and token storage
- realtime stats via websocket snapshot/events
- logs, voice history, action history panels
- settings editor and action execution form

Run:

```powershell
cd apps/dashboard
npm install
npm run dev
```
