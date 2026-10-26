import { useCallback, useEffect, useMemo, useState } from "react";
import "./styles.css";

const API = import.meta.env.VITE_API_URL || "http://localhost:5000";

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || data.message || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}

const NAV = [
  ["dashboard", "▦", "Dashboard", "OVERVIEW"],
  ["servers", "▤", "Servers"],
  ["monitoring", "◷", "Monitoring"],
  ["ai", "✳", "AI Prediction", "INTELLIGENCE"],
  ["simulation", "⚡", "Failure Simulation"],
  ["recovery", "↻", "Recovery"],
  ["logs", "☷", "Alerts & Logs", "SYSTEM"],
  ["settings", "⚙", "Settings"],
];
const scenarios = [
  ["critical", "Critical failure"],
  ["cpu", "High CPU"],
  ["memory", "High memory"],
  ["latency", "High response time"],
  ["errors", "High error rate"],
  ["unavailable", "Service unavailable"],
];

function Status({ value }) {
  const cls = String(value || "unknown").toLowerCase();
  return <span className={`badge ${cls}`}>{value || "Unknown"}</span>;
}
function MetricBar({ label, value, unit = "%", max = 100 }) {
  const n = Math.max(0, Math.min(Number(value || 0), max));
  return <div className="metric-bar"><div><span>{label}</span><b>{value ?? 0}{unit}</b></div><div className="track"><i style={{ width: `${n / max * 100}%` }} /></div></div>;
}
function Empty({ children = "No records found." }) { return <div className="empty">{children}</div>; }

export default function App() {
  const [user, setUser] = useState(null);
  const [login, setLogin] = useState({ username: "admin", password: "" });
  const [loginError, setLoginError] = useState("");
  const [page, setPage] = useState("dashboard");
  const [dashboard, setDashboard] = useState({});
  const [servers, setServers] = useState([]);
  const [logs, setLogs] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [predictions, setPredictions] = useState([]);
  const [settings, setSettings] = useState({});
  const [modelInfo, setModelInfo] = useState({});
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState(null);
  const [selectedServer, setSelectedServer] = useState("");
  const [scenario, setScenario] = useState("critical");
  const [serverForm, setServerForm] = useState({ name: "", ip_address: "demo://new-service" });
  const [editingServer, setEditingServer] = useState(null);
  const [metricHistory, setMetricHistory] = useState([]);
  const [hostMetrics, setHostMetrics] = useState(null);
  const [filter, setFilter] = useState("");

  const notify = (message, kind = "success") => {
    setNotice({ message, kind });
    window.setTimeout(() => setNotice(null), 4500);
  };

  const refresh = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      const [d, s, l, a, p, st, mi, monitoring] = await Promise.all([
        api("/api/dashboard"), api("/api/servers"), api("/api/recovery-logs"),
        api("/api/alerts"), api("/api/ai/predictions"), api("/api/settings"),
        api("/api/ai/model-info"), api("/api/monitoring/current"),
      ]);
      setDashboard(d); setServers(s); setLogs(l); setAlerts(a);
      setPredictions(p); setSettings(st); setModelInfo(mi); setHostMetrics(monitoring.host_metrics);
      setSelectedServer((old) => old && s.some((x) => String(x.id) === String(old)) ? old : (s[0] ? String(s[0].id) : ""));
    } catch (e) {
      if (e.status === 401) setUser(null);
      else notify(e.message, "error");
    } finally { setLoading(false); }
  }, [user]);

  useEffect(() => {
    api("/api/auth/me").then((data) => setUser(data)).catch(() => setUser(null));
  }, []);
  useEffect(() => {
    if (!user) return;
    refresh();
    const timer = window.setInterval(async () => {
      try {
        await api("/api/monitoring/check", { method: "POST", body: "{}" });
      } catch (error) {
        if (error.status === 401) setUser(null);
      }
      await refresh();
    }, Math.max(5, Number(settings.monitoring_interval_seconds || 5)) * 1000);
    return () => window.clearInterval(timer);
  }, [user, refresh, settings.monitoring_interval_seconds]);

  const selected = useMemo(() => servers.find((s) => String(s.id) === String(selectedServer)), [servers, selectedServer]);
  const filteredServers = useMemo(() => servers.filter((s) => `${s.name} ${s.ip_address} ${s.status}`.toLowerCase().includes(filter.toLowerCase())), [servers, filter]);

  async function doLogin(event) {
    event.preventDefault(); setLoginError("");
    try {
      const data = await api("/api/auth/login", { method: "POST", body: JSON.stringify(login) });
      setUser({ username: data.username }); notify("Signed in successfully");
    } catch (e) { setLoginError(e.message); }
  }
  async function logout() {
    try { await api("/api/auth/logout", { method: "POST", body: "{}" }); } catch {}
    setUser(null); setPage("dashboard");
  }
  async function runAction(key, fn, successMessage) {
    setBusy(key);
    try {
      const result = await fn();
      await refresh();
      notify(successMessage || result.message || "Action completed");
      return result;
    } catch (e) { notify(e.message, "error"); return null; }
    finally { setBusy(""); }
  }
  async function simulate() {
    if (!selectedServer) return notify("Choose a server first", "error");
    await runAction("simulate", () => api(`/api/servers/${selectedServer}/simulate-failure`, {
      method: "POST", body: JSON.stringify({ scenario }),
    }), `Simulation '${scenario}' processed. Check recovery and logs.`);
  }
  async function recover(id, forceFailure = false) {
    return runAction(`recover-${id}`, () => api(`/api/servers/${id}/recover`, {
      method: "POST", body: JSON.stringify({ force_failure: forceFailure }),
    }), forceFailure ? "Recovery-failure test recorded; status should remain Failed." : "Recovery request completed. Health verification result recorded.");
  }
  async function runPrediction(id) {
    const result = await runAction(`predict-${id}`, () => api("/api/ai/predict", {
      method: "POST", body: JSON.stringify({ server_id: Number(id) }),
    }), "AI prediction saved");
    if (result) setPage("ai");
  }
  async function addServer(event) {
    event.preventDefault();
    const result = await runAction("add-server", () => api("/api/servers", {
      method: "POST", body: JSON.stringify(serverForm),
    }), "Service added");
    if (result) setServerForm({ name: "", ip_address: "demo://new-service" });
  }
  async function saveServerEdit(event) {
    event.preventDefault();
    if (!editingServer) return;
    const result = await runAction(`edit-${editingServer.id}`, () => api(`/api/servers/${editingServer.id}`, {
      method: "PUT",
      body: JSON.stringify({ name: editingServer.name, ip_address: editingServer.ip_address }),
    }), "Service updated");
    if (result) setEditingServer(null);
  }
  async function deleteServer(id) {
    if (!window.confirm("Delete this service and its stored metrics, predictions, alerts, and logs?")) return;
    await runAction(`delete-${id}`, () => api(`/api/servers/${id}`, {
      method: "DELETE", body: "{}",
    }), "Service and related records deleted");
  }
  async function loadHistory(id) {
    if (!id) return;
    try { setMetricHistory(await api(`/api/servers/${id}/metrics`)); }
    catch (e) { notify(e.message, "error"); }
  }
  useEffect(() => { if (user && page === "monitoring" && selectedServer) loadHistory(selectedServer); }, [user, page, selectedServer]);

  if (!user) return <div className="login-shell"><form className="login-card" onSubmit={doLogin}>
    <div className="brand-mark">☁</div><p className="eyebrow">INFRASTRUCTURE INTELLIGENCE</p>
    <h1>Self-Healing Cloud</h1><p className="muted">Sign in to your local project dashboard.</p>
    <label>Username<input autoComplete="username" value={login.username} onChange={(e) => setLogin({ ...login, username: e.target.value })} required /></label>
    <label>Password<input type="password" autoComplete="current-password" value={login.password} onChange={(e) => setLogin({ ...login, password: e.target.value })} required /></label>
    {loginError && <div className="notice error">{loginError}</div>}
    <button className="btn primary wide" type="submit">Sign in securely</button>
    <p className="login-hint">Local demo default: <b>admin</b> / <b>ChangeMe123!</b><br />Change the password with the ADMIN_PASSWORD environment variable before sharing or deployment.</p>
  </form></div>;

  return <div className="layout">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">☁</div><div><b>Self-Healing</b><small>Cloud Infrastructure</small></div></div>
      <div className="nav-label">WORKSPACE</div>
      {NAV.map(([key, icon, label, group], index) => <div key={key}>
        {group && <div className="nav-label">{group}</div>}
        <button className={`nav-link ${page === key ? "active" : ""}`} onClick={() => setPage(key)}><span className="nav-icon">{icon}</span>{label}</button>
      </div>)}
      <div className="sidebar-bottom"><span className="live-dot" /><div><b>Demo environment</b><small>Metrics are simulated</small></div></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div><p className="eyebrow">AI OPERATIONS CENTER</p><h1>{NAV.find((x) => x[0] === page)?.[2] || "Dashboard"}</h1></div><div className="top-actions"><span className="live-pill"><i /> API connected</span><button className="btn secondary" onClick={refresh} disabled={loading}>{loading ? "Refreshing…" : "↻ Refresh"}</button><button className="avatar" title="Sign out" onClick={logout}>{(user.username || "A")[0].toUpperCase()}</button></div></header>
      {notice && <div className={`notice ${notice.kind}`}>{notice.kind === "success" ? "✓" : "⚠"} {notice.message}<button onClick={() => setNotice(null)}>×</button></div>}
      <div className="page-content">
        {page === "dashboard" && <Dashboard dashboard={dashboard} servers={servers} logs={logs} onGo={setPage} onRecover={recover} busy={busy} onSimulate={() => setPage("simulation")} />}
        {page === "servers" && <section className="panel">
          <div className="panel-heading"><div><h2>Monitored services</h2><p>Service records in the SQLite database. Demo values are not cloud telemetry.</p></div><input className="search-input" placeholder="Search services…" value={filter} onChange={(e) => setFilter(e.target.value)} /></div>
          <div className="table-wrap"><table><thead><tr><th>Service</th><th>CPU</th><th>Memory</th><th>Response</th><th>Status</th><th>AI risk</th><th>Actions</th></tr></thead><tbody>{filteredServers.map((s) => <tr key={s.id}><td><b>{s.name}</b><small className="subcell">{s.ip_address}</small></td><td>{s.cpu_usage}%</td><td>{s.memory_usage}%</td><td>{s.response_time} ms</td><td><Status value={s.status} /></td><td><Status value={s.ai_risk} /></td><td className="actions"><button className="btn tiny secondary" onClick={() => { setSelectedServer(String(s.id)); setPage("ai"); }}>Predict</button><button className="btn tiny primary" disabled={busy === `recover-${s.id}`} onClick={() => recover(s.id)}>Recover</button><button className="btn tiny secondary" onClick={() => setEditingServer({ id: s.id, name: s.name, ip_address: s.ip_address })}>Edit</button><button className="btn tiny danger-outline" disabled={busy === `delete-${s.id}`} onClick={() => deleteServer(s.id)}>Delete</button></td></tr>)}</tbody></table></div>
          {editingServer && <form className="inline-form edit-form" onSubmit={saveServerEdit}><h3>Edit service #{editingServer.id}</h3><input aria-label="Edit service name" placeholder="Service name" value={editingServer.name} onChange={(e) => setEditingServer({ ...editingServer, name: e.target.value })} required maxLength={100} /><input aria-label="Edit service endpoint" placeholder="Identifier / endpoint" value={editingServer.ip_address} onChange={(e) => setEditingServer({ ...editingServer, ip_address: e.target.value })} required maxLength={500} /><button className="btn primary" disabled={busy === `edit-${editingServer.id}`}>Save changes</button><button type="button" className="btn secondary" onClick={() => setEditingServer(null)}>Cancel</button></form>}
          <form className="inline-form" onSubmit={addServer}><h3>Add monitored service</h3><input placeholder="Service name" value={serverForm.name} onChange={(e) => setServerForm({ ...serverForm, name: e.target.value })} required maxLength={100} /><input placeholder="Identifier / endpoint" value={serverForm.ip_address} onChange={(e) => setServerForm({ ...serverForm, ip_address: e.target.value })} required maxLength={500} /><button className="btn primary" disabled={busy === "add-server"}>+ Add service</button></form>
          {servers.length === 0 && <Empty>No services yet. Add one or refresh.</Empty>}
        </section>}
        {page === "monitoring" && <><section className="panel"><div className="panel-heading"><div><h2>Backend host health</h2><p>Actual resource usage of the computer running Flask; not remote cloud-server metrics.</p></div><span className={`badge ${hostMetrics?.available ? "healthy" : "warning"}`}>{hostMetrics?.available ? "Live host metrics" : "Unavailable"}</span></div>{hostMetrics?.available ? <div className="metric-grid"><MetricBar label="Host CPU" value={hostMetrics.cpu_percent} /><MetricBar label="Host memory" value={hostMetrics.memory_percent} /><MetricBar label="Host disk" value={hostMetrics.disk_percent} /></div> : <p className="muted">{hostMetrics?.note || "Host metrics are unavailable. Install the backend requirements and refresh."}</p>}<p className="muted">{hostMetrics?.note || "Host metrics are collected locally."}</p></section><div className="section-intro"><h2>Service metrics history</h2><p>HTTP(S) endpoints are actively probed; other demo service records use simulated metrics.</p><div className="field-row"><label>Service<select value={selectedServer} onChange={(e) => setSelectedServer(e.target.value)}>{servers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label><button className="btn secondary" onClick={() => loadHistory(selectedServer)}>Load history</button><button className="btn primary" onClick={() => runAction("monitor-check", () => api("/api/monitoring/check", { method: "POST", body: "{}" }), "Monitoring check complete")}>Run monitoring check</button></div></div>
          {selected && <div className="metric-grid"><MetricBar label="CPU usage" value={selected.cpu_usage} /><MetricBar label="Memory usage" value={selected.memory_usage} /><MetricBar label="Disk usage" value={selected.disk_usage} /><MetricBar label="Response time" value={selected.response_time} unit=" ms" max={5000} /><MetricBar label="Error rate" value={selected.error_rate} unit="%" /></div>}
          <div className="chart-grid"><MiniChart title="CPU usage (%)" values={metricHistory.map((m) => m.cpu)} color="#3278e7" /><MiniChart title="Memory usage (%)" values={metricHistory.map((m) => m.memory)} color="#8b5cf6" /><MiniChart title="Response time (ms)" values={metricHistory.map((m) => m.response_time)} color="#18a675" /></div>
          <section className="panel"><div className="panel-heading"><div><h2>Recorded samples</h2><p>Most recent 100 records for the selected service.</p></div></div><div className="table-wrap"><table><thead><tr><th>Timestamp</th><th>CPU</th><th>Memory</th><th>Disk</th><th>Response</th><th>Error rate</th></tr></thead><tbody>{metricHistory.slice().reverse().map((m) => <tr key={m.id}><td>{formatDate(m.timestamp)}</td><td>{m.cpu}%</td><td>{m.memory}%</td><td>{m.disk}%</td><td>{m.response_time} ms</td><td>{m.error_rate}%</td></tr>)}</tbody></table></div>{!metricHistory.length && <Empty>Choose a service and load history.</Empty>}</section>
        </>}
        {page === "ai" && <><div className="section-intro"><h2>Failure risk assessment</h2><p>Random Forest model trained on generated synthetic examples. Predictions are estimates, not guarantees.</p><div className="field-row"><label>Service<select value={selectedServer} onChange={(e) => setSelectedServer(e.target.value)}>{servers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label><button className="btn primary" disabled={!selected || busy.startsWith("predict-")} onClick={() => selected && runPrediction(selected.id)}>{busy.startsWith("predict-") ? "Predicting…" : "Run AI prediction"}</button></div></div>
          {selected && <div className="ai-layout"><section className="panel"><div className="panel-heading"><div><h2>{selected.name}</h2><p>Current input features</p></div><Status value={selected.ai_risk} /></div><div className="metric-grid"><MetricBar label="CPU usage" value={selected.cpu_usage} /><MetricBar label="Memory usage" value={selected.memory_usage} /><MetricBar label="Disk usage" value={selected.disk_usage} /><MetricBar label="Response time" value={selected.response_time} unit=" ms" max={5000} /><MetricBar label="Error rate" value={selected.error_rate} /></div></section><section className="risk-panel"><p className="eyebrow">FAILURE PROBABILITY</p><div className="risk-number">{selected.failure_probability}%</div><div className="track risk-track"><i style={{ width: `${Math.min(100, selected.failure_probability)}%` }} /></div><Status value={selected.ai_risk} /><p className="muted">Model: RandomForestClassifier</p><p className="muted">Data source: synthetic training data</p></section></div>}
          <section className="panel"><div className="panel-heading"><div><h2>Model evaluation</h2><p>Evaluation reflects synthetic labels only; not real incident performance.</p></div></div><div className="metric-grid evaluation-grid">{Object.entries(modelInfo.evaluation || {}).filter(([k, v]) => ["accuracy","precision","recall","f1_score","rows","test_rows"].includes(k)).map(([k, v]) => <div className="metric-tile" key={k}><span>{k.replaceAll("_", " ")}</span><b>{typeof v === "number" && v <= 1 ? `${(v * 100).toFixed(1)}%` : v}</b></div>)}</div><p className="muted">{modelInfo.evaluation?.warning || "Train model to generate an evaluation report."}</p></section>
          <section className="panel"><div className="panel-heading"><div><h2>Failure-risk history</h2><p>Stored predictions for the selected service</p></div></div><MiniChart title="Predicted failure probability (%)" values={predictions.filter((p) => String(p.server_id) === String(selectedServer)).slice().reverse().map((p) => p.probability)} color="#dc4053" max={100} /></section>
          <section className="panel"><div className="panel-heading"><div><h2>Prediction history</h2><p>Persisted AI prediction records</p></div></div><SimpleTable rows={predictions} columns={[["created_at","Time"],["server_id","Service ID"],["probability","Probability (%)"],["risk","Risk"],["explanation","Explanation"]]} /></section>
        </>}
        {page === "simulation" && <section className="panel"><div className="panel-heading"><div><h2>Failure simulation lab</h2><p>Changes backend metrics for a demo service. This does not stop a real server.</p></div><span className="badge warning">SIMULATION ONLY</span></div><div className="field-row"><label>Target service<select value={selectedServer} onChange={(e) => setSelectedServer(e.target.value)}>{servers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label><label>Failure scenario<select value={scenario} onChange={(e) => setScenario(e.target.value)}>{scenarios.map(([v, label]) => <option value={v} key={v}>{label}</option>)}</select></label></div><div className="scenario-grid">{scenarios.map(([value, label]) => <button key={value} className={`scenario-card ${scenario === value ? "chosen" : ""}`} onClick={() => setScenario(value)}><span>⚡</span><b>{label}</b><small>{value === "critical" ? "Multiple critical metrics" : value === "cpu" ? "CPU reaches 99%" : value === "memory" ? "Memory reaches 99%" : value === "latency" ? "Response time reaches 3.5 seconds" : value === "errors" ? "Error rate reaches 35%" : "All metrics become critical"}</small></button>)}</div><button className="btn danger" disabled={!selected || busy === "simulate"} onClick={simulate}>{busy === "simulate" ? "Running simulation…" : "Trigger selected failure"}</button><div className="callout"><b>Workflow</b><p>Scenario metrics → failure alert → AI prediction → optional simulated recovery → metric-based health verification → persisted logs.</p><p>When automatic recovery is enabled, the demo adapter restores simulated metrics. It does not restart a real cloud instance or operating-system service.</p></div></section>}
        {page === "recovery" && <><section className="panel"><div className="panel-heading"><div><h2>Recovery controls</h2><p>All recovery actions use the safe simulated adapter by default.</p></div><span className="badge info">Controlled demo</span></div><div className="recovery-target"><label>Target service<select value={selectedServer} onChange={(e) => setSelectedServer(e.target.value)}>{servers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>{selected && <div><span className="muted">Current status</span><Status value={selected.status} /></div>}</div><div className="button-row"><button className="btn primary" disabled={!selected || busy === `recover-${selected?.id}`} onClick={() => selected && recover(selected.id)}>{busy === `recover-${selected?.id}` ? "Recovery in progress…" : "Start recovery"}</button><button className="btn danger-outline" disabled={!selected || busy === `recover-${selected?.id}`} onClick={() => selected && recover(selected.id, true)}>Test failed recovery path</button></div>{selected && busy === `recover-${selected.id}` && <div className="progress-callout"><span className="spinner" /> Recovery action running. The backend is recording the attempt and checking service health…</div>}<div className="callout"><b>Health verification rule</b><p>A service is marked Healthy only if post-recovery metrics pass configured thresholds. The failed-recovery test leaves the service Failed and records an alert.</p></div></section><section className="panel"><div className="panel-heading"><div><h2>Recovery activity</h2><p>Newest first</p></div></div><SimpleTable rows={logs} columns={[["timestamp","Time"],["server_id","Service ID"],["event","Event"],["status","Result"]]} /></section></>}
        {page === "logs" && <><section className="panel"><div className="panel-heading"><div><h2>Alerts and incidents</h2><p>Unresolved alerts are deduplicated by service and alert title.</p></div></div><div className="table-wrap"><table><thead><tr><th>Time</th><th>Service</th><th>Severity</th><th>Alert</th><th>Status</th><th>Action</th></tr></thead><tbody>{alerts.map((a) => <tr key={a.id}><td>{formatDate(a.created_at)}</td><td>{a.server_id}</td><td><Status value={a.severity} /></td><td><b>{a.title}</b><small className="subcell">{a.message}</small></td><td>{a.resolved ? "Resolved" : "Open"}</td><td>{!a.resolved && <button className="btn tiny secondary" onClick={() => runAction(`alert-${a.id}`, () => api(`/api/alerts/${a.id}/resolve`, { method: "PATCH", body: "{}" }), "Alert resolved")}>Resolve</button>}</td></tr>)}</tbody></table></div>{!alerts.length && <Empty>No alerts have been generated yet.</Empty>}</section><section className="panel"><div className="panel-heading"><div><h2>System / recovery logs</h2><p>Persisted backend events</p></div></div><SimpleTable rows={logs} columns={[["timestamp","Time"],["server_id","Service ID"],["event","Event"],["status","Status"]]} /></section></>}
        {page === "settings" && <Settings settings={settings} busy={busy} onSave={(values) => runAction("settings", () => api("/api/settings", { method: "PUT", body: JSON.stringify(values) }), "Settings saved to SQLite")} />}
      </div>
      <footer><span>AI-Based Self-Healing Cloud Infrastructure</span><span>Local demo build · simulated telemetry</span></footer>
    </main>
  </div>;
}

function Dashboard({ dashboard, servers, logs, onGo, onRecover, busy, onSimulate }) {
  const cards = [
    ["Total services", dashboard.total_servers ?? 0, "▤", "blue"],
    ["Healthy", dashboard.healthy_servers ?? 0, "✓", "green"],
    ["Warnings", dashboard.warning_servers ?? 0, "!", "amber"],
    ["Failed", dashboard.failed_servers ?? 0, "×", "red"],
    ["Successful recoveries", dashboard.successful_recoveries ?? 0, "↻", "purple"],
  ];
  return <>
    <div className="stats-grid">{cards.map(([label, value, icon, color]) => <div className="stat-card" key={label}><div className={`stat-icon ${color}`}>{icon}</div><div><span>{label}</span><b>{value}</b></div></div>)}</div>
    <div className="dashboard-grid"><section className="panel span-two"><div className="panel-heading"><div><h2>Service health</h2><p>Latest stored metrics and AI assessment</p></div><button className="btn secondary" onClick={() => onGo("servers")}>View all services →</button></div><div className="table-wrap"><table><thead><tr><th>Service</th><th>CPU</th><th>Memory</th><th>Response</th><th>Status</th><th>Risk</th><th /></tr></thead><tbody>{servers.slice(0, 8).map((s) => <tr key={s.id}><td><b>{s.name}</b><small className="subcell">{s.ip_address}</small></td><td>{s.cpu_usage}%</td><td>{s.memory_usage}%</td><td>{s.response_time} ms</td><td><Status value={s.status} /></td><td><Status value={s.ai_risk} /></td><td><button className="btn tiny secondary" disabled={busy === `recover-${s.id}`} onClick={() => onRecover(s.id)}>Recover</button></td></tr>)}</tbody></table></div>{!servers.length && <Empty />}</section>
    <section className="panel"><div className="panel-heading"><div><h2>Infrastructure snapshot</h2><p>Average across demo services</p></div></div><div className="avg-metrics">{["cpu_usage","memory_usage","disk_usage"].map((key) => { const avg = servers.length ? Math.round(servers.reduce((a,s)=>a+Number(s[key]||0),0)/servers.length) : 0; return <MetricBar key={key} label={key.replace("_usage","").replace("_"," ")} value={avg} />; })}</div><div className="callout"><b>Open alerts</b><p>{dashboard.open_alerts ?? 0} open · {dashboard.critical_alerts ?? 0} critical</p><button className="btn secondary" onClick={() => onGo("logs")}>Review alerts</button></div></section>
    <section className="panel"><div className="panel-heading"><div><h2>Recent activity</h2><p>Latest recovery and incident events</p></div><button className="btn tiny secondary" onClick={() => onGo("recovery")}>All logs</button></div>{logs.slice(0, 6).map((l) => <div className="activity" key={l.id}><span className={`activity-dot ${String(l.status).toLowerCase()}`} /><div><b>{l.event}</b><small>Service #{l.server_id} · {formatDate(l.timestamp)}</small></div><Status value={l.status} /></div>)}{!logs.length && <Empty>No activity yet.</Empty>}</section>
    <section className="panel"><div className="panel-heading"><div><h2>Quick actions</h2><p>Test the self-healing workflow</p></div></div><div className="quick-actions"><button className="quick-action" onClick={() => onGo("ai")}><span>✳</span><b>AI prediction</b><small>Assess failure risk</small></button><button className="quick-action" onClick={onSimulate}><span>⚡</span><b>Simulate failure</b><small>Trigger a demo incident</small></button><button className="quick-action" onClick={() => onGo("settings")}><span>⚙</span><b>Recovery policies</b><small>Configure thresholds</small></button></div></section></div>
  </>;
}
function SimpleTable({ rows, columns }) {
  if (!rows?.length) return <Empty />;
  return <div className="table-wrap"><table><thead><tr>{columns.map(([key,label]) => <th key={key}>{label}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={row.id ?? i}>{columns.map(([key]) => <td key={key}>{key.includes("timestamp") || key === "created_at" ? formatDate(row[key]) : key === "probability" ? `${Number(row[key]).toFixed(2)}%` : key === "risk" || key === "status" ? <Status value={row[key]} /> : key === "explanation" || key === "event" ? <span className="wrap-cell">{row[key]}</span> : String(row[key] ?? "—")}</td>)}</tr>)}</tbody></table></div>;
}
function MiniChart({ title, values = [], color = "#3278e7", max: fixedMax }) {
  const recent = values.slice(-30).map((v) => Number(v) || 0);
  const maxValue = fixedMax || Math.max(1, ...recent) * 1.1;
  const points = recent.length > 1
    ? recent.map((v, i) => `${(i / (recent.length - 1)) * 300},${90 - (Math.min(maxValue, Math.max(0, v)) / maxValue) * 75}`).join(" ")
    : recent.length === 1 ? `0,${90 - (Math.min(maxValue, Math.max(0, recent[0])) / maxValue) * 75} 300,${90 - (Math.min(maxValue, Math.max(0, recent[0])) / maxValue) * 75}` : "0,82 300,82";
  return <div className="chart-card"><div className="chart-title"><b>{title}</b><span>{recent.length ? `Latest: ${recent[recent.length - 1]}` : "No history yet"}</span></div><svg viewBox="0 0 300 100" role="img" aria-label={title} preserveAspectRatio="none"><line x1="0" y1="20" x2="300" y2="20" stroke="#edf1f6" /><line x1="0" y1="55" x2="300" y2="55" stroke="#edf1f6" /><line x1="0" y1="90" x2="300" y2="90" stroke="#edf1f6" /><polyline points={points} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" /></svg><div className="chart-foot"><span>{recent.length} samples</span><span>Most recent 30</span></div></div>;
}

function Settings({ settings, busy, onSave }) {
  const [draft, setDraft] = useState(settings);
  const settingsSignature = JSON.stringify(settings);
  useEffect(() => setDraft(settings), [settingsSignature]);
  const numeric = [
    ["monitoring_interval_seconds","Refresh interval (seconds)"],
    ["cpu_warning","CPU warning threshold (%)"], ["memory_warning","Memory warning threshold (%)"],
    ["disk_warning","Disk warning threshold (%)"], ["response_warning_ms","Response-time warning (ms)"],
    ["error_warning_percent","Error-rate warning (%)"], ["cpu_critical","CPU critical threshold (%)"],
    ["memory_critical","Memory critical threshold (%)"], ["disk_critical","Disk critical threshold (%)"],
    ["response_critical_ms","Response-time critical (ms)"], ["error_critical_percent","Error-rate critical (%)"],
  ];
  return <section className="panel settings-panel"><div className="panel-heading"><div><h2>Monitoring and recovery policy</h2><p>Settings are persisted in SQLite and validated by the API.</p></div></div><label className="toggle-row"><span><b>Automatic simulated recovery</b><small>Restore demo metrics after a critical event and verify them.</small></span><input type="checkbox" checked={Boolean(draft.auto_recovery_enabled)} onChange={(e) => setDraft({ ...draft, auto_recovery_enabled: e.target.checked })} /></label><div className="settings-grid">{numeric.map(([key,label]) => <label key={key}>{label}<input type="number" min="0" max={key.includes("interval") ? 3600 : 60000} value={draft[key] ?? 0} onChange={(e) => setDraft({ ...draft, [key]: Number(e.target.value) })} /></label>)}</div><div className="button-row"><button className="btn primary" disabled={busy === "settings"} onClick={() => onSave(draft)}>{busy === "settings" ? "Saving…" : "Save settings"}</button><button className="btn secondary" onClick={() => setDraft(settings)}>Reset changes</button></div></section>;
}
function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
