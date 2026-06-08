export interface Status {
  state: string;
  autonomy: string;
  equity: number;
  daily_pnl: number;
  trades_today: number;
  discipline_score: number;
  in_cooldown: boolean;
  live: boolean;
  prices: Record<string, number>;
}

export interface Alert {
  intent_id: string;
  symbol: string;
  side: string;
  strategy: string;
  entry_price: number;
  stop_loss: number;
  take_profits: [number, number][];
  risk_reward: number;
  size: number;
  notional: number;
  equity_at_risk_pct: number;
  rationale: string[];
  notes: string[];
  regime: string;
  timeout_sec: number;
  narration: string;
}

export interface Position {
  symbol: string; side: string; size: number; entry: number;
  stop: number; mark: number; upnl: number; r: number; tp1_done: boolean;
}

const j = (r: Response) => r.json();

export const api = {
  status: (): Promise<Status> => fetch("/api/status").then(j),
  positions: (): Promise<Position[]> => fetch("/api/positions").then(j),
  approvals: (): Promise<Alert[]> => fetch("/api/approvals").then(j),
  journal: () => fetch("/api/journal").then(j),
  resolve: (id: string, action: string, was_override = false) =>
    fetch(`/api/approvals/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, was_override }),
    }).then(j),
  control: (action: string, autonomy?: string) =>
    fetch("/api/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, autonomy }),
    }).then(j),
};
