"""Research assistant service with persisted memory and confirmed tool calls."""
from __future__ import annotations

import re
import json
from datetime import date
from typing import Any

import httpx

from ..core.config import settings
from ..core.errors import NotFoundError, ValidationError
from ..db import _now, session_scope
from ..models.assistant import AssistantMessage, AssistantPendingAction, AssistantSession
from ..paper_trading import accounts as account_service
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
        return {"session": _session_view(row), "messages": [], "pending_actions": [], "actions": []}


def get_session(session_id: int) -> dict:
    with session_scope() as session:
        row = session.get(AssistantSession, session_id)
        if not row:
            raise NotFoundError(f"Assistant session {session_id} not found")
        return {
            "session": _session_view(row),
            "messages": _messages(session, session_id),
            "pending_actions": _pending(session, session_id),
            "actions": _actions(session, session_id),
        }


def add_message(session_id: int, payload: MessageCreate) -> dict:
    with session_scope() as session:
        row = session.get(AssistantSession, session_id)
        if not row:
            raise NotFoundError(f"Assistant session {session_id} not found")
        user = AssistantMessage(session_id=session_id, role="user", content=payload.message, tool_calls_json=[])
        session.add(user)
        session.flush()
        source_message_id = user.id
        session.commit()
        tool_calls: list[dict[str, Any]] = []
        resumed = _resume_workflow_plan(session, row, payload.message, source_message_id=source_message_id)
        planned = None if resumed else _plan_action(payload.message)
        if resumed:
            content = resumed["content"]
            tool_calls = resumed["tool_calls"]
        elif planned and planned["kind"] == "write":
            payload_with_context = _attach_assistant_context(planned["action"], planned["payload"], session_id=session_id, source_message_id=source_message_id)
            pending_payload = _pending_payload(planned["action"], payload_with_context)
            action = AssistantPendingAction(session_id=session_id, action=planned["action"], payload_json=pending_payload)
            session.add(action)
            content = _confirm_prompt(planned["action"], pending_payload)
            tool_calls.append({"pending_action": planned["action"], "payload": pending_payload})
        elif planned and planned["kind"] == "backtest":
            content, call = _run_backtest_response(
                planned["payload"]["message"],
                assistant_context=_assistant_context(session_id=session_id, source_message_id=source_message_id),
            )
            tool_calls.append(call)
        elif planned and planned["kind"] == "read":
            result = execute_read_tool(planned["action"], planned["payload"])
            content = _summarize_tool(planned["action"], result)
            tool_calls.append({"tool": planned["action"], "payload": planned["payload"]})
        else:
            content = _llm_reply(_messages(session, session_id) + [{"role": "user", "content": payload.message}])
        session.add(AssistantMessage(session_id=session_id, role="assistant", content=content, tool_calls_json=tool_calls))
        row.updated_at = _now()
        session.flush()
        return {
            "session": _session_view(row),
            "messages": _messages(session, session_id),
            "pending_actions": _pending(session, session_id),
            "actions": _actions(session, session_id),
        }


def confirm_action(action_id: int) -> dict:
    with session_scope() as session:
        action = session.get(AssistantPendingAction, action_id)
        if not action:
            raise NotFoundError(f"Assistant action {action_id} not found")
        if action.status != "pending":
            raise ValidationError("Assistant action has already been resolved")
        payload = dict(action.payload_json or {})
        result = execute_write_tool(action.action, dict(payload))
        result_ref = _result_ref(action.action, result)
        payload["result_ref"] = result_ref
        action.payload_json = payload
        action.status = "confirmed"
        action.resolved_at = _now()
        row = session.get(AssistantSession, action.session_id)
        _append_action_memory(row, action.action, payload, result_ref)
        content = _confirmed_content(row, action.action, payload, result)
        session.add(AssistantMessage(session_id=action.session_id, role="assistant", content=content, tool_calls_json=[{"tool": action.action}]))
        session.flush()
        return {
            "result": result,
            "messages": _messages(session, action.session_id),
            "pending_actions": _pending(session, action.session_id),
            "actions": _actions(session, action.session_id),
        }


def reject_action(action_id: int) -> dict:
    with session_scope() as session:
        action = session.get(AssistantPendingAction, action_id)
        if not action:
            raise NotFoundError(f"Assistant action {action_id} not found")
        action.status = "rejected"
        action.resolved_at = _now()
        row = session.get(AssistantSession, action.session_id)
        content = _rejected_content(row, action.action, dict(action.payload_json or {}))
        session.add(AssistantMessage(session_id=action.session_id, role="assistant", content=content, tool_calls_json=[]))
        session.flush()
        return {
            "messages": _messages(session, action.session_id),
            "pending_actions": _pending(session, action.session_id),
            "actions": _actions(session, action.session_id),
        }


def _load_workflow_plan(row: AssistantSession | None) -> dict | None:
    if not row or not row.summary:
        return None
    try:
        plan = json.loads(row.summary)
    except (TypeError, ValueError):
        return None
    if isinstance(plan, dict) and plan.get("type") == "copilot_workflow_v1":
        return plan
    return None


def _store_workflow_plan(row: AssistantSession | None, plan: dict) -> None:
    if row is not None:
        row.summary = json.dumps(plan)


def _assistant_context(*, session_id: int, source_message_id: int) -> dict:
    return {
        "session_id": session_id,
        "source_message_id": source_message_id,
        "created_by": "atlas_copilot",
    }


def _attach_assistant_context(action: str, payload: dict, *, session_id: int, source_message_id: int) -> dict:
    enriched = dict(payload)
    context = _assistant_context(session_id=session_id, source_message_id=source_message_id)
    enriched["_assistant"] = context
    if action == "create_strategy":
        metrics = dict(enriched.get("metrics") or {})
        metrics["_assistant"] = context
        enriched["metrics"] = metrics
    return enriched


def _result_ref(action: str, result: dict) -> dict:
    if action in {"create_strategy", "update_strategy", "clone_strategy"} and result.get("strategy"):
        strategy = result["strategy"]
        return {"type": "strategy", "id": strategy.get("id"), "name": strategy.get("name")}
    if action == "delete_strategy":
        return {"type": "strategy", "id": result.get("deleted"), "status": "archived"}
    if action == "assign_strategy_to_account" and result.get("assigned"):
        assigned = result["assigned"]
        return {
            "type": "account_assignment",
            "account_id": assigned.get("account_id"),
            "account_name": assigned.get("account_name"),
            "strategy_id": assigned.get("strategy_id"),
            "strategy_name": assigned.get("strategy_name"),
            "weight": assigned.get("weight"),
        }
    if action == "rebalance_account" and result.get("account"):
        account = result["account"]
        return {"type": "account", "id": account.get("id"), "name": account.get("name"), "allocation_count": len(account.get("allocations", []))}
    if action == "create_portfolio" and result.get("portfolio"):
        portfolio = result["portfolio"]
        return {"type": "portfolio", "id": portfolio.get("id"), "name": portfolio.get("name")}
    return {"type": action, "status": "confirmed"}


def _session_memory(summary: str | None) -> dict:
    if not summary:
        return {}
    try:
        parsed = json.loads(summary)
    except (TypeError, ValueError):
        return {"text": summary}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _append_action_memory(row: AssistantSession | None, action: str, payload: dict, result_ref: dict) -> None:
    if row is None or payload.get("plan"):
        return
    memory = _session_memory(row.summary)
    if memory.get("type") not in {"assistant_session_summary_v1", None}:
        return
    if not memory:
        memory = {"type": "assistant_session_summary_v1", "actions": [], "models": [], "assignments": []}
    entry = {
        "action": action,
        "summary": payload.get("action_summary") or action.replace("_", " "),
        "source_message_id": (payload.get("_assistant") or {}).get("source_message_id"),
        "result_ref": result_ref,
    }
    memory.setdefault("actions", []).append(entry)
    if result_ref.get("type") == "strategy":
        memory.setdefault("models", []).append({"id": result_ref.get("id"), "name": result_ref.get("name"), "action": action})
    if result_ref.get("type") == "account_assignment":
        memory.setdefault("assignments", []).append(result_ref)
    row.summary = json.dumps(memory)


def _workflow_step_lines(plan: dict) -> str:
    labels = []
    for step in plan.get("steps", []):
        status = step.get("status", "pending")
        labels.append(f"- {step.get('label', step.get('action', 'Step'))}: {status.replace('_', ' ')}")
    return "\n".join(labels)


def _confirmed_content(row: AssistantSession | None, action: str, payload: dict, result: dict) -> str:
    plan_payload = payload.get("plan")
    if action == "create_strategy" and plan_payload and result.get("strategy"):
        strategy = result["strategy"]
        plan = dict(plan_payload)
        plan["strategy_id"] = strategy["id"]
        plan["strategy_name"] = strategy["name"]
        plan["tickers"] = strategy.get("parameters", {}).get("tickers", [])
        plan.setdefault("actions", []).append({
            "action": "create_strategy",
            "summary": payload.get("action_summary"),
            "source_message_id": (payload.get("_assistant") or {}).get("source_message_id"),
            "result_ref": payload.get("result_ref"),
        })
        plan.setdefault("models", []).append({
            "id": strategy["id"],
            "name": strategy["name"],
            "tickers": strategy.get("parameters", {}).get("tickers", []),
            "parameters": strategy.get("parameters", {}),
        })
        plan["status"] = "awaiting_backtest"
        for step in plan.get("steps", []):
            if step.get("action") == "create_strategy":
                step["status"] = "confirmed"
            elif step.get("action") == "run_backtest":
                step["status"] = "ready"
        _store_workflow_plan(row, plan)
        lines = _workflow_step_lines(plan)
        return (
            f"Confirmed. I created “{strategy['name']}”.\n\n"
            f"Plan status:\n{lines}\n\n"
            "Say “continue” when you want me to run the read-only backtest. "
            "The later assignment will still require its own confirmation."
        )
    if action == "assign_strategy_to_account" and plan_payload:
        plan = _load_workflow_plan(row) or dict(plan_payload)
        plan["status"] = "complete"
        if payload.get("result_ref"):
            plan.setdefault("actions", []).append({
                "action": "assign_strategy_to_account",
                "summary": payload.get("action_summary"),
                "source_message_id": (payload.get("_assistant") or {}).get("source_message_id"),
                "result_ref": payload.get("result_ref"),
            })
            plan.setdefault("assignments", []).append(payload["result_ref"])
        for step in plan.get("steps", []):
            if step.get("action") == "assign_strategy_to_account":
                step["status"] = "confirmed"
        _store_workflow_plan(row, plan)
        assigned = result.get("assigned", {})
        return (
            f"Confirmed. I assigned “{assigned.get('strategy_name', payload.get('strategy_name', 'the model'))}” "
            f"to “{assigned.get('account_name', payload.get('account_name', 'the profile'))}” "
            f"at {assigned.get('weight', payload.get('weight'))}% of simulated capital. The Copilot plan is complete."
        )
    return f"Confirmed. I executed `{action}` and updated the local paper-trading workspace."


def _rejected_content(row: AssistantSession | None, action: str, payload: dict) -> str:
    plan_payload = payload.get("plan")
    if plan_payload:
        plan = _load_workflow_plan(row) or dict(plan_payload)
        plan["status"] = f"{action}_rejected"
        for step in plan.get("steps", []):
            if step.get("action") == action:
                step["status"] = "rejected"
        _store_workflow_plan(row, plan)
        return "Rejected. I did not run that plan step or change additional local strategy data."
    return "Rejected. I did not change any local strategy data."


def _plan_action(message: str) -> dict | None:
    lowered = message.lower()

    workflow = _parse_workflow_request(message)
    if workflow:
        return {"kind": "write", "action": "create_strategy", "payload": workflow}

    # 1) Signal/rule strategy ("when the S&P hits a new high, buy SQQQ, exit +10% stop -3%")
    signal = _parse_signal_request(message)
    if signal:
        return {"kind": "write", "action": "create_strategy", "payload": signal}

    # 2) Backtest an existing strategy by name, optionally over a named regime/year.
    if "backtest" in lowered or "back-test" in lowered or "back test" in lowered:
        return {"kind": "backtest", "payload": {"message": message}}

    # 3) Account/profile reads and safe account lifecycle writes.
    performance = _parse_account_performance_request(message)
    if performance:
        return {"kind": "read", "action": "account_performance", "payload": performance}
    if any(term in lowered for term in ["list", "show"]) and any(term in lowered for term in ["profile", "profiles", "trader", "traders", "account", "accounts"]):
        return {"kind": "read", "action": "list_accounts", "payload": {}}
    rebalance = _parse_rebalance_request(message)
    if rebalance:
        return {"kind": "write", "action": "rebalance_account", "payload": rebalance}

    # 4) Clone an existing strategy before editing or experimentation.
    clone = _parse_clone_request(message)
    if clone:
        return {"kind": "write", "action": "clone_strategy", "payload": clone}

    # 5) Assign/allocate an existing strategy to a trader profile.
    assignment = _parse_assignment_request(message)
    if assignment:
        return {"kind": "write", "action": "assign_strategy_to_account", "payload": assignment}

    # 6) Generic "create a <category> strategy named X for AAPL MSFT".
    if "create" in lowered and "strategy" in lowered:
        return {"kind": "write", "action": "create_strategy", "payload": _parse_create_strategy_payload(message)}

    ticker = _first_ticker(message)
    if ticker and any(term in lowered for term in ["valuation", "fair value", "margin of safety"]):
        return {"kind": "read", "action": "get_valuation", "payload": {"ticker": ticker}}
    if ticker and any(term in lowered for term in ["cash flow", "fcf", "capex", "profitability"]):
        return {"kind": "read", "action": "get_cash_flow_analysis", "payload": {"ticker": ticker}}
    if "list" in lowered and "strateg" in lowered:
        return {"kind": "read", "action": "list_strategies", "payload": {}}
    return None


def _parse_create_strategy_payload(message: str) -> dict:
    lowered = message.lower()
    name_match = re.search(r"named\s+(.+?)\s+for\s+", message, flags=re.IGNORECASE)
    name = name_match.group(1).strip(" .") if name_match else "Assistant Strategy"
    after_for = message[name_match.end():] if name_match else message
    tickers = re.findall(r"\b[A-Z]{1,5}\b", after_for)
    return {
        "category": _category_from_text(lowered),
        "name": name,
        "description": "Assistant-proposed paper strategy for research simulation.",
        "history": "Created from a multi-turn assistant conversation.",
        "methodology": "Start with Atlas valuation, free cash flow quality, and daily trend checks.",
        "parameters": {"tickers": tickers or ["SPY"], "lookback_days": 120, "max_positions": 5},
        "caveats": ["Assistant-generated idea; validate with backtests before use."],
    }


def _parse_workflow_request(message: str) -> dict | None:
    lowered = message.lower()
    if not ("create" in lowered and "strategy" in lowered):
        return None
    has_backtest = any(term in lowered for term in ["backtest", "back-test", "back test"])
    has_assignment = any(term in lowered for term in ["assign", "allocate", "add to", "add it to"])
    if not (has_backtest or has_assignment):
        return None

    payload = _parse_create_strategy_payload(message)
    steps = [{"action": "create_strategy", "kind": "write", "label": f"Create “{payload['name']}”", "status": "pending_confirmation"}]
    start, end, label = _backtest_window(message)
    if has_backtest:
        steps.append({"action": "run_backtest", "kind": "read", "label": f"Backtest over {label}", "status": "blocked"})
    account = _resolve_account(message) if has_assignment else None
    weight_match = list(re.finditer(r"\b(\d+(?:\.\d+)?)\s*%", message))
    assignment = None
    if account and weight_match:
        assignment = {"account_name": account["name"], "weight": float(weight_match[-1].group(1))}
        steps.append({
            "action": "assign_strategy_to_account",
            "kind": "write",
            "label": f"Assign to “{account['name']}” at {assignment['weight']}%",
            "status": "blocked",
        })

    if len(steps) == 1:
        return None

    payload["plan"] = {
        "type": "copilot_workflow_v1",
        "status": "awaiting_create_confirmation",
        "original_request": message,
        "strategy_name": payload["name"],
        "tickers": payload.get("parameters", {}).get("tickers", []),
        "backtest": {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "label": label,
            "benchmark": "SPY",
        },
        "assignment": assignment,
        "steps": steps,
    }
    return payload


def _tokens(value: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9]+", value.lower()) if len(part) > 1}


def _best_item_match(rows: list[dict], text: str) -> dict | None:
    needle = " ".join(text.strip().lower().split())
    if not needle:
        return None
    for row in rows:
        if " ".join(str(row.get("name", "")).lower().split()) == needle:
            return row
    wanted = _tokens(needle)
    best, best_score = None, 0
    for row in rows:
        score = len(wanted & _tokens(str(row.get("name", ""))))
        if score > best_score:
            best, best_score = row, score
    return best if best_score else None


def _resolve_account(message: str) -> dict | None:
    return _best_item_match(account_service.list_accounts().get("accounts", []), message)


def _parse_account_performance_request(message: str) -> dict | None:
    lowered = message.lower()
    if not any(term in lowered for term in ["performance", "return", "risk", "drawdown", "attribution"]):
        return None
    if not any(term in lowered for term in ["profile", "trader", "account"]):
        return None
    account = _resolve_account(message)
    if not account:
        return None
    return {"account_id": account["id"], "account_name": account["name"]}


def _parse_clone_request(message: str) -> dict | None:
    lowered = message.lower()
    if not any(term in lowered for term in ["clone", "copy", "duplicate"]):
        return None
    if not any(term in lowered for term in ["strategy", "model"]):
        return None
    target = _resolve_strategy(message)
    if not target:
        return None
    return {
        "name": f"Clone {target['name']}",
        "strategy_id": target["id"],
        "strategy_name": target["name"],
    }


def _parse_rebalance_request(message: str) -> dict | None:
    lowered = message.lower()
    if "rebalance" not in lowered:
        return None
    account = _resolve_account(message)
    if not account:
        return None
    strategies = paper_service.list_strategies().get("strategies", [])
    allocations = []
    pattern = re.compile(
        r"(\d+(?:\.\d+)?)\s*%\s*(?:to|in|on|into)?\s*([^,;]+?)(?=\s+(?:and\s+)?\d+(?:\.\d+)?\s*%|[,;]|$)",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(message):
        weight = float(match.group(1))
        target_text = match.group(2).strip(" .\"“”")
        strategy = _best_item_match(strategies, target_text)
        if strategy:
            allocations.append({
                "strategy_id": strategy["id"],
                "strategy_name": strategy["name"],
                "weight": weight,
            })
    if not allocations:
        return None
    return {
        "name": f"Rebalance {account['name']}",
        "account_id": account["id"],
        "account_name": account["name"],
        "allocations": allocations,
    }


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


def _pending_payload(action: str, payload: dict) -> dict:
    enriched = dict(payload)
    enriched.setdefault("action_summary", _action_summary(action, enriched))
    details = _action_details(action, enriched)
    if details:
        enriched.setdefault("action_details", details)
    return enriched


def _action_summary(action: str, payload: dict) -> str:
    if action == "create_strategy":
        return f"Create model “{payload.get('name', 'Assistant Strategy')}”"
    if action == "clone_strategy":
        return f"Clone model “{payload.get('strategy_name', payload.get('strategy_id', 'selected strategy'))}”"
    if action == "assign_strategy_to_account":
        return (
            f"Assign “{payload.get('strategy_name', 'strategy')}” to "
            f"“{payload.get('account_name', 'profile')}” at {payload.get('weight')}%"
        )
    if action == "rebalance_account":
        return f"Rebalance “{payload.get('account_name', 'profile')}”"
    if action == "update_strategy":
        return f"Update model “{payload.get('strategy_name', payload.get('strategy_id', 'selected strategy'))}”"
    if action == "delete_strategy":
        return f"Archive model “{payload.get('strategy_name', payload.get('strategy_id', 'selected strategy'))}”"
    if action == "create_portfolio":
        return f"Create portfolio “{payload.get('name', 'Assistant Portfolio')}”"
    return f"Run {action.replace('_', ' ')}"


def _action_details(action: str, payload: dict) -> str:
    if action == "create_strategy":
        tickers = ", ".join(payload.get("parameters", {}).get("tickers", []) or [])
        category = str(payload.get("category", "")).replace("_", " ")
        parts = [category.title() if category else "", tickers]
        plan = payload.get("plan")
        if plan:
            labels = [step.get("label", step.get("action", "")) for step in plan.get("steps", [])[1:]]
            if labels:
                parts.append("Next: " + "; ".join(labels))
        return " · ".join(part for part in parts if part)
    if action == "rebalance_account":
        rows = payload.get("allocations", [])
        labels = [f"{row.get('weight')}% {row.get('strategy_name', row.get('strategy_id'))}" for row in rows]
        return ", ".join(labels)
    if action == "clone_strategy":
        return "The copy will be editable while the original model remains unchanged."
    if action == "assign_strategy_to_account":
        return "This changes only the local simulated trader profile allocation."
    return ""


def _confirm_prompt(action: str, payload: dict) -> str:
    if payload.get("strategy_name") and payload.get("account_name"):
        return (
            f"I can assign “{payload['strategy_name']}” to “{payload['account_name']}” "
            f"at {payload.get('weight')}% of capital. Confirm below and I'll update that simulated trader profile."
        )
    if action == "create_strategy" and payload.get("plan"):
        return (
            f"I can start this plan by creating “{payload.get('name', 'the model')}”. "
            "Confirm below to create only the model. After that, I can run the read-only backtest, "
            "and any assignment will require a separate confirmation."
        )
    if action == "clone_strategy":
        return (
            f"I can clone “{payload.get('strategy_name', 'this model')}” into an editable copy. "
            "Confirm below and I'll create the new local model."
        )
    if action == "rebalance_account":
        details = payload.get("action_details")
        suffix = f" Target allocation: {details}." if details else ""
        return f"I can rebalance “{payload.get('account_name', 'this profile')}”.{suffix} Confirm below before I update the profile."
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


def _resume_intent(message: str) -> bool:
    lowered = message.lower()
    return any(term in lowered for term in ["continue", "next", "resume", "retry", "run the backtest", "backtest it", "backtest the model"])


def _run_backtest_for_target(
    target: dict,
    start: date,
    end: date,
    label: str,
    *,
    assistant_context: dict | None = None,
) -> tuple[str, dict | None, dict]:
    payload = {
        "strategy_id": target["id"],
        "tickers": target.get("parameters", {}).get("tickers", []),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "benchmark": "SPY",
    }
    if assistant_context:
        payload["assistant_context"] = assistant_context
    try:
        result = execute_read_tool("run_backtest", payload)
    except Exception as exc:  # noqa: BLE001 — surface a friendly message
        return f"I couldn't backtest “{target['name']}” over {label}: {exc}", None, payload
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
    return summary, result, payload


def _resume_workflow_plan(session, row: AssistantSession, message: str, *, source_message_id: int) -> dict | None:
    plan = _load_workflow_plan(row)
    if not plan or not _resume_intent(message):
        return None
    if plan.get("status") == "awaiting_assignment_confirmation":
        return {
            "content": "The next plan step is already waiting for confirmation. Confirm or reject the pending assignment before I continue.",
            "tool_calls": [],
        }
    if plan.get("status") not in {"awaiting_backtest", "backtest_failed"}:
        return {
            "content": "There is no ready Copilot plan step to resume. Ask me for the next model, backtest, or assignment you want to run.",
            "tool_calls": [],
        }

    bt = plan.get("backtest") or {}
    target = {
        "id": plan["strategy_id"],
        "name": plan.get("strategy_name", "the model"),
        "parameters": {"tickers": plan.get("tickers", [])},
    }
    start = date.fromisoformat(bt["start_date"])
    end = date.fromisoformat(bt["end_date"])
    label = bt.get("label", f"{bt['start_date']} to {bt['end_date']}")
    content, result, payload = _run_backtest_for_target(
        target,
        start,
        end,
        label,
        assistant_context=_assistant_context(session_id=row.id, source_message_id=source_message_id),
    )
    tool_calls: list[dict[str, Any]] = [{"tool": "run_backtest", "payload": payload}]
    if result is None:
        plan["status"] = "backtest_failed"
        for step in plan.get("steps", []):
            if step.get("action") == "run_backtest":
                step["status"] = "failed_retryable"
        _store_workflow_plan(row, plan)
        return {
            "content": content + " You can adjust the model data and say “retry” to run this plan step again.",
            "tool_calls": tool_calls,
        }

    run = result.get("run", {})
    plan["status"] = "backtest_complete"
    plan["backtest_run_id"] = run.get("id")
    run_ref = {
        "type": "backtest_run",
        "id": run.get("id"),
        "strategy_id": plan.get("strategy_id"),
        "strategy_name": plan.get("strategy_name"),
        "window": run.get("start_date") and {"start": run.get("start_date"), "end": run.get("end_date")},
    }
    tool_calls[0]["result_ref"] = run_ref
    plan.setdefault("actions", []).append({
        "action": "run_backtest",
        "summary": f"Backtest “{plan.get('strategy_name', 'model')}”",
        "source_message_id": source_message_id,
        "result_ref": run_ref,
    })
    plan.setdefault("backtests", []).append(run_ref)
    for step in plan.get("steps", []):
        if step.get("action") == "run_backtest":
            step["status"] = "complete"

    assignment = plan.get("assignment")
    if assignment:
        assign_payload = _pending_payload("assign_strategy_to_account", {
            "name": f"Assign {plan['strategy_name']} to {assignment['account_name']}",
            "strategy_name": plan["strategy_name"],
            "account_name": assignment["account_name"],
            "weight": assignment["weight"],
            "plan": plan,
            "_assistant": _assistant_context(session_id=row.id, source_message_id=source_message_id),
        })
        session.add(AssistantPendingAction(session_id=row.id, action="assign_strategy_to_account", payload_json=assign_payload))
        plan["status"] = "awaiting_assignment_confirmation"
        for step in plan.get("steps", []):
            if step.get("action") == "assign_strategy_to_account":
                step["status"] = "pending_confirmation"
        _store_workflow_plan(row, plan)
        content += (
            "\n\nNext planned write: assign the model to the profile. "
            "I staged that as a separate confirmation below so the backtest approval does not imply allocation approval."
        )
        tool_calls.append({"pending_action": "assign_strategy_to_account", "payload": assign_payload})
    else:
        plan["status"] = "complete"
        _store_workflow_plan(row, plan)
        content += "\n\nThe Copilot plan is complete."
    return {"content": content, "tool_calls": tool_calls}


def _run_backtest_response(message: str, *, assistant_context: dict | None = None) -> tuple[str, dict]:
    target = _resolve_strategy(message)
    if not target:
        return (
            "Which strategy should I backtest? Name one of your models (e.g. “S&P High Fade”) "
            "and optionally a period like 2008, COVID, 2022, or a single year."
        ), {"tool": "run_backtest", "error": "strategy_not_resolved"}
    start, end, label = _backtest_window(message)
    content, result, payload = _run_backtest_for_target(target, start, end, label, assistant_context=assistant_context)
    call = {"tool": "run_backtest", "payload": payload}
    if result and result.get("run"):
        run = result["run"]
        call["result_ref"] = {
            "type": "backtest_run",
            "id": run.get("id"),
            "strategy_id": run.get("strategy_id"),
            "strategy_name": target.get("name"),
            "window": {"start": run.get("start_date"), "end": run.get("end_date")},
        }
    return content, call


def _run_backtest_reply(message: str) -> str:
    content, _ = _run_backtest_response(message)
    return content


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
    if action == "list_accounts":
        accounts = result.get("accounts", [])
        names = ", ".join(account.get("name", "Unnamed") for account in accounts[:6])
        suffix = f": {names}" if names else "."
        return f"You currently have {len(accounts)} active simulated trader profiles{suffix}"
    if action == "get_account":
        account = result.get("account", {})
        allocs = account.get("allocations", [])
        invested = account.get("invested_pct", 0)
        return f"{account.get('name', 'This profile')} has {len(allocs)} strategy allocation(s), {invested}% invested, and {account.get('cash_pct', 0)}% in simulated cash."
    if action == "account_performance":
        account = result.get("account", {})
        total = (result.get("total_return") or 0) * 100
        drawdown = abs((result.get("max_drawdown") or 0) * 100)
        top = result.get("attribution", {}).get("top_contributors", [])
        leader = f" Top contributor: {top[0]['name']} ({top[0]['pnl']:+.0f})." if top else ""
        return f"{account.get('name', 'This profile')} returned {total:+.1f}% over the selected window with a {drawdown:.1f}% max drawdown.{leader}"
    if action == "rebalance_preview":
        preview = result.get("preview", {})
        orders = preview.get("orders", [])
        return f"Rebalance preview ready: {len(orders)} simulated order adjustment(s), target cash {preview.get('target_cash_pct')}%."
    if action == "validate_strategy":
        issues = result.get("issues", [])
        warnings = result.get("warnings", [])
        if issues:
            return f"The strategy draft is not valid yet: {issues[0]}"
        if warnings:
            return f"The strategy draft is valid with a warning: {warnings[0]}"
        return "The strategy draft is valid and ready to save after confirmation."
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
    return {
        "id": row.id,
        "title": row.title,
        "summary": row.summary or "",
        "memory": _session_memory(row.summary),
        "created_at": row.created_at.isoformat(),
    }


def _messages(session, session_id: int) -> list[dict]:
    rows = session.query(AssistantMessage).filter_by(session_id=session_id).order_by(AssistantMessage.created_at.asc(), AssistantMessage.id.asc()).all()
    return [{"id": row.id, "role": row.role, "content": row.content, "tool_calls": row.tool_calls_json or []} for row in rows]


def _pending(session, session_id: int) -> list[dict]:
    rows = session.query(AssistantPendingAction).filter_by(session_id=session_id, status="pending").order_by(AssistantPendingAction.created_at.asc()).all()
    return [{"id": row.id, "action": row.action, "payload": row.payload_json or {}, "status": row.status} for row in rows]


def _actions(session, session_id: int) -> list[dict]:
    rows = (
        session.query(AssistantPendingAction)
        .filter_by(session_id=session_id)
        .order_by(AssistantPendingAction.created_at.asc(), AssistantPendingAction.id.asc())
        .all()
    )
    actions = []
    for row in rows:
        payload = row.payload_json or {}
        context = payload.get("_assistant") or {}
        actions.append({
            "id": row.id,
            "action": row.action,
            "status": row.status,
            "summary": payload.get("action_summary") or row.action.replace("_", " "),
            "details": payload.get("action_details") or "",
            "source_message_id": context.get("source_message_id"),
            "result_ref": payload.get("result_ref"),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        })
    return actions
