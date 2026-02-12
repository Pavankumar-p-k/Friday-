export type MissionMode = "work" | "gaming" | "focus" | "night";

export type AgentType = "scheduler" | "coder" | "media" | "sysadmin";

export type PermissionLevel = "safe" | "confirm" | "admin";

export type IntentType =
  | "open_app"
  | "play_media"
  | "pause_media"
  | "set_reminder"
  | "set_alarm"
  | "run_routine"
  | "list_reminders"
  | "system_info"
  | "unknown";

export interface TelemetrySnapshot {
  cpuPercent: number;
  memoryUsedMb: number;
  memoryTotalMb: number;
  uptimeSec: number;
  networkRxKb: number;
  networkTxKb: number;
  topProcesses: ProcessInfo[];
  timestampIso: string;
}

export interface ProcessInfo {
  pid: number;
  name: string;
  memoryMb: number;
  cpuPercent?: number;
}

export interface ReminderItem {
  id: string;
  title: string;
  note?: string;
  dueAtIso: string;
  status: "pending" | "done" | "missed";
  createdAtIso: string;
}

export interface AlarmItem {
  id: string;
  label: string;
  triggerAtIso: string;
  enabled: boolean;
  createdAtIso: string;
}

export interface RoutineStep {
  id: string;
  command: string;
  description?: string;
}

export interface RoutineItem {
  id: string;
  name: string;
  steps: RoutineStep[];
  createdAtIso: string;
  lastRunAtIso?: string;
}

export interface MemoryProfile {
  preferredApps: string[];
  commonCommands: string[];
  lastMode: MissionMode;
  updatedAtIso: string;
}

export interface SuggestionItem {
  id: string;
  text: string;
  reason: string;
  createdAtIso: string;
}

export interface CommandRecord {
  id: string;
  command: string;
  intent: IntentType;
  success: boolean;
  resultMessage: string;
  timestampIso: string;
}

export interface ProcessNode {
  id: string;
  name: string;
  children: ProcessNode[];
  pid?: number;
}

export interface AutomationCondition {
  type: "time_range" | "contains_command" | "mode_is";
  value: string;
}

export interface AutomationAction {
  type: "run_command" | "show_hint" | "set_mode";
  value: string;
}

export interface AutomationRule {
  id: string;
  name: string;
  enabled: boolean;
  conditions: AutomationCondition[];
  actions: AutomationAction[];
  createdAtIso: string;
}

export interface PluginManifest {
  id: string;
  name: string;
  version: string;
  description: string;
  entryCommand: string;
  permissionLevel: PermissionLevel;
}

export interface PluginState {
  manifest: PluginManifest;
  enabled: boolean;
  installedAtIso: string;
}

export interface MorningBriefing {
  headline: string;
  remindersToday: ReminderItem[];
  suggestedFocus: string;
  generatedAtIso: string;
}

export interface ParsedIntent {
  type: IntentType;
  confidence: number;
  entities: Record<string, string>;
}

export interface ActionRequest {
  rawCommand: string;
  parsedIntent: ParsedIntent;
  requiredPermission: PermissionLevel;
}

export interface ActionResult {
  ok: boolean;
  message: string;
  data?: unknown;
  needsConfirmation?: boolean;
}

export interface AssistantState {
  mode: MissionMode;
  telemetry: TelemetrySnapshot;
  reminders: ReminderItem[];
  alarms: AlarmItem[];
  routines: RoutineItem[];
  memory: MemoryProfile;
  suggestions: SuggestionItem[];
  commandHistory: CommandRecord[];
  automations: AutomationRule[];
  plugins: PluginState[];
}

export interface CommandResponse {
  result: ActionResult;
  state: AssistantState;
}

export interface JarvisApi {
  getState: () => Promise<AssistantState>;
  runCommand: (command: string, bypassConfirmation?: boolean) => Promise<CommandResponse>;
  setMode: (mode: MissionMode) => Promise<AssistantState>;
  completeReminder: (id: string) => Promise<AssistantState>;
  replayCommand: (id: string) => Promise<CommandResponse>;
  generateBriefing: () => Promise<MorningBriefing>;
  reloadPlugins: () => Promise<AssistantState>;
  setAutomationEnabled: (id: string, enabled: boolean) => Promise<AssistantState>;
  setPluginEnabled: (pluginId: string, enabled: boolean) => Promise<AssistantState>;
  terminateProcess: (pid: number, bypassConfirmation?: boolean) => Promise<CommandResponse>;
}

export const IPC_CHANNELS = {
  getState: "jarvis:get-state",
  runCommand: "jarvis:run-command",
  setMode: "jarvis:set-mode",
  completeReminder: "jarvis:complete-reminder",
  replayCommand: "jarvis:replay-command",
  generateBriefing: "jarvis:generate-briefing",
  reloadPlugins: "jarvis:reload-plugins",
  setAutomationEnabled: "jarvis:set-automation-enabled",
  setPluginEnabled: "jarvis:set-plugin-enabled",
  terminateProcess: "jarvis:terminate-process"
} as const;
