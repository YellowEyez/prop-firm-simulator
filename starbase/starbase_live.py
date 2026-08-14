"""Project StarBase v5G live-account state foundation (Step 28).

This module models *state*, not live transition orchestration or payout execution.
Those remain Steps 29-31. The purpose here is to make live accounts first-class,
auditable objects with their own balance conventions, loss floor, DLL, reserve/vault
metadata, contract tier, and current rule provenance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from starbase_integrity import sha256_text, stable_json
from starbase_paths import asset_path

LIVE_STATE_VERSION = "5G.1.0"
LIVE_PROFILE_SCHEMA_VERSION = "1.0.0"


class LiveStateError(ValueError):
    pass


@dataclass(frozen=True)
class LiveAccountState:
    account_id: str
    profile_id: str
    firm_id: str
    firm_name: str
    profile_name: str
    source_account_size: Optional[int]
    status: str
    starting_balance_mode: str
    starting_balance: float
    balance: float
    failure_floor: Optional[float]
    cushion: Optional[float]
    drawdown_type: str
    dll_amount: Optional[float]
    dll_action: str
    max_minis: Optional[int]
    max_micros: Optional[int]
    risk_tier: str
    reserve_balance: float
    bonus_vault_balance: float
    cumulative_live_withdrawals: float
    trader_wallet_cash: float
    state_grade: str
    profile_verified_as_of: str
    profile_schema_version: str
    rule_snapshot_hash: str
    unresolved_reasons: tuple[str, ...]
    source_urls: tuple[str, ...]
    live_payout_count: int = 0
    last_live_payout_date: Optional[str] = None
    live_bonus_cash_received: float = 0.0


def load_live_profiles(path: Optional[str | Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else asset_path("starbase_live_profiles_v1.json")
    data = json.loads(Path(p).read_text(encoding="utf-8"))
    if data.get("schema_version") != LIVE_PROFILE_SCHEMA_VERSION:
        raise LiveStateError(f"Unsupported live profile schema: {data.get('schema_version')}")
    return data


def profile_by_id(catalog: Dict[str, Any], profile_id: str) -> Dict[str, Any]:
    for p in catalog.get("profiles", []):
        if p.get("profile_id") == profile_id:
            return p
    raise LiveStateError(f"Unknown live profile: {profile_id}")


def live_profile_rows(catalog: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    cat = catalog or load_live_profiles()
    rows = []
    for p in cat.get("profiles", []):
        dll = p.get("dll") or {}
        rows.append({
            "Profile": p.get("display_name"),
            "Firm": p.get("firm_name"),
            "Profile ID": p.get("profile_id"),
            "Source Size": p.get("source_account_size"),
            "Starting Balance Mode": p.get("starting_balance_mode"),
            "Starting Balance": p.get("starting_balance"),
            "Initial Failure Floor": p.get("initial_failure_floor"),
            "Drawdown": p.get("drawdown_type"),
            "Daily Loss Limit": dll.get("amount"),
            "State Grade": p.get("state_grade"),
        })
    return rows


def _tier_for_balance(profile: Dict[str, Any], balance: float) -> Dict[str, Any]:
    tiers = profile.get("contract_tiers_cme") or []
    if not tiers:
        return {}
    chosen: Dict[str, Any] = {}
    for t in tiers:
        low = float(t.get("min_balance") if t.get("min_balance") is not None else float("-inf"))
        high_raw = t.get("max_balance_exclusive")
        high = float(high_raw) if high_raw is not None else float("inf")
        if float(balance) >= low and float(balance) < high:
            chosen = t
            break
    if not chosen:
        chosen = tiers[-1]
    return chosen


def _state_snapshot_hash(catalog: Dict[str, Any], profile: Dict[str, Any], inputs: Dict[str, Any]) -> str:
    payload = {
        "live_state_version": LIVE_STATE_VERSION,
        "profile_schema_version": catalog.get("schema_version"),
        "profile_verified_as_of": catalog.get("verified_as_of"),
        "profile": profile,
        "inputs": inputs,
    }
    return sha256_text(stable_json(payload))


def create_live_account(
    profile_id: str,
    *,
    catalog: Optional[Dict[str, Any]] = None,
    account_id: Optional[str] = None,
    starting_balance_override: Optional[float] = None,
    reserve_balance: float = 0.0,
    bonus_vault_balance: float = 0.0,
) -> LiveAccountState:
    cat = catalog or load_live_profiles()
    p = profile_by_id(cat, profile_id)
    if p.get("state_grade") == "CONFLICTING_OFFICIAL_TEXT":
        reasons = " | ".join(p.get("unresolved_reasons") or [])
        raise LiveStateError(f"Cannot instantiate conflicting live profile without resolution: {reasons}")

    mode = str(p.get("starting_balance_mode") or "FIXED")
    fixed_start = p.get("starting_balance")
    if mode.startswith("TRANSITION_DERIVED"):
        if starting_balance_override is None:
            raise LiveStateError("This live profile requires a transition-derived starting balance override.")
        min_start = float(p.get("minimum_starting_balance") or 0.0)
        if float(starting_balance_override) < min_start:
            raise LiveStateError(f"Starting balance must be at least ${min_start:,.2f} for this live profile.")
        start = float(starting_balance_override)
    else:
        start = float(fixed_start if starting_balance_override is None else starting_balance_override)

    floor = p.get("initial_failure_floor")
    floor = None if floor is None else float(floor)
    tier = _tier_for_balance(p, start)
    dll_cfg = p.get("dll") or {}
    tier_dll = tier.get("dll") if tier else None
    dll_amount = tier_dll if tier_dll is not None else dll_cfg.get("amount")
    unresolved = tuple(str(x) for x in (p.get("unresolved_reasons") or []))
    inputs = {
        "starting_balance_override": starting_balance_override,
        "reserve_balance": float(reserve_balance),
        "bonus_vault_balance": float(bonus_vault_balance),
    }
    rid = account_id or f"LIVE-{p['firm_id'].upper()}-{profile_id.upper()}-001"
    cushion = None if floor is None else start - floor
    return LiveAccountState(
        account_id=rid,
        profile_id=profile_id,
        firm_id=str(p.get("firm_id")),
        firm_name=str(p.get("firm_name")),
        profile_name=str(p.get("display_name")),
        source_account_size=int(p["source_account_size"]) if p.get("source_account_size") is not None else None,
        status="ACTIVE",
        starting_balance_mode=mode,
        starting_balance=start,
        balance=start,
        failure_floor=floor,
        cushion=cushion,
        drawdown_type=str(p.get("drawdown_type") or "UNRESOLVED"),
        dll_amount=float(dll_amount) if dll_amount is not None else None,
        dll_action=str(dll_cfg.get("action") or "NONE"),
        max_minis=int(tier["max_minis"]) if tier.get("max_minis") is not None else None,
        max_micros=int(tier["max_micros"]) if tier.get("max_micros") is not None else None,
        risk_tier=str(tier.get("level") or f"BALANCE_TIER_{tier.get('min_balance','?')}") if tier else "UNRESOLVED",
        reserve_balance=float(reserve_balance),
        bonus_vault_balance=float(bonus_vault_balance),
        cumulative_live_withdrawals=0.0,
        trader_wallet_cash=0.0,
        state_grade=str(p.get("state_grade") or "UNRESOLVED"),
        profile_verified_as_of=str(cat.get("verified_as_of") or ""),
        profile_schema_version=str(cat.get("schema_version") or ""),
        rule_snapshot_hash=_state_snapshot_hash(cat, p, inputs),
        unresolved_reasons=unresolved,
        source_urls=tuple(str(x) for x in (p.get("source_urls") or [])),
    )


def revalue_live_state(
    state: LiveAccountState,
    new_balance: float,
    *,
    catalog: Optional[Dict[str, Any]] = None,
    floor_locked: Optional[bool] = None,
) -> LiveAccountState:
    """Revalue state for inspection/testing without executing payouts or transitions.

    EOD trailing floor behavior is applied only for profiles with an explicit start-drawdown
    and lock floor. This is a state projection, not a complete live lifecycle simulator.
    """
    cat = catalog or load_live_profiles()
    p = profile_by_id(cat, state.profile_id)
    bal = float(new_balance)
    current_floor = state.failure_floor
    drawdown = p.get("starting_drawdown")
    lock_floor = p.get("lock_floor")
    lock_trigger = p.get("lock_trigger_balance")

    if state.drawdown_type in {"EOD_TRAILING", "TRAILING_MLL"} and drawdown is not None:
        raw_floor = bal - float(drawdown)
        if current_floor is None:
            current_floor = raw_floor
        else:
            current_floor = max(float(current_floor), raw_floor)
        should_lock = bool(floor_locked) if floor_locked is not None else (lock_trigger is not None and bal >= float(lock_trigger))
        if should_lock and lock_floor is not None:
            current_floor = float(lock_floor)
    elif state.drawdown_type in {"EOD_MINIMUM_BALANCE", "LIVE_MINIMUM_BALANCE_PLUS_DLL"}:
        current_floor = float(p.get("lock_floor") if p.get("lock_floor") is not None else p.get("initial_failure_floor"))

    tier = _tier_for_balance(p, bal)
    dll_cfg = p.get("dll") or {}
    tier_dll = tier.get("dll") if tier else None
    dll_amount = tier_dll if tier_dll is not None else dll_cfg.get("amount")
    status = state.status
    if current_floor is not None and bal <= float(current_floor):
        status = "FAILED"
    return replace(
        state,
        balance=bal,
        failure_floor=current_floor,
        cushion=None if current_floor is None else bal - float(current_floor),
        dll_amount=float(dll_amount) if dll_amount is not None else None,
        max_minis=int(tier["max_minis"]) if tier.get("max_minis") is not None else state.max_minis,
        max_micros=int(tier["max_micros"]) if tier.get("max_micros") is not None else state.max_micros,
        risk_tier=str(tier.get("level") or f"BALANCE_TIER_{tier.get('min_balance','?')}") if tier else state.risk_tier,
        status=status,
    )


def state_as_dict(state: LiveAccountState) -> Dict[str, Any]:
    return asdict(state)


def run_live_state_verification(catalog: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Independent Step-28 state fixtures. No historical trades or payout engine required."""
    cat = catalog or load_live_profiles()
    fixtures = [
        {
            "id": "L01_LUCID_50K_OPEN",
            "profile_id": "lucid_live_50k",
            "create": {},
            "expected": {"starting_balance": 0.0, "failure_floor": -2000.0, "cushion": 2000.0, "dll_amount": None, "max_minis": 2, "max_micros": 20},
        },
        {
            "id": "L02_LUCID_50K_SCALE_LOCK",
            "profile_id": "lucid_live_50k",
            "create": {},
            "revalue": 4100.0,
            "expected": {"failure_floor": 100.0, "cushion": 4000.0, "max_minis": 4, "max_micros": 40, "status": "ACTIVE"},
        },
        {
            "id": "L03_TRADEIFY_50K_OPEN",
            "profile_id": "tradeify_elite_50k",
            "create": {},
            "expected": {"starting_balance": 0.0, "failure_floor": -2000.0, "max_minis": 2, "max_micros": 20, "dll_amount": None},
        },
        {
            "id": "L04_MFFU_50K_OPEN",
            "profile_id": "mffu_flex_live_50k",
            "create": {},
            "expected": {"starting_balance": 2000.0, "failure_floor": 156.0, "cushion": 1844.0, "max_minis": 3, "max_micros": 30, "dll_amount": None},
        },
        {
            "id": "L05_APEX_LEVEL2",
            "profile_id": "apex_live_uniform",
            "create": {},
            "revalue": 12000.0,
            "expected": {"failure_floor": 100.0, "max_minis": 25, "max_micros": 250, "dll_amount": 5000.0, "risk_tier": "2"},
        },
        {
            "id": "L06_TOPSTEP_50K_TRANSITION_STATE",
            "profile_id": "topstep_lfa_50k",
            "create": {"starting_balance_override": 10000.0, "reserve_balance": 40000.0},
            "expected": {"starting_balance": 10000.0, "failure_floor": 1000.0, "reserve_balance": 40000.0, "dll_amount": 2000.0, "max_minis": 5, "max_micros": 50},
        },
    ]
    results = []
    for f in fixtures:
        state = create_live_account(f["profile_id"], catalog=cat, **f.get("create", {}))
        if "revalue" in f:
            state = revalue_live_state(state, f["revalue"], catalog=cat)
        actual = state_as_dict(state)
        checks = []
        for k, expected in f["expected"].items():
            got = actual.get(k)
            if isinstance(expected, float):
                ok = got is not None and abs(float(got) - expected) <= 1e-6
            else:
                ok = got == expected
            checks.append({"field": k, "expected": expected, "actual": got, "pass": ok})
        results.append({"fixture_id": f["id"], "profile_id": f["profile_id"], "pass": all(x["pass"] for x in checks), "checks": checks})

    conflict_blocked = False
    conflict_message = ""
    try:
        create_live_account("fundednext_rapid_live_50k", catalog=cat)
    except LiveStateError as exc:
        conflict_blocked = True
        conflict_message = str(exc)
    results.append({
        "fixture_id": "L07_FUNDEDNEXT_CONFLICT_BLOCK",
        "profile_id": "fundednext_rapid_live_50k",
        "pass": conflict_blocked,
        "checks": [{"field": "conflicting official text is blocked", "expected": True, "actual": conflict_blocked, "pass": conflict_blocked}, {"field": "reason", "expected": "explicit conflict message", "actual": conflict_message, "pass": bool(conflict_message)}],
    })
    passed = sum(1 for r in results if r["pass"])
    return {
        "suite_version": LIVE_STATE_VERSION,
        "profile_schema": cat.get("schema_version"),
        "profiles_verified_as_of": cat.get("verified_as_of"),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "all_pass": passed == len(results),
        "results": results,
    }
