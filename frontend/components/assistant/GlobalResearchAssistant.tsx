"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { ApiError } from "@/lib/api";
import {
  AssistantBudget,
  AssistantMessage,
  AssistantSessionData,
  ResearchArtifact,
  assistantApi,
} from "@/lib/assistantApi";
import ArtifactTable from "./ArtifactTable";

const ArtifactChart = dynamic(() => import("./ArtifactChart"), {
  ssr: false,
  loading: () => <div className="atlas-artifact-card h-[286px] animate-pulse bg-white/[0.025]" />,
});

const STORAGE_KEY = "atlas.global-research-session.v1";

function Icon({ name, size = 18 }: { name: "sparkles" | "send" | "close" | "new" | "check" | "warning" | "source"; size?: number }) {
  const paths = {
    sparkles: <path d="m12 2 1.5 4.5L18 8l-4.5 1.5L12 14l-1.5-4.5L6 8l4.5-1.5L12 2Zm6 11 .8 2.2L21 16l-2.2.8L18 19l-.8-2.2L15 16l2.2-.8L18 13ZM5 14l1 3 3 1-3 1-1 3-1-3-3-1 3-1 1-3Z" />,
    send: <path d="m3 3 18 9-18 9 3.5-7.1L14 12l-7.5-1.9L3 3Z" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    new: <path d="M12 5v14M5 12h14" />,
    check: <path d="m5 12 4 4L19 6" />,
    warning: <path d="M12 3 2.8 20h18.4L12 3Zm0 6v5m0 3h.01" />,
    source: <path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5" />,
  };
  return <svg viewBox="0 0 24 24" width={size} height={size} fill={name === "sparkles" || name === "send" ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function ResearchAvatar({ size, alt = "" }: { size: number; alt?: string }) {
  return (
    <span className="atlas-research-avatar" style={{ width: size, height: size }}>
      <Image
        src="/atlas-ai-analyst.png"
        alt={alt}
        width={size}
        height={size}
        sizes={`${size}px`}
        className="h-full w-full object-cover"
        priority={size >= 60}
        unoptimized
      />
    </span>
  );
}

function InlineText({ text }: { text: string }) {
  const pieces = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return (
    <>
      {pieces.map((piece, index) => {
        if (piece.startsWith("**") && piece.endsWith("**")) return <strong key={index}>{piece.slice(2, -2)}</strong>;
        if (piece.startsWith("`") && piece.endsWith("`")) return <code key={index} className="rounded bg-white/[0.07] px-1 py-0.5 font-mono text-[0.9em] text-accent-2">{piece.slice(1, -1)}</code>;
        return <Fragment key={index}>{piece}</Fragment>;
      })}
    </>
  );
}

function RichText({ text }: { text: string }) {
  return (
    <div className="atlas-rich-text">
      {text.split("\n").map((line, index) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={index} className="h-2" />;
        if (trimmed.startsWith("### ")) return <h5 key={index}><InlineText text={trimmed.slice(4)} /></h5>;
        if (trimmed.startsWith("## ")) return <h4 key={index}><InlineText text={trimmed.slice(3)} /></h4>;
        if (trimmed.startsWith("# ")) return <h4 key={index}><InlineText text={trimmed.slice(2)} /></h4>;
        if (/^[-*] /.test(trimmed)) return <div key={index} className="atlas-rich-list"><span>•</span><span><InlineText text={trimmed.slice(2)} /></span></div>;
        const numbered = trimmed.match(/^(\d+)\.\s+(.+)/);
        if (numbered) return <div key={index} className="atlas-rich-list"><span>{numbered[1]}.</span><span><InlineText text={numbered[2]} /></span></div>;
        return <p key={index}><InlineText text={trimmed} /></p>;
      })}
    </div>
  );
}

function Sources({ artifact }: { artifact: ResearchArtifact }) {
  const [open, setOpen] = useState(false);
  const sources = artifact.sources ?? [];
  const checks = artifact.checks ?? [];
  if (!sources.length && !checks.length) return null;
  const warnings = checks.filter((check) => check.status === "warn").length;
  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-line bg-black/10">
      <button type="button" onClick={() => setOpen((current) => !current)} className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left">
        <span className="inline-flex items-center gap-2 text-[11px] font-medium text-muted">
          <Icon name={warnings ? "warning" : "check"} size={14} />
          {sources.length} source{sources.length === 1 ? "" : "s"} · {warnings ? `${warnings} gap${warnings === 1 ? "" : "s"}` : "grounded"}
        </span>
        <span className={`text-faint transition-transform ${open ? "rotate-180" : ""}`}>⌄</span>
      </button>
      {open && (
        <div className="border-t border-line px-3 py-3">
          <div className="grid gap-2">
            {sources.map((source, index) => (
              <div key={`${source.label}-${index}`} className="flex items-start gap-2 text-[10.5px] leading-relaxed text-muted">
                <span className="mt-0.5 text-accent-2"><Icon name="source" size={12} /></span>
                <span><strong className="font-medium text-text">{source.label}</strong> · {source.provider}{source.as_of ? ` · as of ${source.as_of}` : ""}</span>
              </div>
            ))}
            {checks.map((check) => (
              <div key={check.label} className="flex items-start gap-2 text-[10.5px] leading-relaxed text-muted">
                <span className={`mt-0.5 ${check.status === "warn" ? "text-negative" : check.status === "pass" ? "text-positive" : "text-accent-2"}`}><Icon name={check.status === "warn" ? "warning" : "check"} size={12} /></span>
                <span><strong className="font-medium text-text">{check.label}</strong> · {check.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ArtifactView({ artifact }: { artifact?: ResearchArtifact }) {
  if (!artifact) return null;
  const charts = artifact.charts ?? [];
  const tables = artifact.tables ?? [];
  if (!charts.length && !tables.length && !(artifact.sources?.length || artifact.checks?.length)) return null;
  return (
    <div className="mt-3 grid gap-2.5">
      {charts.map((chart) => <ArtifactChart key={chart.id} chart={chart} />)}
      {tables.map((table) => <ArtifactTable key={table.id} table={table} />)}
      <Sources artifact={artifact} />
    </div>
  );
}

function routeTicker(pathname: string): string | undefined {
  const match = pathname.match(/^\/company\/([^/]+)/i);
  return match ? decodeURIComponent(match[1]).toUpperCase() : undefined;
}

function errorText(error: unknown): string {
  if (error instanceof ApiError && error.code === "AI_BUDGET_EXHAUSTED") return error.message;
  if (error instanceof Error) return error.message;
  return "Atlas Research could not complete that request.";
}

function Message({ message }: { message: AssistantMessage }) {
  const assistant = message.role === "assistant";
  return (
    <article className={`flex ${assistant ? "justify-start" : "justify-end"}`}>
      <div className={assistant ? "w-full" : "max-w-[88%]"}>
        {assistant && (
          <div className="mb-1.5 flex items-center gap-1.5 px-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-faint">
            <ResearchAvatar size={17} /> Atlas Research
          </div>
        )}
        <div className={`${assistant ? "atlas-assistant-answer" : "atlas-user-message"} ${message.error ? "!border-negative/50 !bg-negative/10" : ""}`}>
          {assistant ? <RichText text={message.content} /> : <p>{message.content}</p>}
        </div>
        {assistant && <ArtifactView artifact={message.artifact} />}
      </div>
    </article>
  );
}

export default function GlobalResearchAssistant() {
  const pathname = usePathname();
  const ticker = routeTicker(pathname);
  const [open, setOpen] = useState(false);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [budget, setBudget] = useState<AssistantBudget | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [connecting, setConnecting] = useState(true);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [activity, setActivity] = useState("Reading Atlas data");
  const connectingRef = useRef(false);
  const scroller = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);

  const suggestions = useMemo(() => ticker ? [
    `What do the recent cash-flow and balance-sheet trends imply for ${ticker}?`,
    `How does ${ticker}'s valuation look relative to its cash generation and current price?`,
    `What are the strongest and weakest signals in ${ticker}'s fundamentals?`,
    "Compare AAPL, MSFT, and GOOGL cash generation over the last five annual periods.",
  ] : [
    "Compare AAPL, MSFT, and GOOGL cash generation over the last five annual periods.",
    "Which held up better over three years: SPY, QQQ, or IWM, and what did I pay in volatility?",
    "Screen tracked companies for FCF margin above 15% and positive margin of safety.",
    "What market and company data in Atlas would you examine before trusting a low P/E stock?",
  ], [ticker]);

  const fetchBudget = useCallback(async () => {
    try {
      const response = await assistantApi.budget();
      setBudget(response.data);
    } catch { /* session errors are more actionable than a missing budget badge */ }
  }, []);

  const createSession = useCallback(async () => {
    const response = await assistantApi.createSession();
    const data = response.data;
    localStorage.setItem(STORAGE_KEY, String(data.session.id));
    setSessionId(data.session.id);
    setMessages(data.messages ?? []);
    return data;
  }, []);

  const connect = useCallback(async () => {
    if (connectingRef.current) return;
    connectingRef.current = true;
    setConnecting(true);
    setConnectionError(null);
    try {
      const stored = Number(localStorage.getItem(STORAGE_KEY));
      let data: AssistantSessionData;
      if (Number.isInteger(stored) && stored > 0) {
        try {
          data = (await assistantApi.getSession(stored)).data;
          if (data.session.surface !== "global") data = await createSession();
          else setSessionId(stored);
        } catch {
          localStorage.removeItem(STORAGE_KEY);
          data = await createSession();
        }
      } else data = await createSession();
      setMessages(data.messages ?? []);
      await fetchBudget();
    } catch (error) {
      setConnectionError(errorText(error));
    } finally {
      setConnecting(false);
      connectingRef.current = false;
    }
  }, [createSession, fetchBudget]);

  useEffect(() => { void connect(); }, [connect]);
  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => textarea.current?.focus(), 180);
    const previous = document.body.style.overflow;
    if (window.innerWidth <= 760) document.body.style.overflow = "hidden";
    return () => {
      window.clearTimeout(timer);
      document.body.style.overflow = previous;
    };
  }, [open]);
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy, open]);
  useEffect(() => {
    if (!busy) return;
    const labels = ["Reading Atlas data", "Comparing periods", "Testing the interpretation", "Building grounded visuals"];
    let index = 0;
    setActivity(labels[0]);
    const interval = window.setInterval(() => {
      index = (index + 1) % labels.length;
      setActivity(labels[index]);
    }, 2400);
    return () => window.clearInterval(interval);
  }, [busy]);
  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if (event.key === "Escape" && open) setOpen(false);
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "j") {
        event.preventDefault();
        setOpen((current) => !current);
      }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, [open]);

  async function newConversation() {
    if (busy) return;
    setConnecting(true);
    try {
      localStorage.removeItem(STORAGE_KEY);
      await createSession();
      setInput("");
    } catch (error) {
      setConnectionError(errorText(error));
    } finally {
      setConnecting(false);
    }
  }

  async function send(text: string) {
    const question = text.trim();
    if (!question || !sessionId || busy) return;
    const optimistic: AssistantMessage = { id: Date.now(), role: "user", content: question, optimistic: true };
    setInput("");
    setMessages((current) => [...current, optimistic]);
    setBusy(true);
    try {
      const response = await assistantApi.sendMessage(sessionId, question, { path: pathname, ...(ticker ? { ticker } : {}) });
      setMessages(response.data.messages ?? []);
      const latestBudget = [...(response.data.messages ?? [])].reverse().find((message) => message.artifact?.budget)?.artifact?.budget;
      if (latestBudget) setBudget(latestBudget);
      else await fetchBudget();
    } catch (error) {
      setMessages((current) => [
        ...current,
        { id: Date.now() + 1, role: "assistant", content: errorText(error), error: true },
      ]);
      await fetchBudget();
    } finally {
      setBusy(false);
    }
  }

  if (pathname === "/login") return null;
  const budgetPct = budget?.limit_usd ? Math.min(100, (budget.spent_usd / budget.limit_usd) * 100) : 0;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`atlas-assistant-launcher ${open ? "pointer-events-none scale-90 opacity-0" : ""}`}
        aria-label="Open Atlas Research"
        title="Open Atlas Research (⌘J)"
      >
        <span className="atlas-launcher-glow" />
        <span className="atlas-launcher-avatar"><ResearchAvatar size={62} /></span>
        <span className="atlas-launcher-spark"><Icon name="sparkles" size={11} /></span>
        <span className="atlas-launcher-presence" />
        <span className="atlas-launcher-copy" aria-hidden="true">
          <strong>Ask Atlas</strong>
          <small>Your AI research analyst</small>
        </span>
      </button>

      {open && <button type="button" className="atlas-assistant-backdrop" onClick={() => setOpen(false)} aria-label="Close Atlas Research" />}
      <aside className={`atlas-assistant-panel ${open ? "is-open" : ""}`} aria-hidden={!open} aria-label="Atlas Research assistant">
        <header className="atlas-assistant-header">
          <div className="flex min-w-0 items-center gap-3">
            <div className="atlas-header-avatar">
              <ResearchAvatar size={42} />
              <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-[#111118] bg-positive" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="truncate font-serif text-[17px] font-semibold tracking-tight text-white">Atlas Research</h2>
                <span className="rounded-full border border-accent/25 bg-accent/10 px-1.5 py-0.5 text-[8px] font-semibold uppercase tracking-[0.12em] text-accent-2">AI</span>
              </div>
              <p className="truncate text-[10px] text-faint">Financial Atlas data · grounded visuals</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button type="button" onClick={newConversation} className="atlas-header-button" title="New conversation" aria-label="New conversation"><Icon name="new" size={17} /></button>
            <button type="button" onClick={() => setOpen(false)} className="atlas-header-button" title="Close" aria-label="Close Atlas Research"><Icon name="close" size={17} /></button>
          </div>
        </header>

        {budget && (
          <div className="atlas-budget-strip" title={`$${budget.spent_usd.toFixed(4)} used of the $${budget.limit_usd.toFixed(0)} application cap`}>
            <div className="flex items-center gap-2">
              <span className={`h-1.5 w-1.5 rounded-full ${budget.remaining_usd > 0 ? "bg-positive" : "bg-negative"}`} />
              <span>{budget.enabled ? `${budget.model.replace("gpt-", "GPT-")} · $${budget.remaining_usd.toFixed(2)} AI budget left` : "OpenAI not configured"}</span>
            </div>
            <div className="h-1 w-16 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-accent" style={{ width: `${budgetPct}%` }} /></div>
          </div>
        )}

        <div ref={scroller} className="atlas-assistant-scroll" aria-live="polite">
          {connecting && !messages.length && (
            <div className="grid min-h-full place-items-center text-center">
              <div><span className="mx-auto mb-3 block h-5 w-5 animate-spin rounded-full border-2 border-line border-t-accent" /><p className="text-xs text-muted">Connecting to Atlas…</p></div>
            </div>
          )}
          {connectionError && !messages.length && (
            <div className="mx-auto mt-24 max-w-xs rounded-2xl border border-negative/30 bg-negative/10 p-5 text-center">
              <p className="text-sm font-medium text-text">Atlas could not connect</p>
              <p className="mt-2 text-xs leading-relaxed text-muted">{connectionError}</p>
              <button type="button" onClick={() => void connect()} className="mt-4 rounded-lg bg-accent px-3 py-2 text-xs font-semibold text-white">Try again</button>
            </div>
          )}
          {!connecting && !connectionError && messages.length === 0 && (
            <div className="atlas-assistant-welcome">
              <div className="atlas-welcome-avatar"><ResearchAvatar size={78} alt="Atlas AI analyst" /></div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-2">Your Atlas research analyst</p>
              <h3 className="mt-2 font-serif text-2xl font-semibold leading-tight text-white">Ask the whole platform.</h3>
              <p className="mx-auto mt-2 max-w-sm text-xs leading-relaxed text-muted">
                Compare companies, interpret financial statements, test valuation logic, screen the tracked universe, or examine price risk—without hunting through tabs.
              </p>
              {ticker && <div className="mx-auto mt-3 w-fit rounded-full border border-accent/25 bg-accent/10 px-3 py-1 text-[10px] text-accent-2">Following {ticker} on this page</div>}
              <div className="mt-6 grid gap-2 text-left">
                {suggestions.map((suggestion) => (
                  <button type="button" key={suggestion} onClick={() => void send(suggestion)} className="atlas-suggestion">
                    <span className="mt-0.5 text-accent-2"><Icon name="sparkles" size={13} /></span>
                    <span>{suggestion}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.length > 0 && <div className="grid gap-5">{messages.map((message) => <Message key={message.id} message={message} />)}</div>}
          {busy && (
            <div className="mt-5 flex items-center gap-3 px-1 text-[11px] text-muted">
              <span className="relative flex h-6 w-6 items-center justify-center rounded-lg border border-accent/25 bg-accent/10 text-accent-2"><Icon name="sparkles" size={13} /><span className="absolute inset-0 animate-ping rounded-lg border border-accent/25" /></span>
              <span>{activity}<span className="atlas-thinking-dots">…</span></span>
            </div>
          )}
        </div>

        <footer className="atlas-assistant-composer">
          <div className="atlas-composer-shell">
            <textarea
              ref={textarea}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send(input);
                }
              }}
              rows={1}
              maxLength={4000}
              placeholder={ticker ? `Ask anything about ${ticker} or Atlas…` : "Ask anything Financial Atlas knows…"}
              disabled={!sessionId || busy || connecting}
              className="min-h-[44px] max-h-32 flex-1 resize-none bg-transparent px-1 py-2.5 text-[13px] leading-relaxed text-text outline-none placeholder:text-faint disabled:opacity-50"
              aria-label="Ask Atlas Research"
            />
            <button type="button" onClick={() => void send(input)} disabled={!input.trim() || !sessionId || busy} className="atlas-send-button" aria-label="Send question"><Icon name="send" size={16} /></button>
          </div>
          <div className="mt-2 flex items-center justify-between px-1 text-[9px] text-faint">
            <span>Research, not personalized financial advice.</span>
            <span className="hidden sm:inline">Enter to send · Shift+Enter for line break</span>
          </div>
        </footer>
      </aside>
    </>
  );
}
