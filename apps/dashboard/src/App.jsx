import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE =
  import.meta.env.VITE_FRIDAY_API_BASE ||
  (typeof window !== "undefined" ? window.location.origin : "");
const TOKEN_KEY = "friday_dashboard_token";

function getSpeechRecognition() {
  if (typeof window === "undefined") {
    return null;
  }
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function jsonRequest(path, token, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(token),
      ...(options.headers || {})
    }
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed (${response.status})`);
  }
  return response.json();
}

function Login({ onAuthenticated }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("change-me");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const data = await jsonRequest("/v1/dashboard/auth/login", "", {
        method: "POST",
        body: JSON.stringify({ username, password })
      });
      onAuthenticated(data.access_token);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-shell">
      <div className="noise-bg" />
      <form className="login-card" onSubmit={submit}>
        <h1>FRIDAY Control Deck</h1>
        <p>Secure dashboard authentication</p>
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error ? <div className="error">{error}</div> : null}
        <button type="submit" disabled={loading}>
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}

function Stats({ stats }) {
  const items = [
    ["Chats", stats.chat_history_count || 0],
    ["Voice", stats.voice_history_count || 0],
    ["Actions", stats.action_history_count || 0],
    ["Action Success", stats.action_success_count || 0],
    ["Action Fail", stats.action_failure_count || 0],
    ["Logs", stats.log_count || 0]
  ];
  return (
    <section className="panel panel-wide">
      <h2>Assistant Stats</h2>
      <div className="stats-grid">
        {items.map(([label, value]) => (
          <article key={label} className="stat-card">
            <div className="label">{label}</div>
            <div className="value">{value}</div>
          </article>
        ))}
      </div>
    </section>
  );
}

function LiveVoiceConsole({ token, onDone }) {
  const recognitionRef = useRef(null);
  const [sessionId, setSessionId] = useState("live-ui");
  const [mode, setMode] = useState("action");
  const [heard, setHeard] = useState("");
  const [manualText, setManualText] = useState("");
  const [reply, setReply] = useState("");
  const [actions, setActions] = useState([]);
  const [listening, setListening] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [autoSpeak, setAutoSpeak] = useState(true);
  const [error, setError] = useState("");

  const SpeechRecognitionCtor = getSpeechRecognition();
  const supported = Boolean(SpeechRecognitionCtor);

  async function dispatchTranscript(text) {
    const transcript = String(text || "").trim();
    if (!transcript) {
      return;
    }
    setThinking(true);
    setError("");
    try {
      const data = await jsonRequest("/v1/voice/dispatch", token, {
        method: "POST",
        body: JSON.stringify({
          session_id: sessionId,
          transcript,
          context: { mode }
        })
      });
      setHeard(data.transcript || transcript);
      setReply(data.reply || "");
      setActions(data.actions || []);
      if (autoSpeak && typeof window !== "undefined" && window.speechSynthesis && data.reply) {
        const utterance = new window.SpeechSynthesisUtterance(data.reply);
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
      }
      onDone();
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setThinking(false);
    }
  }

  function startListening() {
    if (!SpeechRecognitionCtor || listening) {
      return;
    }
    setError("");
    const recognition = new SpeechRecognitionCtor();
    recognitionRef.current = recognition;
    recognition.lang = "en-US";
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onstart = () => setListening(true);
    recognition.onend = () => setListening(false);
    recognition.onerror = (event) => {
      setListening(false);
      setError(`speech error: ${event.error || "unknown"}`);
    };
    recognition.onresult = (event) => {
      let interim = "";
      const finals = [];
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const chunk = event.results[i][0]?.transcript || "";
        if (event.results[i].isFinal) {
          finals.push(chunk);
        } else {
          interim += chunk;
        }
      }
      if (interim.trim()) {
        setHeard(interim.trim());
      }
      const finalText = finals.join(" ").trim();
      if (finalText) {
        setHeard(finalText);
        dispatchTranscript(finalText);
      }
    };
    recognition.start();
  }

  function stopListening() {
    const recognition = recognitionRef.current;
    if (!recognition) {
      return;
    }
    recognition.stop();
    recognitionRef.current = null;
    setListening(false);
  }

  useEffect(() => {
    return () => stopListening();
  }, []);

  return (
    <section className="panel panel-wide">
      <h2>Live Talking AI (Voice)</h2>
      <div className="voice-controls">
        <label>
          Session
          <input value={sessionId} onChange={(e) => setSessionId(e.target.value)} />
        </label>
        <label>
          Mode
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="action">action</option>
            <option value="chat">chat</option>
            <option value="code">code</option>
          </select>
        </label>
      </div>
      <div className="button-row">
        <button disabled={!supported || listening} onClick={startListening}>
          {listening ? "Listening..." : "Start Mic"}
        </button>
        <button disabled={!listening} onClick={stopListening}>
          Stop Mic
        </button>
        <label className="checkline">
          <input
            type="checkbox"
            checked={autoSpeak}
            onChange={(e) => setAutoSpeak(e.target.checked)}
          />
          Auto speak reply
        </label>
      </div>
      {!supported ? (
        <div className="error">
          Browser speech recognition is not available. Use manual text dispatch below.
        </div>
      ) : null}
      <label>
        Manual command
        <textarea
          value={manualText}
          onChange={(e) => setManualText(e.target.value)}
          placeholder="Type and send if mic support is unavailable"
        />
      </label>
      <button disabled={thinking} onClick={() => dispatchTranscript(manualText)}>
        {thinking ? "Processing..." : "Send Command"}
      </button>
      {error ? <div className="error">{error}</div> : null}
      <div className="voice-live-result">
        <div>
          <strong>Heard:</strong> {heard || "-"}
        </div>
        <div>
          <strong>Reply:</strong> {reply || "-"}
        </div>
        <div className="muted tiny">
          Suggested actions:{" "}
          {actions.length ? actions.map((item) => `${item.tool}(${item.confidence})`).join(", ") : "none"}
        </div>
      </div>
    </section>
  );
}

function Logs({ logs }) {
  return (
    <section className="panel panel-third">
      <h2>Logs</h2>
      <div className="list-scroll">
        {logs.map((item) => (
          <article className={`log-item log-${item.level.toLowerCase()}`} key={item.id}>
            <div className="mono">
              [{item.level}] {item.source}
            </div>
            <div>{item.message}</div>
            <div className="muted">{item.created_at}</div>
          </article>
        ))}
      </div>
    </section>
  );
}

function VoiceHistory({ entries }) {
  return (
    <section className="panel panel-third">
      <h2>Voice Command History</h2>
      <div className="list-scroll">
        {entries.map((item) => (
          <article className="voice-item" key={item.id}>
            <div className="mono">{item.created_at}</div>
            <div>
              <strong>Heard:</strong> {item.transcript}
            </div>
            <div>
              <strong>Reply:</strong> {item.reply}
            </div>
            <div className="muted">
              {item.mode} | {item.llm_backend}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function SettingsEditor({ token, settings, onUpdated }) {
  const [draft, setDraft] = useState(settings);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setDraft(settings);
  }, [settings]);

  async function save() {
    setSaving(true);
    setError("");
    try {
      const data = await jsonRequest("/v1/dashboard/settings", token, {
        method: "PUT",
        body: JSON.stringify({ updates: draft })
      });
      onUpdated(data.settings);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setSaving(false);
    }
  }

  const editable = [
    "auto_execute_low_risk",
    "voice_loop_require_wake_word",
    "voice_loop_poll_interval_sec",
    "voice_loop_mode",
    "request_timeout_sec"
  ];

  return (
    <section className="panel panel-half">
      <h2>Settings</h2>
      <div className="settings-grid">
        {editable.map((key) => (
          <label key={key}>
            {key}
            <input
              value={draft[key] || ""}
              onChange={(e) => setDraft((prev) => ({ ...prev, [key]: e.target.value }))}
            />
          </label>
        ))}
      </div>
      {error ? <div className="error">{error}</div> : null}
      <button disabled={saving} onClick={save}>
        {saving ? "Saving..." : "Save Settings"}
      </button>
    </section>
  );
}

function ActionRunner({ token, onDone }) {
  const [tool, setTool] = useState("reminder");
  const [sessionId, setSessionId] = useState("dashboard-ui");
  const [argsRaw, setArgsRaw] = useState('{"action":"set","note":"review logs"}');
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const presets = [
    {
      label: "Open Notepad",
      tool: "open_app",
      args: { app: "notepad" }
    },
    {
      label: "Play Music",
      tool: "media_control",
      args: { action: "play" }
    },
    {
      label: "Set Reminder",
      tool: "reminder",
      args: { action: "set", note: "follow up in 30 minutes" }
    }
  ];

  async function execute() {
    setRunning(true);
    setError("");
    try {
      const parsed = JSON.parse(argsRaw || "{}");
      const data = await jsonRequest("/v1/dashboard/actions/execute", token, {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, tool, args: parsed })
      });
      setResult(data);
      onDone();
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="panel panel-half">
      <h2>Automation Actions</h2>
      <div className="preset-row">
        {presets.map((item) => (
          <button
            key={item.label}
            onClick={() => {
              setTool(item.tool);
              setArgsRaw(JSON.stringify(item.args));
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      <label>
        Session
        <input value={sessionId} onChange={(e) => setSessionId(e.target.value)} />
      </label>
      <label>
        Tool
        <select value={tool} onChange={(e) => setTool(e.target.value)}>
          <option value="reminder">reminder</option>
          <option value="media_control">media_control</option>
          <option value="open_app">open_app</option>
          <option value="safe_shell">safe_shell</option>
          <option value="code_agent">code_agent</option>
        </select>
      </label>
      <label>
        Args JSON
        <textarea value={argsRaw} onChange={(e) => setArgsRaw(e.target.value)} />
      </label>
      {error ? <div className="error">{error}</div> : null}
      <button disabled={running} onClick={execute}>
        {running ? "Executing..." : "Execute Action"}
      </button>
      {result ? <pre className="result-box">{JSON.stringify(result, null, 2)}</pre> : null}
    </section>
  );
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem(TOKEN_KEY) || "");
  const [stats, setStats] = useState({});
  const [logs, setLogs] = useState([]);
  const [voiceHistory, setVoiceHistory] = useState([]);
  const [actionHistory, setActionHistory] = useState([]);
  const [settings, setSettings] = useState({});
  const [status, setStatus] = useState("idle");

  const wsUrl = useMemo(() => {
    const base = API_BASE.replace("http://", "ws://").replace("https://", "wss://");
    return `${base}/v1/dashboard/ws?token=${encodeURIComponent(token)}`;
  }, [token]);

  useEffect(() => {
    if (!token) {
      return;
    }
    localStorage.setItem(TOKEN_KEY, token);
    setStatus("connected");

    const refresh = async () => {
      const [statsData, logsData, voiceData, settingsData, actionData] = await Promise.all([
        jsonRequest("/v1/dashboard/stats", token),
        jsonRequest("/v1/dashboard/logs?limit=80", token),
        jsonRequest("/v1/dashboard/voice-history?limit=60", token),
        jsonRequest("/v1/dashboard/settings", token),
        jsonRequest("/v1/dashboard/actions/history?limit=60", token)
      ]);
      setStats(statsData);
      setLogs(logsData);
      setVoiceHistory(voiceData);
      setSettings(settingsData.settings || {});
      setActionHistory(actionData);
    };

    refresh().catch(() => setStatus("load-failed"));

    const ws = new WebSocket(wsUrl);
    ws.onopen = () => setStatus("streaming");
    ws.onclose = () => setStatus("disconnected");
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "dashboard.snapshot" && data.stats) {
        setStats(data.stats);
        return;
      }
      if (
        data.type === "dashboard.voice_history.updated" ||
        data.type === "dashboard.action_history.updated" ||
        data.type === "dashboard.action.executed" ||
        data.type === "dashboard.log"
      ) {
        refresh().catch(() => setStatus("load-failed"));
      }
    };

    const timer = setInterval(() => {
      refresh().catch(() => setStatus("load-failed"));
    }, 15000);

    return () => {
      clearInterval(timer);
      ws.close();
    };
  }, [token, wsUrl]);

  if (!token) {
    return (
      <Login
        onAuthenticated={(newToken) => {
          localStorage.setItem(TOKEN_KEY, newToken);
          setToken(newToken);
        }}
      />
    );
  }

  return (
    <div className="page">
      <div className="noise-bg" />
      <header>
        <div>
          <h1>FRIDAY Control Deck</h1>
          <p className="muted">Realtime assistant observability and controls</p>
        </div>
        <div className="header-actions">
          <span className="chip">{status}</span>
          <button
            onClick={() => {
              localStorage.removeItem(TOKEN_KEY);
              setToken("");
            }}
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="dashboard-grid">
        <Stats stats={stats} />
        <LiveVoiceConsole token={token} onDone={() => setStatus("voice-updated")} />
        <ActionRunner token={token} onDone={() => setStatus("refreshing")} />
        <SettingsEditor token={token} settings={settings} onUpdated={setSettings} />
        <Logs logs={logs} />
        <VoiceHistory entries={voiceHistory} />
        <section className="panel panel-third">
          <h2>Action History</h2>
          <div className="list-scroll">
            {actionHistory.map((item) => (
              <article className="voice-item" key={item.id}>
                <div>
                  <strong>{item.tool}</strong> ({item.success ? "ok" : "failed"})
                </div>
                <div className="mono">{item.created_at}</div>
                <div>{item.message}</div>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
