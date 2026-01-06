import { useEffect, useMemo, useState } from "react";

type Message = {
  device_id: string;
  ts: string;
  field_a: number;
  field_b: number;
  battery: number;
  seq: number;
  meta?: Record<string, string>;
};

type Stats = {
  messages_total: number;
  latest: Message | null;
};

type Alert = {
  id: string;
  device_id: string;
  rule_id: string;
  rule_type: string;
  triggered_at: string;
  payload: any;
  count: number;
  severity: number;
};

type Device = {
  _id: string;
  name: string;
  description?: string;
  external_id?: string | null;
  created_at?: string;
  created_by?: string;
};

const apiBase = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function fetchJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${apiBase}${path}`, options);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      if (body.error) msg = body.error;
    } catch (_) {
      /* ignore */
    }
    throw new Error(msg || `Request failed: ${res.status}`);
  }
  return res.json();
}

function formatTs(ts?: string) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [deviceFilter, setDeviceFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [token, setToken] = useState<string | null>(() => localStorage.getItem("token"));
  const [userEmail, setUserEmail] = useState<string | null>(() => localStorage.getItem("email"));
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");

  const [devices, setDevices] = useState<Device[]>([]);
  const [deviceName, setDeviceName] = useState("");
  const [deviceDesc, setDeviceDesc] = useState("");
  const [deviceExternal, setDeviceExternal] = useState("");
  const [deviceError, setDeviceError] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const [alertsOpen, setAlertsOpen] = useState(false);

  const headers = useMemo(() => {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (token) h["Authorization"] = `Bearer ${token}`;
    return h;
  }, [token]);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (deviceFilter.trim()) params.set("device_id", deviceFilter.trim());
    params.set("limit", "50");
    return params.toString();
  }, [deviceFilter]);

  const loadMessages = async () => {
    if (!token) {
      setError("Login to see messages");
      setMessages([]);
      setStats(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [msgs, st] = await Promise.all([
        fetchJson<Message[]>(`/messages?${query}`, { headers }),
        fetchJson<Stats>("/stats", { headers }),
      ]);
      setMessages(msgs);
      setStats(st);
    } catch (e: any) {
      setError(e.message || "Error");
    } finally {
      setLoading(false);
    }
  };

  const loadDevices = async () => {
    if (!token) return;
    setDeviceError(null);
    try {
      const list = await fetchJson<Device[]>("/devices", { headers });
      setDevices(list);
    } catch (e: any) {
      setDeviceError(e.message || "Error");
    }
  };

  const loadAlerts = async () => {
    if (!token) return;
    setAlertsError(null);
    try {
      const list = await fetchJson<Alert[]>("/alerts", { headers });
      setAlerts(list);
    } catch (e: any) {
      setAlertsError(e.message || "Error");
    }
  };

  const handleAuth = async (mode: "login" | "register") => {
    setAuthError(null);
    try {
      const body = { email: authEmail, password: authPassword };
      const path = mode === "login" ? "/auth/login" : "/auth/register";
      const res = await fetchJson<{ token: string; email: string }>(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setToken(res.token);
      setUserEmail(res.email);
      localStorage.setItem("token", res.token);
      localStorage.setItem("email", res.email);
      setAuthPassword("");
      await Promise.all([loadDevices(), loadMessages(), loadAlerts()]);
    } catch (e: any) {
      setAuthError(e.message || "Auth error");
    }
  };

  const handleLogout = () => {
    setToken(null);
    setUserEmail(null);
    localStorage.removeItem("token");
    localStorage.removeItem("email");
    setDevices([]);
  };

  const addDevice = async () => {
    setDeviceError(null);
    if (!token) return setDeviceError("Login first");
    try {
      const payload = {
        name: deviceName,
        description: deviceDesc,
        external_id: deviceExternal || undefined,
      };
      await fetchJson<Device>("/devices", {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });
      setDeviceName("");
      setDeviceDesc("");
      setDeviceExternal("");
      loadDevices();
    } catch (e: any) {
      setDeviceError(e.message || "Error");
    }
  };

  const deleteDevice = async (id: string) => {
    setDeviceError(null);
    if (!token) return setDeviceError("Login first");
    try {
      await fetchJson(`/devices/${id}`, { method: "DELETE", headers });
      setDevices((d) => d.filter((x) => x._id !== id));
    } catch (e: any) {
      setDeviceError(e.message || "Error");
    }
  };

  useEffect(() => {
    loadMessages();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  useEffect(() => {
    if (token) loadDevices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    if (token) loadAlerts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <div className="page">
      <header>
        <div>
          <h1>IoT Dashboard</h1>
          <p className="muted">API: {apiBase}</p>
        </div>
        <div className="actions auth-block">
          <input
            placeholder="email"
            value={authEmail}
            onChange={(e) => setAuthEmail(e.target.value)}
          />
          <input
            type="password"
            placeholder="password"
            value={authPassword}
            onChange={(e) => setAuthPassword(e.target.value)}
          />
          <button onClick={() => handleAuth("login")}>Login</button>
          <button onClick={() => handleAuth("register")}>Register</button>
          {token && (
            <button className="ghost" onClick={handleLogout}>
              Logout ({userEmail})
            </button>
          )}
          <button className="ghost" onClick={() => { setAlertsOpen(!alertsOpen); if (!alertsOpen) loadAlerts(); }}>
            🔔 {alerts.length}
          </button>
        </div>
      </header>

      {authError && <div className="error">Auth: {authError}</div>}
      {error && <div className="error">Error: {error}</div>}

      {token && (
        <section className="stats">
          <div className="card">
            <div className="label">Messages total</div>
            <div className="value">{stats?.messages_total ?? "—"}</div>
          </div>
          <div className="card">
            <div className="label">Latest</div>
            <div className="value small">
              {stats?.latest ? (
                <>
                  <strong>{stats.latest.device_id}</strong> #{stats.latest.seq} —{" "}
                  {formatTs(stats.latest.ts)} — A:{stats.latest.field_a} B:{stats.latest.field_b}
                </>
              ) : (
                "—"
              )}
            </div>
          </div>
        </section>
      )}

      {alertsOpen && token && (
        <section className="panel">
          <div className="panel-header">
            <h2>Alerts</h2>
            <button className="ghost" onClick={loadAlerts}>
              Refresh
            </button>
          </div>
          {alertsError && <div className="error">Alerts: {alertsError}</div>}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>device</th>
                  <th>rule</th>
                  <th>time</th>
                  <th>field_a</th>
                  <th>field_b</th>
                  <th>severity</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => (
                  <tr key={a.id}>
                    <td>{a.device_id}</td>
                    <td>{a.rule_id}</td>
                    <td>{formatTs(a.triggered_at)}</td>
                    <td>{a.payload?.field_a ?? "—"}</td>
                    <td>{a.payload?.field_b ?? "—"}</td>
                    <td>{a.severity}</td>
                  </tr>
                ))}
                {alerts.length === 0 && (
                  <tr>
                    <td colSpan={6} className="muted">
                      No alerts yet
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="panel">
        <div className="panel-header">
          <h2>Messages</h2>
          <div className="actions">
            <input
              placeholder="device_id (optional)"
              value={deviceFilter}
              onChange={(e) => setDeviceFilter(e.target.value)}
            />
            <button onClick={loadMessages} disabled={loading || !token}>
              {loading ? "Loading..." : "Refresh"}
            </button>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>device</th>
                <th>seq</th>
                <th>ts</th>
                <th>field_a</th>
                <th>field_b</th>
                <th>battery</th>
              </tr>
            </thead>
            <tbody>
              {messages.map((m, idx) => (
                <tr key={`${m.device_id}-${m.seq}-${idx}`}>
                  <td>{m.device_id}</td>
                  <td>{m.seq}</td>
                  <td>{formatTs(m.ts)}</td>
                  <td>{m.field_a}</td>
                  <td>{m.field_b}</td>
                  <td>{m.battery}%</td>
                </tr>
              ))}
              {messages.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted">
                    {token ? "No data yet" : "Login to see messages"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Devices (auth required)</h2>
        </div>
        {deviceError && <div className="error">Devices: {deviceError}</div>}

        <div className="device-form">
          <input
            placeholder="Name"
            value={deviceName}
            onChange={(e) => setDeviceName(e.target.value)}
          />
          <input
            placeholder="Description"
            value={deviceDesc}
            onChange={(e) => setDeviceDesc(e.target.value)}
          />
          <input
            placeholder="External id (optional)"
            value={deviceExternal}
            onChange={(e) => setDeviceExternal(e.target.value)}
          />
          <button onClick={addDevice} disabled={!token}>
            Add device
          </button>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>name</th>
                <th>external_id</th>
                <th>created</th>
                <th>by</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {devices.map((d) => (
                <tr key={d._id}>
                  <td>{d.name}</td>
                  <td>{d.external_id || "—"}</td>
                  <td>{formatTs(d.created_at)}</td>
                  <td>{d.created_by || "—"}</td>
                  <td>
                    <button className="ghost" onClick={() => deleteDevice(d._id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {devices.length === 0 && (
                <tr>
                  <td colSpan={5} className="muted">
                    {token ? "No devices yet" : "Login to manage devices"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
