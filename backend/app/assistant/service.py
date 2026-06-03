"""Research assistant service with persisted memory and confirmed tool calls."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

import httpx

from ..core.config import settings
from ..core.errors import NotFoundError, ValidationError
from ..db import _now, session_scope
from ..models.assistant import AssistantMessage, AssistantPendingAction, AssistantSession
from ..paper_trading import service as paper_service
from .schemas import MessageCreate, SessionCreate
from .tools import execute_read_tool, execute_write_tool

SYSTEM_PROMPT = (
    "You are Atlas, a research assistant for Financial Atlas. Explain assumptions, use Atlas data "
    "when available, and never provide personalized financial advice or real trading instructions."
)

# Common inverse / leveraged ETFs people name when fading an index.
INVERSE_ETFS = {"SQQQ", "SPXU", "SDOW", "SDS", "SH", "PSQ", "DOG", "RWM", "QID", "TZA", "SOXS", "FAZ", "SARK", "SPXS"}
# Index phrases → the price symbol the signal engine reads.
_INDEX_REF = [
    ("s&p 500", "^GSPC"), ("s&p500", "^GSPC"), ("sp 500", "^GSPC"), ("sp500", "^GSPC"),
    ("s&p", "^GSPC"), ("spx", "^GSPC"), ("spy", "^GSPC"),
    ("nasdaq 100", "^IXIC"), ("nasdaq", "^IXIC"), ("ndx", "^IXIC"), ("qqq", "^IXIC"),
    ("dow jones", "^DJI"), ("dow", "^DJI"), ("russell", "^RUT"),
]
_REF_LABEL = {"^GSPC": "S&P 500", "^IXIC": "Nasdaq", "^DJI": "Dow Jones", "^RUT": "Russell 2000"}
_SIGNAL_LABEL = {
    "new_high": "new high", "new_low": "new low", "pct_drop": "dip",
    "pct_gain": "surge", "ma_cross_up": "MA crossover",
}


def create_session(payload: SessionCreate) -> dict:
    with session_scope() as session:
        row = AssistantSession(title=payload.title or "Paper trading chat", summary="")
        session.add(row)
        session.flush()
        return {"session": _session_view(row), "messages": [], "pending_actions": []}


def get_session(session_id: int) -> dict:
    with session_scope() as session:
        row = session.get(AssistantSession, session_id)
        if not row:
            raise NotFoundError(f"Assistant session {session_id} not found")
        return {"session": _session_view(row), "messages": _messages(session, session_id), "pending_actions": _pending(session, session_id)}


def add_message(session_id: int, payload: MessageCreate) -> dict:
    with session_scope() as session:
        row = session.get(AssistantSession, session_id)
        if not row:
            raise NotFoundError(f"Assistant session {session_id} not found")
        user = AssistantMessage(session_id=session_id, role="user", content=payload.message, tool_calls_json=[])
        session.add(user)
        planned = _plan_action(payload.message)
        tool_calls: list[dict[str, Any]] = []
        if planned and planned["kind"] == "write":
            action = AssistantPendingAction(session_id=session_id, action=planned["action"], payload_json=planned["payload"])
            session.add(action)
            content = _confirm_prompt(planned["payload"])
            tool_calls.append({"pending_action": planned["action"], "payload": planned["payload"]})
        elif planned and planned["kind"] == "backtest":
            content = _run_backtest_reply(planned["payload"]["message"])
            tool_calls.append({"tool": "run_backtest"})
        elif planned and planned["kind"] == "read":
            result = execute_read_tool(planned["action"], planned["payload"])
            content = _summarize_tool(planned["action"], result)
            tool_calls.append({"tool": planned["action"], "payload": planned["payload"]})
        else:
            content = _llm_reply(_messages(session, session_id) + [{"role": "user", "content": payload.message}])
        session.add(AssistantMessage(session_id=session_id, role="assistant", content=content, tool_calls_json=tool_calls))
        row.updated_at = _now()
        session.flush()
        return {"session": _session_view(row), "messages": _messages(session, session_id), "pending_actions": _pending(session, session_id)}


def confirm_action(action_id: int) -> dict:
    with session_scope() as session:
        action = session.get(AssistantPendingAction, action_id)
        if not action:
            raise NotFoundError(f"Assistant action {action_id} not found")
        if action.status != "pending":
            raise ValidationError("Assistant action has already been resolved")
        result = execute_write_tool(action.action, dict(action.payload_json or {}))
        action.status = "confirmed"
        action.resolved_at = _now()
        content = f"Confirmed. I executed `{action.action}` and updated the local paper-trading workspace."
        session.add(AssistantMessage(session_id=action.session_id, role="assistant", content=content, tool_calls_json=[{"tool": action.action}]))
        session.flush()
        return {"result": result, "messages": _messages(session, action.session_id), "pending_actions": _pending(session, action.session_id)}


def reject_action(action_id: int) -> dict:
    with session_scope() as session:
        action = session.get(AssistantPendingAction, action_id)
        if not action:
            raise NotFoundError(f"Assistant action {action_id} not found")
        action.status = "rejected"
        action.resolved_at = _now()
        session.add(AssistantMessage(session_id=action.session_id, role="assistant", content="Rejected. I did not change any local strategy data.", tool_calls_json=[]))
        session.flush()
        return {"messages": _messages(session, action.session_id), "pending_actions": _pending(session, action.session_id)}


def _plan_action(message: str) -> dict | None:
    lowered = message.lower()

    # 1) Signal/rule strategy ("when the S&P hits a new high, buy SQQQ, exit +10% stop -3%")
    signal = _parse_signal_request(message)
    if signal:
        return {"kind": "write", "action": "create_strategy", "payload": signal}

    # 2) Backtest an existing strategy by name, optionally over a named regime/year.
    if "backtest" in lowered or "back-test" in lowered or "back test" in lowered:
        return {"kind": "backtest", "payload": {"message": message}}

    # 3) Assign/allocate an existing strategy to a trader profile.
    assignment = _parse_assignment_request(message)
    if assignment:
        return {"kind": "write", "action": "assign_strategy_to_account", "payload": assignment}

    # 4) Generic "create a <category> strategy named X for AAPL MSFT".
    if "create" in lowered and "strategy" in lowered:
        name_match = re.search(r"named\s+(.+?)\s+for\s+", message, flags=re.IGNORECASE)
        name = name_match.group(1).strip(" .") if name_match else "Assistant Strategy"
        after_for = message[name_match.end():] if name_match else message
        tickers = re.findall(r"\b[A-Z]{1,5}\b", after_for)
        return {
            "kind": "write",
            "action": "create_strategy",
            "payload": {
                "category": _category_from_text(lowered),
                "name": name,
                "description": "Assistant-proposed paper strategy for research simulation.",
                "history": "Created from a multi-turn assistant conversation.",
                "methodology": "Start with Atlas valuation, free cash flow quality, and daily trend checks.",
                "parameters": {"tickers": tickers or ["SPY"], "lookback_days": 120, "max_positions": 5},
                "caveats": ["Assistant-generated idea; validate with backtests before use."],
            },
        }

    ticker = _first_ticker(message)
    if ticker and any(term in lowered for term in ["valuation", "fair value", "margin of safety"]):
        return {"kind": "read", "action": "get_valuation", "payload": {"ticker": ticker}}
    if ticker and any(term in lowered for term in ["cash flow", "fcf", "capex", "profitability"]):
        return {"kind": "read", "action": "get_cash_flow_analysis", "payload": {"ticker": ticker}}
    if "list" in lowered and "strateg" in lowered:
        return {"kind": "read", "action": "list_strategies", "payload": {}}
    return None


def _category_from_text(lowered: str) -> str:
    for kw, cat in [("short sell", "short_selling"), ("short-sell", "short_selling"), ("option", "options"),
                    ("dividend", "income_quality"), ("income", "income_quality"), ("rotat", "risk_rotation"),
                    ("hedge", "risk_rotation"), ("momentum", "short_term"), ("swing", "short_term"),
                    ("short term", "short_term"), ("long term", "long_term")]:
        if kw in lowered:
            return cat
    return "long_term"


def _parse_assignment_request(message: str) -> dict | None:
    lowered = message.lower()
    if not any(term in lowered for term in ("assign", "allocate", "add")):
        return None
    weight_match = re.search(r"\b(\d+(?:\.\d+)?)\s*%", message)
    if not weight_match:
        return None
    before_weight = message[:weight_match.start()].strip(" .")
    before_weight = re.sub(r"\b(?:at|with|for)\s*$", "", before_weight, flags=re.IGNORECASE).strip(" .")
    match = re.search(
        r"\b(?:assign|allocate|add)\b\s+(?:the\s+)?(?:(?:model|strategy)\s+)?(.+?)\s+"
        r"(?:to|into|for)\s+(?:the\s+)?(?:(?:trader|profile|account)\s+)?(.+)$",
        before_weight,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    strategy_name = match.group(1).strip(" .\"“”")
    account_name = match.group(2).strip(" .\"“”")
    if not strategy_name or not account_name:
        return None
    weight = float(weight_match.group(1))
    return {
        "name": f"Assign {strategy_name} to {account_name}",
        "strategy_name": strategy_name,
        "account_name": account_name,
        "weight": weight,
    }


_PROFIT_KW = ("profit", "gain", "target", "upside", "exit")
_STOP_KW = ("stop", "loss", "downside", "risk")


def _extract_tp_sl(message: str, exclude: list[tuple[int, int]] | None = None) -> tuple[float | None, float | None]:
    """Assign each percentage to take-profit or stop-loss.

    A keyword immediately *preceding* the number owns it ("take profit 8%",
    "stop loss 4%"); a following keyword is the fallback ("exit at 10% gains").
    """
    low = message.lower()
    spans: list[tuple[str, int, int]] = []
    spans += [("tp", m.start(), m.end()) for kw in _PROFIT_KW for m in re.finditer(re.escape(kw), low)]
    spans += [("sl", m.start(), m.end()) for kw in _STOP_KW for m in re.finditer(re.escape(kw), low)]
    exclude = exclude or []
    tp = sl = None
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%", message):
        ns, ne = m.start(), m.end()
        if any(s <= ns < e for s, e in exclude):
            continue
        left = [(ns - ke, kind) for kind, ks, ke in spans if ke <= ns and ns - ke <= 25]
        right = [(ks - ne, kind) for kind, ks, ke in spans if ks >= ne and ks - ne <= 15]
        kind = min(left)[1] if left else (min(right)[1] if right else None)
        if kind is None:
            continue
        val = float(m.group(1)) / 100
        if kind == "tp" and tp is None:
            tp = val
        elif kind == "sl" and sl is None:
            sl = val
    return tp, sl


def _parse_signal_request(message: str) -> dict | None:
    """Turn a natural-language signal idea into a rule-based create_strategy payload."""
    lo = message.lower()
    if any(p in lo for p in ["all-time high", "all time high", "new high", "record high", "52-week high", "52 week high"]):
        stype, cat = "new_high", "risk_rotation"
    elif any(p in lo for p in ["all-time low", "all time low", "new low", "record low"]):
        stype, cat = "new_low", "short_term"
    elif "golden cross" in lo or ("cross" in lo and ("moving average" in lo or "sma" in lo or "ma " in lo)):
        stype, cat = "ma_cross_up", "short_term"
    elif re.search(r"(drop|fall|declin|dip|sell[- ]?off|down)\w*\s+(?:by\s+)?\d+(?:\.\d+)?\s*%", lo):
        stype, cat = "pct_drop", "short_term"
    else:
        return None

    # Require an explicit exit so we don't hijack casual chatter.
    if not any(k in lo for k in ["stop", "exit", "take profit", "take-profit", "target", "profit", "gain"]):
        return None

    instrument = None
    paren = re.search(r"\(([^)]*\b[A-Z]{2,5}\b[^)]*)\)", message)
    if paren:
        t = re.search(r"\b[A-Z]{2,5}\b", paren.group(1))
        instrument = t.group(0) if t else None
    if not instrument:
        # match buy/buys/buying/short/shorts/purchase(s)/long(s) + TICKER
        m2 = re.search(r"\b(?:buy|short|purchas|long|own|into)\w*\s+(?:the\s+)?(?:inverse\s+(?:of\s+)?)?([A-Z]{2,5})\b", message)
        instrument = m2.group(1) if m2 else None
    if not instrument:
        for t in re.findall(r"\b[A-Z]{2,5}\b", message):
            if t in INVERSE_ETFS:
                instrument = t
                break
    if not instrument:
        return None

    matched_index = next((sym for key, sym in _INDEX_REF if key in lo), None)
    if stype in ("new_high", "new_low"):
        reference = matched_index or "^GSPC"
    elif stype == "ma_cross_up":
        reference = instrument  # a crossover is measured on the instrument you trade
    else:  # pct_drop — the dip is on the named index, else the instrument itself
        reference = matched_index or instrument

    direction = "short" if re.search(r"\bshort(?:s|ing)?\b", lo) else "long"
    signal: dict[str, Any] = {"type": stype, "reference": reference}
    exclude: list[tuple[int, int]] = []
    if stype == "pct_drop":
        dm = re.search(r"(?:drop|fall|declin|dip|down|sell[- ]?off)\w*\s+(?:by\s+)?(\d+(?:\.\d+)?)\s*%", message, re.IGNORECASE)
        if dm:
            signal["pct"] = float(dm.group(1)) / 100
            exclude.append((dm.start(1), dm.end()))
        else:
            signal["pct"] = 0.05
    tp, sl = _extract_tp_sl(message, exclude)
    tp = tp or 0.10
    sl = sl or 0.05

    ref_label = _REF_LABEL.get(reference, reference)
    sig_label = _SIGNAL_LABEL.get(stype, "signal")
    verb = "Shorts" if direction == "short" else "Buys"
    self_ref = reference == instrument
    subject = "its own" if self_ref else f"the {ref_label}"
    name = f"{instrument} {sig_label.title()}" if self_ref else f"{instrument} on {ref_label} {sig_label.title()}"
    rules = {
        "instrument": instrument, "direction": direction, "signal": signal,
        "take_profit_pct": tp, "stop_loss_pct": sl,
    }
    return {
        "category": cat,
        "name": name[:120],
        "description": f"{verb} {instrument} on {subject} {sig_label}; exits at +{tp * 100:.0f}% or −{sl * 100:.0f}%.",
        "history": "Created from a natural-language idea in the Atlas Copilot.",
        "methodology": (
            f"Signal: {subject} {sig_label}. {verb} {instrument}, take profit at +{tp * 100:.0f}%, "
            f"stop loss at −{sl * 100:.0f}%. Backtest it in the Backtest tab to validate."
        ),
        "parameters": {"tickers": [instrument], "rules": rules},
        "caveats": [
            "Research simulation only; not financial advice.",
            "Validate with a backtest before relying on it — signal rules can whipsaw.",
        ],
    }


def _confirm_prompt(payload: dict) -> str:
    if payload.get("strategy_name") and payload.get("account_name"):
        return (
            f"I can assign “{payload['strategy_name']}” to “{payload['account_name']}” "
            f"at {payload.get('weight')}% of capital. Confirm below and I'll update that simulated trader profile."
        )
    extra = f" {payload['methodology']}" if payload.get("methodology") else ""
    return (
        f"I can set up “{payload['name']}” for you.{extra} "
        "Confirm below and I'll add it to your models — then open the Backtest tab to test it."
    )


def _resolve_strategy(message: str) -> dict | None:
    """Pick the active strategy whose name best overlaps the message."""
    strategies = paper_service.list_strategies().get("strategies", [])
    lo = message.lower()
    best, best_score = None, 0
    for s in strategies:
        words = [w for w in re.split(r"[^a-z0-9]+", s["name"].lower()) if len(w) > 2]
        score = sum(1 for w in words if w in lo)
        if score > best_score:
            best, best_score = s, score
    return best


def _backtest_window(message: str) -> tuple[date, date, str]:
    lo = message.lower()
    if any(k in lo for k in ["gfc", "financial crisis", "2008", "2009"]):
        return date(2006, 6, 1), date(2009, 12, 31), "2006–2009 (GFC)"
    if any(k in lo for k in ["covid", "pandemic", "2020"]):
        return date(2019, 6, 1), date(2021, 6, 30), "2019–2021 (COVID)"
    if any(k in lo for k in ["rate shock", "bear", "2022"]):
        return date(2022, 1, 1), date(2022, 12, 31), "2022 (bear market)"
    if any(k in lo for k in ["bull", "2013", "2014", "2015", "2016", "2017"]):
        return date(2013, 1, 1), date(2017, 12, 31), "2013–2017 (bull market)"
    yr = re.search(r"\b(?:19|20)\d{2}\b", message)
    if yr:
        y = int(yr.group(0))
        return date(y, 1, 1), date(y, 12, 31), str(y)
    today = date.today()
    return date(today.year - 3, today.month, 1), today, "the last 3 years"


def _run_backtest_reply(message: str) -> str:
    target = _resolve_strategy(message)
    if not target:
        return (
            "Which strategy should I backtest? Name one of your models (e.g. “S&P High Fade”) "
            "and optionally a period like 2008, COVID, 2022, or a single year."
        )
    start, end, label = _backtest_window(message)
    try:
        result = execute_read_tool("run_backtest", {
            "strategy_id": target["id"],
            "tickers": target.get("parameters", {}).get("tickers", []),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "benchmark": "SPY",
        })
    except Exception as exc:  # noqa: BLE001 — surface a friendly message
        return f"I couldn't backtest “{target['name']}” over {label}: {exc}"
    run = result.get("run", {})
    m = run.get("metrics", {})
    trades = run.get("trades", [])
    warnings = run.get("warnings", [])
    tot = (m.get("total_return") or 0) * 100
    dd = (m.get("max_drawdown") or 0) * 100
    parts = [f"Backtest — {target['name']} over {label}: total return {tot:+.1f}%, max drawdown {dd:.1f}%, {len(trades)} trades"]
    if m.get("win_rate") is not None:
        parts.append(f", win rate {m['win_rate'] * 100:.0f}%")
    summary = "".join(parts) + "."
    if warnings:
        summary += " " + " ".join(warnings[:2])
    summary += " Open the Backtest tab to see the equity curve and trade-by-trade fills."
    return summary


def _first_ticker(message: str) -> str | None:
    ignored = {"FCF", "DCF", "AI", "API", "ETF", "SEC"}
    for token in re.findall(r"\b[A-Z]{1,5}\b", message):
        if token not in ignored:
            return token
    return None


def _summarize_tool(action: str, result: dict) -> str:
    if action == "get_valuation":
        fair = result.get("blended_fair_value") or result.get("blended", {}).get("blended_fair_value")
        return f"Atlas valuation data is available. Blended fair value: {fair}. Treat this as a model output, not advice."
    if action == "get_cash_flow_analysis":
        periods = result.get("periods", [])
        latest = periods[0] if periods else {}
        return f"Latest cash-flow snapshot: FCF {latest.get('free_cash_flow')}, FCF margin {latest.get('fcf_margin')}. Data source: {result.get('served_by')}."
    if action == "list_strategies":
        count = len(result.get("strategies", []))
        return f"You currently have {count} active paper-trading strategies available to clone, tune, backtest, or run."
    return "I queried Atlas data and added the result to this conversation."


def _llm_reply(messages: list[dict]) -> str:
    if not settings.openai_api_key:
        return (
            "I can help discuss strategy ideas, valuation assumptions, FCF quality, profitability, capex, "
            "and backtests. Add `OPENAI_API_KEY` to enable richer OpenAI responses. Research only; not advice."
        )
    payload = {
        "model": settings.openai_model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages[-12:],
        "temperature": 0.2,
    }
    try:
        with httpx.Client(timeout=30) as client:
            res = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            res.raise_for_status()
            return res.json()["choices"][0]["message"]["content"]
    except Exception:
        return "I could not reach the OpenAI model, but your Atlas data and local assistant tools are still available."


def _session_view(row: AssistantSession) -> dict:
    return {"id": row.id, "title": row.title, "summary": row.summary or "", "created_at": row.created_at.isoformat()}


def _messages(session, session_id: int) -> list[dict]:
    rows = session.query(AssistantMessage).filter_by(session_id=session_id).order_by(AssistantMessage.created_at.asc(), AssistantMessage.id.asc()).all()
    return [{"id": row.id, "role": row.role, "content": row.content, "tool_calls": row.tool_calls_json or []} for row in rows]


def _pending(session, session_id: int) -> list[dict]:
    rows = session.query(AssistantPendingAction).filter_by(session_id=session_id, status="pending").order_by(AssistantPendingAction.created_at.asc()).all()
    return [{"id": row.id, "action": row.action, "payload": row.payload_json or {}, "status": row.status} for row in rows]
