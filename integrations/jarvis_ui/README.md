# Jarvis UI Integration

This folder integrates your existing Desktop `jarvis` UI with the `Friday-` backend without modifying the original `C:\Users\Pavan\Desktop\jarvis` folder.

## What is reused from Desktop Jarvis

Copied from `C:\Users\Pavan\Desktop\jarvis` into `integrations/jarvis_ui/source_copy`:

- `contracts.ts`
- `schemas.ts`
- `preload.ts`
- `useMicLevel.ts`
- `VoiceOrb.tsx`

These are copied as source references only. The original Jarvis folder is not modified.

## Bridge preload

`preload_http_bridge.ts` implements the same `window.jarvisApi` contract but routes calls to FRIDAY backend endpoints:

- `/v1/jarvis/state`
- `/v1/jarvis/run-command`
- `/v1/jarvis/set-mode`
- `/v1/jarvis/complete-reminder`
- `/v1/jarvis/replay-command`
- `/v1/jarvis/generate-briefing`
- `/v1/jarvis/reload-plugins`
- `/v1/jarvis/set-automation-enabled`
- `/v1/jarvis/set-plugin-enabled`
- `/v1/jarvis/terminate-process`

## Prepare runnable bridge copy

```powershell
cd C:\Users\Pavan\AppData\Roaming\Friday-
.\scripts\prepare_jarvis_ui_bridge.ps1
```

This creates `apps/jarvis-bridge` as a copied workspace and replaces preload with HTTP bridge logic.

