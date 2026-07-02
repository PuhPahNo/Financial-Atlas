"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiErrorText, paperTradingApi } from "@/lib/paperTradingApi";
import { Btn, Icon, IconBtn } from "./ptkit";

interface Msg { id: number; role: string; content: string; tool_calls?: any[]; error?: boolean }
interface Pending { id: number; action: string; payload: any; status: string }
interface ActionStatus { id: number; action: string; status: string; summary?: string; details?: string; result_ref?: any }

function pendingSummary(action: Pending) {
  const payload = action.payload ?? {};
  if (payload.action_summary) return payload.action_summary;
  if (payload.name) return `“${payload.name}”`;
  return action.action.replaceAll("_", " ");
}

function pendingDetail(action: Pending) {
  const payload = action.payload ?? {};
  if (payload.action_details) return payload.action_details;
  if (payload.category) return String(payload.category).replaceAll("_", " ");
  if (payload.strategy_name && payload.account_name) return `${payload.strategy_name} → ${payload.account_name}`;
  return "Review this local paper-trading change before it is saved.";
}

const SUGGESTIONS = [
  "When the S&P 500 hits a new all-time high, buy SQQQ; take profit 10%, stop loss 3%",
  "Backtest the S&P High Fade over COVID",
  "What's the valuation for NVDA?",
  "Create a long-term strategy named Cash Compounders for AAPL MSFT",
  "List my strategies",
];

export default function Copilot({ onChanged }: { onChanged?: () => void }) {
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [pending, setPending] = useState<Pending[]>([]);
  const [actions, setActions] = useState<ActionStatus[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  const connect = useCallback(() => {
    setSessionError(null);
    paperTradingApi.createAssistantSession().then((res) => {
      setSessionId(res.data.session.id);
      setActions(res.data.actions ?? []);
    }).catch((e) => setSessionError(apiErrorText(e)));
  }, []);
  useEffect(() => { connect(); }, [connect]);
  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" }); }, [messages, pending, busy]);

  const pushError = (prefix: string, e: unknown) =>
    setMessages((m) => [...m, { id: Date.now(), role: "assistant", error: true, content: `${prefix}: ${apiErrorText(e)}` }]);

  async function send(text: string) {
    if (!sessionId || !text.trim() || busy) return;
    setInput("");
    setMessages((m) => [...m, { id: Date.now(), role: "user", content: text }]);
    setBusy(true);
    try {
      const res = await paperTradingApi.sendAssistantMessage(sessionId, text);
      setMessages(res.data.messages);
      setPending(res.data.pending_actions ?? []);
      setActions(res.data.actions ?? []);
    } catch (e) { pushError("That message didn't go through", e); } finally { setBusy(false); }
  }
  async function confirm(id: number) {
    try {
      const res = await paperTradingApi.confirmAssistantAction(id);
      setMessages(res.data.messages); setPending(res.data.pending_actions ?? []); setActions(res.data.actions ?? []); onChanged?.();
    } catch (e) { pushError("Couldn't apply that action", e); }
  }
  async function reject(id: number) {
    try {
      const res = await paperTradingApi.rejectAssistantAction(id);
      setMessages(res.data.messages); setPending(res.data.pending_actions ?? []); setActions(res.data.actions ?? []);
    } catch (e) { pushError("Couldn't reject that action", e); }
  }

  return (
    <div style={{ animation: "pt-fadeUp .3s var(--ease)", display: "flex", flexDirection: "column", flex: 1, minHeight: 0, width: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
        <span style={{ width: 38, height: 38, borderRadius: 11, background: "linear-gradient(135deg, var(--cat-opt), var(--accent))", display: "grid", placeItems: "center", color: "#04040a" }}>
          <Icon name="sparkles" size={20} fill />
        </span>
        <div>
          <h1 className="serif" style={{ margin: 0, fontSize: 26, fontWeight: 600 }}>Atlas Copilot</h1>
          <p style={{ margin: "2px 0 0", fontSize: 13.5, color: "var(--text-2)" }}>Ask about fundamentals, build strategies, or launch backtests — actions are confirmed before they run.</p>
        </div>
      </div>

      <div ref={scroller} className="card" style={{ flex: 1, overflowY: "auto", padding: 22, display: "flex", flexDirection: "column", gap: 16, background: "var(--surface-1)" }}>
        {sessionError && (
          <div style={{ margin: "auto", textAlign: "center", maxWidth: 440 }}>
            <div style={{ fontSize: 14, color: "var(--neg)", marginBottom: 14, lineHeight: 1.5 }}>Couldn't connect to the Copilot: {sessionError}</div>
            <Btn variant="soft" size="sm" onClick={connect}>Retry connection</Btn>
          </div>
        )}
        {!sessionError && messages.length === 0 && !busy && (
          <div style={{ margin: "auto", textAlign: "center", maxWidth: 440 }}>
            <div style={{ fontSize: 15, color: "var(--text-2)", marginBottom: 18, lineHeight: 1.5 }}>I can pull Atlas valuation & cash-flow data, turn a plain-English idea into a backtestable signal rule (with your OK), and run backtests across real market regimes. Try:</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)} style={{ padding: "9px 14px", fontSize: 12.5, cursor: "pointer", textAlign: "left", color: "var(--text-1)", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-pill)" }}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
            <div style={{ maxWidth: "min(82%, 760px)", padding: "12px 16px", borderRadius: 16, fontSize: 14, lineHeight: 1.55, whiteSpace: "pre-wrap",
              background: m.role === "user" ? "var(--accent)" : m.error ? "var(--neg-soft)" : "var(--surface-2)", color: m.role === "user" ? "#0a0a12" : "var(--text-1)",
              border: m.role === "user" ? "none" : m.error ? "1px solid var(--neg)" : "1px solid var(--border)" }}>
              {m.content}
            </div>
          </div>
        ))}
        {pending.map((p) => (
          <div key={p.id} style={{ alignSelf: "flex-start", maxWidth: "92%", padding: 16, borderRadius: 14, background: "var(--accent-soft)", border: "1px solid var(--accent-line)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, color: "var(--accent-2)", fontWeight: 600, fontSize: 13 }}>
              <Icon name="sparkles" size={15} fill /> Confirm action: <span className="mono">{p.action}</span>
            </div>
            <div style={{ fontSize: 14, color: "var(--text-1)", fontWeight: 600, marginBottom: 4 }}>{pendingSummary(p)}</div>
            <div style={{ fontSize: 12.5, color: "var(--text-2)", marginBottom: 12, lineHeight: 1.45 }}>{pendingDetail(p)}</div>
            <div style={{ display: "flex", gap: 10 }}>
              <Btn variant="primary" size="sm" icon="play" onClick={() => confirm(p.id)}>Confirm</Btn>
              <Btn variant="soft" size="sm" icon="x" onClick={() => reject(p.id)}>Reject</Btn>
            </div>
          </div>
        ))}
        {actions.length > 0 && (
          <div style={{ alignSelf: "stretch", borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 2 }}>
            <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0, color: "var(--text-3)", marginBottom: 8 }}>Action status</div>
            <div style={{ display: "grid", gap: 8 }}>
              {actions.slice(-4).map((action) => (
                <div key={action.id} style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 10, alignItems: "start", padding: "9px 10px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface-2)" }}>
                  <span className="mono" style={{ fontSize: 10.5, color: action.status === "confirmed" ? "var(--pos)" : action.status === "rejected" ? "var(--neg)" : "var(--accent-2)", textTransform: "uppercase" }}>{action.status}</span>
                  <div>
                    <div style={{ fontSize: 12.5, color: "var(--text-1)", fontWeight: 600 }}>{action.summary || action.action.replaceAll("_", " ")}</div>
                    {action.result_ref?.name && <div style={{ fontSize: 11.5, color: "var(--text-2)", marginTop: 2 }}>{action.result_ref.name}</div>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {busy && (
          <div style={{ display: "flex", gap: 5, padding: "12px 16px", alignSelf: "flex-start" }}>
            {[0, 1, 2].map((i) => <span key={i} style={{ width: 7, height: 7, borderRadius: 999, background: "var(--text-3)", animation: "pt-fadeIn 1s ease infinite alternate", animationDelay: `${i * 0.15}s` }} />)}
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send(input)}
          placeholder={sessionId ? "Ask Atlas anything about your strategies or the markets…" : sessionError ? "Connection failed — retry above" : "Connecting…"} disabled={!sessionId}
          style={{ flex: 1, padding: "13px 16px", background: "var(--surface-2)", color: "var(--text-1)", border: "1px solid var(--border)", borderRadius: "var(--r-md)", fontSize: 14, fontFamily: "var(--font-sans)", outline: "none" }}
          onFocus={(e) => (e.target.style.borderColor = "var(--accent-line)")} onBlur={(e) => (e.target.style.borderColor = "var(--border)")} />
        <IconBtn icon="send" size={48} onClick={() => send(input)} title="Send" />
      </div>
    </div>
  );
}
