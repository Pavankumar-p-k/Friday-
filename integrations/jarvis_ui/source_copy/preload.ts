import { contextBridge, ipcRenderer } from "electron";
import { IPC_CHANNELS, type JarvisApi, type MissionMode } from "../shared/contracts";
import { commandSchema } from "../shared/schemas";

const api: JarvisApi = {
  getState: async () => ipcRenderer.invoke(IPC_CHANNELS.getState),
  runCommand: async (command: string, bypassConfirmation = false) =>
    ipcRenderer.invoke(IPC_CHANNELS.runCommand, commandSchema.parse(command), bypassConfirmation),
  setMode: async (mode: MissionMode) => ipcRenderer.invoke(IPC_CHANNELS.setMode, mode),
  completeReminder: async (id: string) => ipcRenderer.invoke(IPC_CHANNELS.completeReminder, id),
  replayCommand: async (id: string) => ipcRenderer.invoke(IPC_CHANNELS.replayCommand, id),
  generateBriefing: async () => ipcRenderer.invoke(IPC_CHANNELS.generateBriefing),
  reloadPlugins: async () => ipcRenderer.invoke(IPC_CHANNELS.reloadPlugins),
  setAutomationEnabled: async (id: string, enabled: boolean) =>
    ipcRenderer.invoke(IPC_CHANNELS.setAutomationEnabled, id, enabled),
  setPluginEnabled: async (pluginId: string, enabled: boolean) =>
    ipcRenderer.invoke(IPC_CHANNELS.setPluginEnabled, pluginId, enabled),
  terminateProcess: async (pid: number, bypassConfirmation = false) =>
    ipcRenderer.invoke(IPC_CHANNELS.terminateProcess, pid, bypassConfirmation)
};

contextBridge.exposeInMainWorld("jarvisApi", api);
