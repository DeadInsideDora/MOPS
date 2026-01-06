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

const apiBase = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${apiBase}${path}`);
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return res.json();
}

function formatTs(ts: string) {
  return new Date(ts).toLocaleString();
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [deviceFilter, setDeviceFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (deviceFilter.trim()) params.set("device_id", deviceFilter.trim());
    params.set("limit", "50");
    return params.toString();
  }, [deviceFilter]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [msgs, st] = await Promise.all([
        fetchJson<Message[]>(`/messages?${query}`),
        fetchJson<Stats>("/stats"),
      ]);
      setMessages(msgs);
      setStats(st);
    } catch (e: any) {
      setError(e.message || "Error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  return (
    <div className="page">
      <header>
        <div>
          <h1>IoT Dashboard</h1>
          <p className="muted">API: {apiBase}</p>
        </div>
        <div className="actions">
          <input
            placeholder="device_id (optional)"
            value={deviceFilter}
            onChange={(e) => setDeviceFilter(e.target.value)}
          />
          <button onClick={load} disabled={loading}>
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      </header>

      {error && <div className="error">Error: {error}</div>}

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

      <section>
        <h2>Messages</h2>
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
                    No data yet
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
