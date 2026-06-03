"use client";

import { useState } from "react";
import { paperTradingApi } from "@/lib/paperTradingApi";
import { Panel } from "@/components/ui";

export default function AssistantPanel({ onChanged }: { onChanged: () => void }) {
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [pending, setPending] = useState<any[]>([]);
  const [input, setInput] = useState("How would you improve this strategy?");
  const [busy, setBusy] = useState(false);

  async function ensureSession() {
    if (sessionId) return sessionId;
    const res = await paperTradingApi.createAssistantSession();
    setSessionId(res.data.session.id);
    return res.data.session.id as number;
  }

  async function send() {
    if (!input.trim()) return;
    setBusy(true);
    const text = input.trim();
    setInput("");
    setMessages((rows) => [...rows, { role: "user", content: text }]);
    try {
      const id = await ensureSession();
      const res = await paperTradingApi.sendAssistantMessage(id, text);
      setMessages(res.data.messages);
      setPending(res.data.pending_actions ?? []);
    } finally {
      setBusy(false);
    }
  }

  async function resolve(actionId: number, confirm: boolean) {
    const res = confirm
      ? await paperTradingApi.confirmAssistantAction(actionId)
      : await paperTradingApi.rejectAssistantAction(actionId);
    setMessages(res.data.messages);
    setPending(res.data.pending_actions ?? []);
    onChanged();
  }

  return (
    <Panel title="Atlas Research Assistant" hint="Discuss strategies and approve tool calls before they mutate local data.">
      <div className="space-y-3">
        <div className="max-h-72 space-y-3 overflow-y-auto rounded-lg border border-line bg-surface-2/40 p-3" aria-live="polite">
          {messages.length === 0 ? (
            <p className="text-sm text-muted">Ask about valuation, FCF, profitability, capex, or models you want to test.</p>
          ) : messages.map((message, idx) => (
            <div key={idx} className={message.role === "user" ? "text-right" : "text-left"}>
              <span className={`inline-block max-w-[90%] rounded-lg px-3 py-2 text-sm ${message.role === "user" ? "bg-accent text-white" : "bg-surface text-text"}`}>
                {message.content}
              </span>
            </div>
          ))}
        </div>
        {pending.map((action) => (
          <div key={action.id} className="rounded-lg border border-accent/40 bg-accent/10 p-3 text-sm">
            <p className="font-medium">Approve assistant action: {action.action}</p>
            <p className="mt-1 text-xs text-muted">{JSON.stringify(action.payload)}</p>
            <div className="mt-3 flex gap-2">
              <button onClick={() => resolve(action.id, true)} className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white">Confirm</button>
              <button onClick={() => resolve(action.id, false)} className="rounded-md border border-line px-3 py-1.5 text-xs text-muted hover:text-text">Reject</button>
            </div>
          </div>
        ))}
        <div className="flex gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} className="min-w-0 flex-1 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-accent" />
          <button onClick={send} disabled={busy} className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white shadow-glow disabled:opacity-50">{busy ? "Thinking..." : "Send"}</button>
        </div>
      </div>
    </Panel>
  );
}
