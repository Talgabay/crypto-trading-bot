import { useEffect, useState } from "react";
import { api, Alert, Position, Status } from "./api";
import { useLiveSocket } from "./useLiveSocket";

const stateColor: Record<string, string> = {
  running: "bg-emerald-600",
  paused: "bg-amber-600",
  halted: "bg-rose-700",
  cooldown: "bg-indigo-600",
};

function Card(props: { title: string; children: any; className?: string }) {
  return (
    <div className={`bg-slate-900/70 rounded-xl p-4 border border-slate-800 ${props.className || ""}`}>
      <h2 className="text-sm font-semibold text-slate-400 mb-3">{props.title}</h2>
      {props.children}
    </div>
  );
}

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [feed, setFeed] = useState<string[]>([]);
  const [journal, setJournal] = useState<any>(null);

  const { connected } = useLiveSocket((e) => {
    if (e.type === "narration" && e.text) {
      setFeed((f) => [e.text!, ...f].slice(0, 40));
    } else if (e.type === "approval_request" && e.alert) {
      setAlerts((a) => [e.alert, ...a.filter((x) => x.intent_id !== e.alert.intent_id)]);
    }
  });

  async function refresh() {
    setStatus(await api.status());
    setPositions(await api.positions());
    setAlerts(await api.approvals());
    setJournal((await api.journal()).summary);
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2500);
    return () => clearInterval(t);
  }, []);

  async function decide(id: string, action: string) {
    await api.resolve(id, action);
    setAlerts((a) => a.filter((x) => x.intent_id !== id));
  }

  return (
    <div className="max-w-6xl mx-auto p-5 space-y-4">
      {/* header / status banner */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">🤝 קו-פיילוט מסחר</h1>
          <p className="text-slate-400 text-sm">שותף שמגשר על הפער הפסיכולוגי</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`px-3 py-1 rounded-full text-sm ${stateColor[status?.state || "paused"]}`}>
            {status?.state?.toUpperCase() || "—"}
          </span>
          <span className={`w-2 h-2 rounded-full ${connected ? "bg-emerald-400" : "bg-rose-500"}`} title="WS" />
          <span className="text-xs text-slate-400">{status?.live ? "LIVE testnet" : "דמו"}</span>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card title="הון (Equity)"><div className="text-2xl font-bold">${status?.equity?.toLocaleString() ?? "—"}</div></Card>
        <Card title="P&L יומי"><div className={`text-2xl font-bold ${(status?.daily_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{status?.daily_pnl?.toFixed(2) ?? "—"}</div></Card>
        <Card title="עסקאות היום"><div className="text-2xl font-bold">{status?.trades_today ?? 0}</div></Card>
        <Card title="ציון משמעת"><div className="text-2xl font-bold text-indigo-300">{status?.discipline_score ?? 100}</div></Card>
      </div>

      {/* controls */}
      <Card title="שליטה">
        <div className="flex flex-wrap gap-2 items-center">
          <button onClick={() => api.control("resume").then(refresh)} className="px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-sm">▶ הפעל</button>
          <button onClick={() => api.control("pause").then(refresh)} className="px-3 py-1.5 rounded bg-amber-700 hover:bg-amber-600 text-sm">⏸ השהה</button>
          <button onClick={() => api.control("kill").then(refresh)} className="px-3 py-1.5 rounded bg-rose-800 hover:bg-rose-700 text-sm">🛑 Kill switch</button>
          <div className="mx-2 h-6 w-px bg-slate-700" />
          <span className="text-sm text-slate-400">אוטונומיה:</span>
          {["auto", "approve", "advise"].map((m) => (
            <button key={m} onClick={() => api.control("autonomy", m).then(refresh)}
              className={`px-3 py-1.5 rounded text-sm ${status?.autonomy === m ? "bg-indigo-600" : "bg-slate-700 hover:bg-slate-600"}`}>
              {m === "auto" ? "אוטומטי" : m === "approve" ? "אישור" : "ייעוץ"}
            </button>
          ))}
        </div>
      </Card>

      {/* pending approvals — the heart of semi-auto */}
      {alerts.length > 0 && (
        <Card title={`🔔 ממתין לאישורך (${alerts.length})`} className="border-indigo-700">
          <div className="space-y-3">
            {alerts.map((a) => (
              <div key={a.intent_id} className="bg-slate-800/60 rounded-lg p-3">
                <div className="flex justify-between items-center mb-2">
                  <span className="font-semibold">{a.side === "long" ? "🟢 לונג" : "🔴 שורט"} {a.symbol}</span>
                  <span className="text-xs text-slate-400">{a.strategy} · R:R {a.risk_reward}</span>
                </div>
                <ul className="text-sm text-slate-300 list-disc pr-5 mb-2">
                  {a.rationale.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
                <div className="text-xs text-slate-400 mb-2">
                  כניסה {a.entry_price} · SL {a.stop_loss} · גודל {a.size} · סיכון {a.equity_at_risk_pct}%
                </div>
                <div className="flex gap-2">
                  <button onClick={() => decide(a.intent_id, "approve")} className="px-4 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-sm">✅ אישור</button>
                  <button onClick={() => decide(a.intent_id, "reject")} className="px-4 py-1.5 rounded bg-rose-700 hover:bg-rose-600 text-sm">❌ דחייה</button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        {/* positions */}
        <Card title="פוזיציות פתוחות">
          {positions.length === 0 ? <p className="text-slate-500 text-sm">אין פוזיציות פתוחות</p> : (
            <table className="w-full text-sm">
              <thead className="text-slate-500 text-right">
                <tr><th>נכס</th><th>כיוון</th><th>כניסה</th><th>מחיר</th><th>R</th><th>P&L</th></tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.symbol} className="border-t border-slate-800">
                    <td>{p.symbol}</td>
                    <td>{p.side === "long" ? "לונג" : "שורט"}</td>
                    <td>{p.entry.toFixed(2)}</td>
                    <td>{p.mark.toFixed(2)}</td>
                    <td className={p.r >= 0 ? "text-emerald-400" : "text-rose-400"}>{p.r}R</td>
                    <td className={p.upnl >= 0 ? "text-emerald-400" : "text-rose-400"}>{p.upnl}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        {/* narration feed — the 'partner who tells you what's happening' */}
        <Card title="📣 פיד נרטיב (השותף)">
          <div className="space-y-1 max-h-72 overflow-y-auto text-sm">
            {feed.length === 0 ? <p className="text-slate-500">מקשיב לשוק…</p> :
              feed.map((t, i) => (
                <div key={i} className="text-slate-300 whitespace-pre-line border-b border-slate-800/60 pb-1">{t}</div>
              ))}
          </div>
        </Card>
      </div>

      {/* journal / psychology loop */}
      {journal && (
        <Card title="📔 יומן — בוט מול החלטות אנושיות">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-slate-400">כשעקבת אחרי התוכנית</div>
              <div className="text-lg">{journal.followed.count} עסקאות · {journal.followed.wins} מנצחות</div>
              <div className={journal.followed.pnl >= 0 ? "text-emerald-400" : "text-rose-400"}>P&L {journal.followed.pnl}</div>
            </div>
            <div>
              <div className="text-slate-400">כשעקפת (override)</div>
              <div className="text-lg">{journal.override.count} עסקאות · {journal.override.wins} מנצחות</div>
              <div className={journal.override.pnl >= 0 ? "text-emerald-400" : "text-rose-400"}>P&L {journal.override.pnl}</div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
