# FRIDAY Dashboard (React)

Frontend dashboard for:

- authenticated access
- realtime stats and event stream
- logs + voice command history
- settings management
- assistant action execution

## Run

```powershell
cd apps/dashboard
npm install
npm run dev
```

Set API base (optional):

```powershell
$env:VITE_FRIDAY_API_BASE="http://127.0.0.1:8000"
```

Local dev proxy target (used when `VITE_FRIDAY_API_BASE` is not set):

```powershell
$env:VITE_BACKEND_PROXY_TARGET="http://127.0.0.1:8000"
```
