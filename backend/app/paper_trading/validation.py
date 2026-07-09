"""Validation helpers for user-authored paper-trading strategies."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..core.errors import ValidationError
from .schemas import Category, normalize_tickers


RULE_SIGNAL_TYPES = {"new_high", "new_low", "pct_drop", "pct_gain", "ma_cross_up", "ma_cross_down"}
LONG_ONLY_RULE_FAMILIES = {"long_term", "income_quality", "risk_rotation"}
VALID_DIRECTIONS = {"long", "short"}


def _issue(field: str, code: str, message: str) -> dict[str, str]:
    return {"field": field, "code": code, "message": message}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pct(
    *,
    value: Any,
    fallback: float | None,
    field: str,
    label: str,
    issues: list[dict[str, str]],
    maximum: float = 1.0,
    required: bool = True,
) -> float | None:
    if value is None or value == "":
        if required:
            issues.append(_issue(field, "required", f"{label} is required."))
        return fallback

    parsed = _float(value)
    if parsed is None:
        issues.append(_issue(field, "invalid_number", f"{label} must be a number."))
        return fallback

    normalized = parsed / 100 if parsed > 1 else parsed
    if normalized <= 0 or normalized > maximum:
        pct_max = int(maximum * 100)
        issues.append(_issue(field, "out_of_range", f"{label} must be greater than 0% and no more than {pct_max}%."))
    return normalized


def _bounded_int(
    *,
    value: Any,
    fallback: int | None,
    field: str,
    label: str,
    issues: list[dict[str, str]],
    minimum: int,
    maximum: int,
    required: bool = False,
) -> int | None:
    if value is None or value == "":
        if required:
            issues.append(_issue(field, "required", f"{label} is required."))
        return fallback

    parsed = _int(value)
    if parsed is None:
        issues.append(_issue(field, "invalid_number", f"{label} must be a whole number."))
        return fallback

    if parsed < minimum or parsed > maximum:
        issues.append(_issue(field, "out_of_range", f"{label} must be between {minimum} and {maximum}."))
    return parsed


def _validate_options_profile(params: dict[str, Any], issues: list[dict[str, str]]) -> None:
    profile = params.get("synthetic_options")
    if not isinstance(profile, dict):
        issues.append(_issue(
            "parameters.synthetic_options",
            "required",
            "Options rule strategies need a synthetic options profile that states the proxy assumption.",
        ))
        return
    if not str(profile.get("style") or "").strip():
        issues.append(_issue("parameters.synthetic_options.style", "required", "Synthetic options style is required."))
    if not str(profile.get("underlying") or "").strip():
        issues.append(_issue("parameters.synthetic_options.underlying", "required", "Synthetic options underlying is required."))
    if not str(profile.get("assumption") or "").strip():
        issues.append(_issue("parameters.synthetic_options.assumption", "required", "Synthetic options assumption is required."))


def _validation_result(params: dict[str, Any], issues: list[dict[str, str]]) -> dict[str, Any]:
    return {"valid": not issues, "issues": issues, "warnings": [], "parameters": params}


def _validate_catalogue_config(
    params: dict[str, Any],
    tickers: list[str],
    issues: list[dict[str, str]],
) -> None:
    model = str(params.get("model") or "").strip().lower()
    if model:
        from ..backtesting.screen import MODELS  # late import — avoids module cycles
        if model not in MODELS:
            issues.append(_issue(
                "parameters.model",
                "invalid_choice",
                f"Model '{model}' is not in the model library ({', '.join(sorted(MODELS))}).",
            ))
        params["model"] = model
        # Index-scanning models need no tickers; fixed baskets must declare their members.
        if str(params.get("universe") or "").lower() in {"tickers", "fixed", "custom"} and not tickers:
            issues.append(_issue(
                "parameters.tickers",
                "required",
                "Fixed-universe models need at least one ticker to trade.",
            ))
    elif not tickers:
        issues.append(_issue("parameters.tickers", "required", "At least one ticker is required."))


def _normalize_rule_identity(
    family: str,
    params: dict[str, Any],
    rules: dict[str, Any],
    tickers: list[str],
    issues: list[dict[str, str]],
) -> str:
    instrument = _symbol(rules.get("instrument") or (tickers[0] if tickers else ""))
    if not instrument:
        issues.append(_issue("parameters.rules.instrument", "required", "Instrument ticker is required."))
    else:
        rules["instrument"] = instrument
        params["tickers"] = normalize_tickers([instrument, *tickers])

    direction = str(rules.get("direction") or "long").strip().lower()
    if direction not in VALID_DIRECTIONS:
        issues.append(_issue("parameters.rules.direction", "invalid_choice", "Direction must be long or short."))
        direction = "long"
    rules["direction"] = direction

    if family in LONG_ONLY_RULE_FAMILIES and direction == "short":
        issues.append(_issue(
            "parameters.rules.direction",
            "incompatible_family",
            "Long-term, income, and risk-rotation rule strategies must use long exposure. Use the Short Selling family for bearish rules.",
        ))
    if family == "short_selling" and direction != "short":
        issues.append(_issue(
            "parameters.rules.direction",
            "incompatible_family",
            "Short Selling rule strategies must use short direction.",
        ))
    return instrument


def _normalize_signal(rules: dict[str, Any], instrument: str, issues: list[dict[str, str]]) -> None:
    signal = rules.get("signal") or {}
    if not isinstance(signal, dict):
        issues.append(_issue("parameters.rules.signal", "invalid_type", "Signal must be an object."))
        signal = {}

    signal_type = str(signal.get("type") or rules.get("signal_type") or "").strip().lower()
    if not signal_type:
        issues.append(_issue("parameters.rules.signal.type", "required", "Signal type is required."))
    elif signal_type not in RULE_SIGNAL_TYPES:
        issues.append(_issue(
            "parameters.rules.signal.type",
            "invalid_choice",
            f"Signal type '{signal_type}' is not supported.",
        ))
    signal["type"] = signal_type

    reference = _symbol(signal.get("reference") or rules.get("reference") or "")
    if not reference and signal_type in {"new_high", "new_low"}:
        reference = "^GSPC"
    signal["reference"] = reference or instrument

    if signal_type in {"pct_drop", "pct_gain"}:
        signal["pct"] = _pct(
            value=signal.get("pct"), fallback=0.05, field="parameters.rules.signal.pct",
            label="Signal move size", issues=issues, maximum=1.0,
        )
        signal["window_days"] = _bounded_int(
            value=signal.get("window_days") or signal.get("days"), fallback=21,
            field="parameters.rules.signal.window_days", label="Signal lookback window",
            issues=issues, minimum=1, maximum=252, required=True,
        )
    elif signal_type in {"ma_cross_up", "ma_cross_down"}:
        fast = _bounded_int(
            value=signal.get("fast_days"), fallback=20, field="parameters.rules.signal.fast_days",
            label="Fast moving average", issues=issues, minimum=1, maximum=252, required=True,
        )
        slow = _bounded_int(
            value=signal.get("slow_days"), fallback=50, field="parameters.rules.signal.slow_days",
            label="Slow moving average", issues=issues, minimum=2, maximum=500, required=True,
        )
        if fast is not None and slow is not None and fast >= slow:
            issues.append(_issue(
                "parameters.rules.signal.fast_days",
                "incompatible_value",
                "Fast moving average must be shorter than the slow moving average.",
            ))
        signal["fast_days"] = fast
        signal["slow_days"] = slow
    elif signal_type in {"new_high", "new_low"} and signal.get("lookback_days") is not None:
        signal["lookback_days"] = _bounded_int(
            value=signal.get("lookback_days"), fallback=None,
            field="parameters.rules.signal.lookback_days", label="High/low lookback",
            issues=issues, minimum=2, maximum=2520,
        )
    rules["signal"] = signal


def _normalize_rule_exits(family: str, rules: dict[str, Any], issues: list[dict[str, str]]) -> None:
    rules["take_profit_pct"] = _pct(
        value=rules.get("take_profit_pct", rules.get("take_profit")), fallback=0.10,
        field="parameters.rules.take_profit_pct", label="Take profit", issues=issues, maximum=2.0,
    )
    rules["stop_loss_pct"] = _pct(
        value=rules.get("stop_loss_pct", rules.get("stop_loss")), fallback=0.05,
        field="parameters.rules.stop_loss_pct", label="Stop loss", issues=issues, maximum=1.0,
    )
    if family == "short_selling" and rules.get("stop_loss_pct") and rules["stop_loss_pct"] > 0.50:
        issues.append(_issue(
            "parameters.rules.stop_loss_pct",
            "out_of_range",
            "Short Selling stop loss must be no more than 50%.",
        ))
    max_hold = _bounded_int(
        value=rules.get("max_hold_days"), fallback=None, field="parameters.rules.max_hold_days",
        label="Max holding period", issues=issues, minimum=0, maximum=1095,
    )
    rules["max_hold_days"] = max_hold or None


def validate_strategy_config(category: Category | str, parameters: dict[str, Any] | None) -> dict[str, Any]:
    """Return field-level validation details plus normalized parameters.

    Catalogue/guided strategies can stay broad, but explicit rule strategies use
    a typed schema so malformed user or assistant-created configs never reach the
    backtest engine by coincidence.
    """
    issues: list[dict[str, str]] = []
    params = deepcopy(parameters or {})
    family = str(category)

    tickers = normalize_tickers(_as_list(params.get("tickers")))
    params["tickers"] = tickers

    rules = params.get("rules")
    if rules is None:
        _validate_catalogue_config(params, tickers, issues)
        return _validation_result(params, issues)

    if not isinstance(rules, dict):
        issues.append(_issue("parameters.rules", "invalid_type", "Rules must be an object."))
        return _validation_result(params, issues)

    instrument = _normalize_rule_identity(family, params, rules, tickers, issues)
    _normalize_signal(rules, instrument, issues)
    _normalize_rule_exits(family, rules, issues)
    params["rules"] = rules

    if family == "options":
        _validate_options_profile(params, issues)

    return _validation_result(params, issues)


def validate_or_raise(category: Category | str, parameters: dict[str, Any] | None) -> dict[str, Any]:
    result = validate_strategy_config(category, parameters)
    if not result["valid"]:
        raise ValidationError("Strategy configuration is invalid", issues=result["issues"])
    return result
