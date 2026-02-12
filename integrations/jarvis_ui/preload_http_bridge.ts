import { contextBridge } from "electron";
import type { JarvisApi, MissionMode } from "./source_copy/contracts";

const API_BASE = process.env.FRIDAY_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });
  if (!response.ok) {
    throw new Error(`FRIDAY bridge request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

const api: JarvisApi = {
  getState: async () => request("/v1/jarvis/state"),
  runCommand: async (command: string, bypassConfirmation = false) =>
    request("/v1/jarvis/run-command", {
      method: "POST",
      body: JSON.stringify({ command, bypass_confirmation: bypassConfirmation })
    }),
  setMode: async (mode: MissionMode) =>
    request("/v1/jarvis/set-mode", {
      method: "POST",
      body: JSON.stringify({ mode })
    }),
  completeReminder: async (id: string) =>
    request("/v1/jarvis/complete-reminder", {
      method: "POST",
      body: JSON.stringify({ id })
    }),
  replayCommand: async (id: string) =>
    request("/v1/jarvis/replay-command", {
      method: "POST",
      body: JSON.stringify({ id })
    }),
  generateBriefing: async () =>
    request("/v1/jarvis/generate-briefing", {
      method: "POST"
    }),
  reloadPlugins: async () =>
    request("/v1/jarvis/reload-plugins", {
      method: "POST"
    }),
  setAutomationEnabled: async (id: string, enabled: boolean) =>
    request("/v1/jarvis/set-automation-enabled", {
      method: "POST",
      body: JSON.stringify({ id, enabled })
    }),
  setPluginEnabled: async (pluginId: string, enabled: boolean) =>
    request("/v1/jarvis/set-plugin-enabled", {
      method: "POST",
      body: JSON.stringify({ plugin_id: pluginId, enabled })
    }),
  terminateProcess: async (pid: number, bypassConfirmation = false) =>
    request("/v1/jarvis/terminate-process", {
      method: "POST",
      body: JSON.stringify({ pid, bypass_confirmation: bypassConfirmation })
    })
};

contextBridge.exposeInMainWorld("jarvisApi", api);

