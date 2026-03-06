import { useState, useEffect, useCallback, useRef } from "react";

const API = "https://sotso-assistant.duckdns.org/api/v1";

const C = {
  bg: "#0b0c10", surface: "#13141c", card: "#181a25", cardHover: "#1e2030",
  border: "#252838", text: "#e8eaf0", muted: "#6b7094",
  accent: "#3b82f6", accentSoft: "rgba(59,130,246,0.1)", accentGlow: "rgba(59,130,246,0.2)",
  green: "#22c55e", greenSoft: "rgba(34,197,94,0.1)",
  orange: "#f97316", orangeSoft: "rgba(249,115,22,0.1)",
  red: "#ef4444", redSoft: "rgba(239,68,68,0.1)",
  purple: "#a855f7", purpleSoft: "rgba(168,85,247,0.1)",
  pink: "#ec4899", pinkSoft: "rgba(236,72,153,0.1)",
  yellow: "#eab308", yellowSoft: "rgba(234,179,8,0.1)",
};

const PRIO = { urgent: { c: C.red, bg: C.redSoft, l: "Urgent" }, high: { c: C.orange, bg: C.orangeSoft, l: "High" }, medium: { c: C.yellow, bg: C.yellowSoft, l: "Medium" }, low: { c: C.green, bg: C.greenSoft, l: "Low" } };
const STATUS = { todo: { c: C.muted, bg: "rgba(107,112,148,0.1)", l: "To Do", i: "\u{1F4CB}" }, in_progress: { c: C.accent, bg: C.accentSoft, l: "In Progress", i: "\u{1F504}" }, review: { c: C.purple, bg: C.purpleSoft, l: "Review", i: "\u{1F440}" }, done: { c: C.green, bg: C.greenSoft, l: "Done", i: "\u2705" } };

function useFetch(url, interval = 0) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    try {
      const r = await fetch(url);
      if (r.ok) setData(await r.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [url]);
  useEffect(() => {
    load();
    if (interval > 0) { const id = setInterval(load, interval); return () => clearInterval(id); }
  }, [load, interval]);
  return { data, loading, refresh: load };
}

// ─── Components ───
function Badge({ color, bg, children }) {
  return <span style={{ background: bg, color, padding: "3px 10px", borderRadius: 6, fontSize: 11, fontWeight: 700 }}>{children}</span>;
}

function StatCard({ icon, label, value, color, bg }) {
  return (
    <div style={{ background: C.card, borderRadius: 14, padding: "18px 20px", border: `1px solid ${C.border}`, flex: "1 1 140px", minWidth: 140 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <div style={{ width: 34, height: 34, borderRadius: 9, background: bg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>{icon}</div>
        <span style={{ fontSize: 11, color: C.muted, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</span>
      </div>
      <div style={{ fontSize: 26, fontWeight: 800, color: C.text, fontFamily: "'Outfit',sans-serif" }}>{value}</div>
    </div>
  );
}

function TaskRow({ task, onStatusChange }) {
  const st = STATUS[task.status] || STATUS.todo;
  const pr = PRIO[task.priority] || PRIO.medium;
  return (
    <div style={{ background: C.card, borderRadius: 12, padding: "12px 16px", border: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 12, transition: "border-color 0.2s" }}>
      <div style={{ width: 4, height: 28, borderRadius: 2, background: pr.c, flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: C.text, textDecoration: task.status === "done" ? "line-through" : "none", opacity: task.status === "done" ? 0.5 : 1 }}>{task.title}</div>
        <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>
          {task.assignee || "Unassigned"}{task.label ? ` · ${task.label}` : ""}{task.due_date ? ` · Due ${new Date(task.due_date).toLocaleDateString()}` : ""}
        </div>
      </div>
      <Badge color={pr.c} bg={pr.bg}>{pr.l}</Badge>
      <select value={task.status} onChange={e => onStatusChange(task.id, e.target.value)} style={{
        background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, color: st.c, padding: "5px 8px", fontSize: 11, fontWeight: 600, cursor: "pointer", outline: "none",
      }}>
        <option value="todo">To Do</option>
        <option value="in_progress">In Progress</option>
        <option value="review">Review</option>
        <option value="done">Done</option>
      </select>
    </div>
  );
}

function KanbanColumn({ title, icon, color, tasks, onStatusChange }) {
  return (
    <div style={{ flex: "1 1 240px", minWidth: 240 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, padding: "0 4px" }}>
        <span>{icon}</span>
        <span style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{title}</span>
        <span style={{ fontSize: 11, color: C.muted, background: C.surface, padding: "2px 8px", borderRadius: 10, fontWeight: 600 }}>{tasks.length}</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, minHeight: 100, background: C.surface, borderRadius: 12, padding: 10, border: `1px solid ${C.border}` }}>
        {tasks.length === 0 && <div style={{ fontSize: 12, color: C.muted, textAlign: "center", padding: 20, fontStyle: "italic" }}>No tasks</div>}
        {tasks.map(t => (
          <div key={t.id} style={{ background: C.card, borderRadius: 10, padding: "12px 14px", border: `1px solid ${C.border}`, borderLeft: `3px solid ${(PRIO[t.priority] || PRIO.medium).c}` }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: C.text, marginBottom: 6 }}>{t.title}</div>
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontSize: 10, color: C.muted }}>{t.assignee || "?"}</span>
              {t.label && <Badge color={C.accent} bg={C.accentSoft}>{t.label}</Badge>}
              <Badge color={(PRIO[t.priority] || PRIO.medium).c} bg={(PRIO[t.priority] || PRIO.medium).bg}>{(PRIO[t.priority] || PRIO.medium).l}</Badge>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ProgressBar({ name, stats }) {
  const total = stats.total || 1;
  const done = stats.done || 0;
  const pct = Math.round((done / total) * 100);
  return (
    <div style={{ background: C.card, borderRadius: 12, padding: "14px 18px", border: `1px solid ${C.border}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{name}</span>
        <span style={{ fontSize: 12, fontWeight: 700, color: C.accent }}>{pct}%</span>
      </div>
      <div style={{ height: 6, borderRadius: 3, background: C.surface, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", borderRadius: 3, background: `linear-gradient(90deg, ${C.accent}, ${C.green})`, transition: "width 0.5s" }} />
      </div>
      <div style={{ display: "flex", gap: 12, marginTop: 6, fontSize: 10, color: C.muted }}>
        <span>{stats.todo || 0} todo</span>
        <span>{stats.in_progress || 0} active</span>
        <span>{stats.review || 0} review</span>
        <span>{stats.done || 0} done</span>
      </div>
    </div>
  );
}

function AIChat() {
  const [msgs, setMsgs] = useState([{ role: "bot", text: "Hello! I'm your AI assistant. Ask me anything about tasks, calendar, or team progress." }]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const send = async () => {
    if (!input.trim() || loading) return;
    const q = input.trim();
    setMsgs(p => [...p, { role: "user", text: q }]);
    setInput("");
    setLoading(true);
    try {
      const r = await fetch(`${API}/ai/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: q }) });
      const d = await r.json();
      setMsgs(p => [...p, { role: "bot", text: d.response || "No response" }]);
    } catch { setMsgs(p => [...p, { role: "bot", text: "Error connecting to API" }]); }
    setLoading(false);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 10, paddingBottom: 10 }}>
        {msgs.map((m, i) => (
          <div key={i} style={{ alignSelf: m.role === "user" ? "flex-end" : "flex-start", maxWidth: "80%" }}>
            <div style={{
              background: m.role === "user" ? C.accent : C.card, color: m.role === "user" ? "#fff" : C.text,
              padding: "10px 14px", borderRadius: 12, fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap",
              border: m.role === "bot" ? `1px solid ${C.border}` : "none",
              borderBottomRightRadius: m.role === "user" ? 4 : 12, borderBottomLeftRadius: m.role === "bot" ? 4 : 12,
            }}>{m.text}</div>
          </div>
        ))}
        {loading && <div style={{ alignSelf: "flex-start", background: C.card, padding: "10px 16px", borderRadius: 12, border: `1px solid ${C.border}`, fontSize: 13, color: C.muted }}>Thinking...</div>}
        <div ref={endRef} />
      </div>
      <div style={{ display: "flex", gap: 8, paddingTop: 10, borderTop: `1px solid ${C.border}` }}>
        <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === "Enter" && send()}
          placeholder="Ask anything — tasks, calendar, insights..." style={{
            flex: 1, background: C.card, border: `1px solid ${C.border}`, borderRadius: 10, padding: "10px 14px",
            color: C.text, fontSize: 13, outline: "none", fontFamily: "'DM Sans',sans-serif",
          }} />
        <button onClick={send} style={{ width: 42, height: 42, borderRadius: 10, border: "none", background: C.accent, color: "#fff", fontSize: 16, cursor: "pointer" }}>\u2191</button>
      </div>
    </div>
  );
}

// ─── Pages ───
function DashboardPage() {
  const { data: dash, loading } = useFetch(`${API}/dashboard`, 30000);
  if (loading) return <div style={{ color: C.muted, padding: 40 }}>Loading dashboard...</div>;
  if (!dash) return <div style={{ color: C.red, padding: 40 }}>Failed to load dashboard. Check API connection.</div>;

  const s = dash.stats;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h2 style={{ fontSize: 24, fontWeight: 800, color: C.text, fontFamily: "'Outfit',sans-serif", margin: 0 }}>Dashboard</h2>
        <p style={{ fontSize: 13, color: C.muted, margin: "4px 0 0" }}>AI Personal Assistant Overview</p>
      </div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <StatCard icon="\u{1F4CB}" label="To Do" value={s.todo} color={C.muted} bg="rgba(107,112,148,0.1)" />
        <StatCard icon="\u{1F504}" label="In Progress" value={s.in_progress} color={C.accent} bg={C.accentSoft} />
        <StatCard icon="\u{1F440}" label="Review" value={s.review} color={C.purple} bg={C.purpleSoft} />
        <StatCard icon="\u2705" label="Done" value={s.done} color={C.green} bg={C.greenSoft} />
        <StatCard icon="\u{1F534}" label="Overdue" value={s.overdue} color={C.red} bg={C.redSoft} />
        <StatCard icon="\u{1F4AC}" label="Messages" value={s.total_messages} color={C.pink} bg={C.pinkSoft} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div style={{ background: C.card, borderRadius: 14, padding: 20, border: `1px solid ${C.border}` }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: C.text, margin: "0 0 14px", fontFamily: "'Outfit',sans-serif" }}>Team Progress</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {Object.entries(dash.team_stats || {}).map(([name, stats]) => <ProgressBar key={name} name={name} stats={stats} />)}
            {Object.keys(dash.team_stats || {}).length === 0 && <div style={{ fontSize: 12, color: C.muted }}>No team data yet</div>}
          </div>
        </div>

        <div style={{ background: C.card, borderRadius: 14, padding: 20, border: `1px solid ${C.border}` }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: C.text, margin: "0 0 14px", fontFamily: "'Outfit',sans-serif" }}>Recent Tasks</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {(dash.recent_tasks || []).slice(0, 8).map(t => (
              <div key={t.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0", borderBottom: `1px solid ${C.border}` }}>
                <span style={{ fontSize: 12 }}>{(STATUS[t.status] || STATUS.todo).i}</span>
                <div style={{ flex: 1, fontSize: 12, color: C.text, fontWeight: 500 }}>{t.title}</div>
                <span style={{ fontSize: 10, color: C.muted }}>{t.assignee}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {dash.overdue_tasks?.length > 0 && (
        <div style={{ background: C.redSoft, borderRadius: 14, padding: 18, border: `1px solid rgba(239,68,68,0.2)` }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: C.red, margin: "0 0 10px" }}>\u{26A0}\u{FE0F} Overdue Tasks</h3>
          {dash.overdue_tasks.map(t => (
            <div key={t.id} style={{ fontSize: 12, color: C.text, padding: "4px 0" }}>#{t.id} {t.title} \u2192 {t.assignee}</div>
          ))}
        </div>
      )}
    </div>
  );
}

function BoardPage() {
  const { data, loading, refresh } = useFetch(`${API}/board`, 15000);
  const board = data?.board || { todo: [], in_progress: [], review: [], done: [] };

  const changeStatus = async (id, status) => {
    await fetch(`${API}/tasks/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
    refresh();
  };

  if (loading) return <div style={{ color: C.muted, padding: 40 }}>Loading board...</div>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <h2 style={{ fontSize: 24, fontWeight: 800, color: C.text, fontFamily: "'Outfit',sans-serif", margin: 0 }}>Task Board</h2>
      <div style={{ display: "flex", gap: 14, overflowX: "auto" }}>
        <KanbanColumn title="To Do" icon="\u{1F4CB}" color={C.muted} tasks={board.todo} onStatusChange={changeStatus} />
        <KanbanColumn title="In Progress" icon="\u{1F504}" color={C.accent} tasks={board.in_progress} onStatusChange={changeStatus} />
        <KanbanColumn title="Review" icon="\u{1F440}" color={C.purple} tasks={board.review} onStatusChange={changeStatus} />
        <KanbanColumn title="Done" icon="\u2705" color={C.green} tasks={board.done.slice(0, 10)} onStatusChange={changeStatus} />
      </div>
    </div>
  );
}

function TasksPage() {
  const { data, loading, refresh } = useFetch(`${API}/tasks?limit=50`, 15000);
  const [filter, setFilter] = useState("all");
  const tasks = (data?.tasks || []).filter(t => filter === "all" || t.status === filter);

  const changeStatus = async (id, status) => {
    await fetch(`${API}/tasks/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
    refresh();
  };

  const filters = [{ id: "all", l: "All" }, { id: "todo", l: "To Do" }, { id: "in_progress", l: "Active" }, { id: "review", l: "Review" }, { id: "done", l: "Done" }];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <h2 style={{ fontSize: 24, fontWeight: 800, color: C.text, fontFamily: "'Outfit',sans-serif", margin: 0 }}>Tasks</h2>
      <div style={{ display: "flex", gap: 6 }}>
        {filters.map(f => (
          <button key={f.id} onClick={() => setFilter(f.id)} style={{
            padding: "7px 14px", borderRadius: 8, border: `1px solid ${filter === f.id ? C.accent : C.border}`,
            background: filter === f.id ? C.accentSoft : "transparent", color: filter === f.id ? C.accent : C.muted,
            fontSize: 12, fontWeight: 600, cursor: "pointer",
          }}>{f.l}</button>
        ))}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {loading && <div style={{ color: C.muted }}>Loading...</div>}
        {tasks.map(t => <TaskRow key={t.id} task={t} onStatusChange={changeStatus} />)}
        {!loading && tasks.length === 0 && <div style={{ color: C.muted, textAlign: "center", padding: 40 }}>No tasks found</div>}
      </div>
    </div>
  );
}

function ChatPage() {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 40px)" }}>
      <h2 style={{ fontSize: 24, fontWeight: 800, color: C.text, fontFamily: "'Outfit',sans-serif", margin: "0 0 16px" }}>\u2728 AI Assistant</h2>
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <AIChat />
      </div>
    </div>
  );
}

// ─── Sidebar ───
function Sidebar({ active, onNav }) {
  const items = [
    { id: "dashboard", icon: "\u229E", label: "Dashboard" },
    { id: "board", icon: "\u{1F5C2}", label: "Board" },
    { id: "tasks", icon: "\u2611", label: "Tasks" },
    { id: "chat", icon: "\u2728", label: "AI Chat" },
  ];
  return (
    <div style={{
      width: 64, minHeight: "100vh", background: C.surface, borderRight: `1px solid ${C.border}`,
      display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 16, gap: 4,
    }}>
      <div style={{
        width: 38, height: 38, borderRadius: 10, background: `linear-gradient(135deg, ${C.accent}, ${C.purple})`,
        display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, color: "#fff", fontWeight: 800,
        marginBottom: 20, boxShadow: `0 4px 16px ${C.accentGlow}`,
      }}>AI</div>
      {items.map(it => (
        <button key={it.id} onClick={() => onNav(it.id)} style={{
          width: 46, height: 46, borderRadius: 10, border: "none",
          background: active === it.id ? C.accentSoft : "transparent",
          color: active === it.id ? C.accent : C.muted,
          fontSize: 18, cursor: "pointer", display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center", gap: 2, transition: "all 0.2s",
        }}>
          <span>{it.icon}</span>
          <span style={{ fontSize: 8, fontWeight: 600 }}>{it.label}</span>
        </button>
      ))}
    </div>
  );
}

// ─── App ───
export default function App() {
  const [page, setPage] = useState("dashboard");
  return (
    <div style={{ display: "flex", minHeight: "100vh", background: C.bg, fontFamily: "'DM Sans',sans-serif", color: C.text }}>
      <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet" />
      <Sidebar active={page} onNav={setPage} />
      <div style={{ flex: 1, padding: "20px 28px", overflowY: "auto", maxHeight: "100vh" }}>
        {page === "dashboard" && <DashboardPage />}
        {page === "board" && <BoardPage />}
        {page === "tasks" && <TasksPage />}
        {page === "chat" && <ChatPage />}
      </div>
    </div>
  );
}
