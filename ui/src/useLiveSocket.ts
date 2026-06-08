import { useEffect, useRef, useState } from "react";

export interface LiveEvent {
  type: string;
  text?: string;
  alert?: any;
  [k: string]: any;
}

export function useLiveSocket(onEvent: (e: LiveEvent) => void) {
  const [connected, setConnected] = useState(false);
  const ref = useRef<WebSocket | null>(null);

  useEffect(() => {
    let stop = false;
    function connect() {
      if (stop) return;
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws`);
      ref.current = ws;
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        setTimeout(connect, 2000); // auto-reconnect
      };
      ws.onmessage = (m) => {
        try {
          onEvent(JSON.parse(m.data));
        } catch {
          /* ignore */
        }
      };
    }
    connect();
    return () => {
      stop = true;
      ref.current?.close();
    };
  }, []);

  return { connected };
}
