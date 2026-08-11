"""Project StarBase v4A trusted single-account state and accounting ledger.

v4A deliberately does NOT enforce drawdown breaches, DLL rules, evaluation pass/fail,
or payout eligibility. It establishes the auditable accounting substrate those later
v4 stages will consume.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from starbase_integrity import assess_rule_coverage, sha256_text, stable_json
from starbase_rulebook import product_details

ACCOUNT_LEDGER_SCHEMA_VERSION = "4A.0.0"
ACCOUNT_ENGINE_VERSION = "4.0A"
GENESIS_HASH = "0" * 64

ACCOUNT_STATUSES = {
    "ACTIVE",
    "PASSED_WAITING",
    "PAYOUT_ELIGIBLE",
    "PAUSED",
    "FAILED",
    "EXPIRED",
    "CLOSED",
}
ACCOUNT_STAGES = {"evaluation", "sim_funded", "live"}


class AccountStateError(ValueError):
    pass


@dataclass(frozen=True)
class AccountState:
    account_id: str
    firm_id: str
    firm_name: str
    product_id: str
    product_name: str
    account_size: int
    stage: str
    starting_balance: float
    balance: float
    status: str = "ACTIVE"
    current_session_id: Optional[str] = None
    session_net_pnl: float = 0.0
    lifetime_gross_pnl: float = 0.0
    lifetime_commissions: float = 0.0
    lifetime_net_pnl: float = 0.0
    trade_count: int = 0
    external_cash_flow: float = 0.0
    account_costs_paid: float = 0.0
    payout_cash_received: float = 0.0
    drawdown_type: Optional[str] = None
    reference_max_loss: Optional[float] = None
    reference_initial_failure_floor: Optional[float] = None
    rule_coverage_status: str = "UNVERIFIED"
    rulebook_schema_version: str = ""
    rulebook_verified_as_of: str = ""
    rule_snapshot_hash: str = ""
    event_count: int = 0
    last_event_hash: str = GENESIS_HASH


@dataclass(frozen=True)
class AccountLedgerEvent:
    sequence: int
    event_id: str
    event_hash: str
    previous_hash: str
    event_type: str
    timestamp_utc: str
    account_id: str
    session_id: Optional[str]
    balance_before: float
    balance_delta: float
    balance_after: float
    external_cash_delta: float
    gross_pnl: float = 0.0
    commission: float = 0.0
    status_before: str = "ACTIVE"
    status_after: str = "ACTIVE"
    note: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_hash(payload: Dict[str, Any]) -> str:
    return sha256_text(stable_json(payload))


def _make_event(*, state_before: AccountState, event_type: str, balance_delta: float = 0.0,
                external_cash_delta: float = 0.0, gross_pnl: float = 0.0,
                commission: float = 0.0, session_id: Optional[str] = None,
                status_after: Optional[str] = None, note: str = "",
                metadata: Optional[Dict[str, Any]] = None,
                timestamp_utc: Optional[str] = None) -> AccountLedgerEvent:
    seq = state_before.event_count + 1
    ts = timestamp_utc or _utc_now_iso()
    status_after = status_after or state_before.status
    core = {
        "schema": ACCOUNT_LEDGER_SCHEMA_VERSION,
        "sequence": seq,
        "event_type": event_type,
        "timestamp_utc": ts,
        "account_id": state_before.account_id,
        "session_id": session_id,
        "balance_before": round(float(state_before.balance), 10),
        "balance_delta": round(float(balance_delta), 10),
        "balance_after": round(float(state_before.balance + balance_delta), 10),
        "external_cash_delta": round(float(external_cash_delta), 10),
        "gross_pnl": round(float(gross_pnl), 10),
        "commission": round(float(commission), 10),
        "status_before": state_before.status,
        "status_after": status_after,
        "note": note,
        "metadata": metadata or {},
        "previous_hash": state_before.last_event_hash,
    }
    digest = _event_hash(core)
    return AccountLedgerEvent(
        sequence=seq,
        event_id=f"{state_before.account_id}-E{seq:06d}",
        event_hash=digest,
        previous_hash=state_before.last_event_hash,
        event_type=event_type,
        timestamp_utc=ts,
        account_id=state_before.account_id,
        session_id=session_id,
        balance_before=state_before.balance,
        balance_delta=balance_delta,
        balance_after=state_before.balance + balance_delta,
        external_cash_delta=external_cash_delta,
        gross_pnl=gross_pnl,
        commission=commission,
        status_before=state_before.status,
        status_after=status_after,
        note=note,
        metadata=metadata or {},
    )


def _apply_event_state(state: AccountState, event: AccountLedgerEvent) -> AccountState:
    if event.previous_hash != state.last_event_hash:
        raise AccountStateError("Ledger chain mismatch")
    if abs(event.balance_before - state.balance) > 1e-9:
        raise AccountStateError("Event balance_before does not match account state")
    return replace(
        state,
        balance=event.balance_after,
        status=event.status_after,
        external_cash_flow=state.external_cash_flow + event.external_cash_delta,
        event_count=event.sequence,
        last_event_hash=event.event_hash,
    )


def create_account_from_rulebook(rulebook: Dict[str, Any], *, product_id: str,
                                 account_size: int, stage: str,
                                 account_id: Optional[str] = None,
                                 starting_balance: Optional[float] = None,
                                 timestamp_utc: Optional[str] = None) -> Tuple[AccountState, List[AccountLedgerEvent]]:
    if stage not in ACCOUNT_STAGES:
        raise AccountStateError(f"Unsupported account stage: {stage}")
    details = product_details(rulebook, product_id)
    firm = details["firm"]
    product = details["product"]
    size_rules = product.get("account_sizes", {}).get(str(int(account_size)))
    if not size_rules or not size_rules.get(stage):
        raise AccountStateError(f"{product_id} ${int(account_size):,} does not define stage {stage}")
    stage_rules = size_rules[stage]
    start = float(starting_balance if starting_balance is not None else account_size)
    max_loss = stage_rules.get("max_loss")
    initial_floor = start - float(max_loss) if max_loss is not None else None
    coverage = assess_rule_coverage(rulebook, product_id, account_size, stage)
    rule_snapshot = {
        "rulebook_schema_version": rulebook.get("schema_version"),
        "rulebook_verified_as_of": rulebook.get("verified_as_of"),
        "firm_id": firm["firm_id"],
        "product_id": product_id,
        "account_size": int(account_size),
        "stage": stage,
        "stage_rules": stage_rules,
    }
    rid = account_id or f"{firm['firm_id'].upper()}-{product_id.upper()}-{int(account_size)}-{stage.upper()}-001"
    state = AccountState(
        account_id=rid,
        firm_id=firm["firm_id"],
        firm_name=firm["display_name"],
        product_id=product_id,
        product_name=product["display_name"],
        account_size=int(account_size),
        stage=stage,
        starting_balance=start,
        balance=start,
        drawdown_type=stage_rules.get("drawdown_type"),
        reference_max_loss=float(max_loss) if max_loss is not None else None,
        reference_initial_failure_floor=initial_floor,
        rule_coverage_status=coverage["status"],
        rulebook_schema_version=str(rulebook.get("schema_version", "")),
        rulebook_verified_as_of=str(rulebook.get("verified_as_of", "")),
        rule_snapshot_hash=sha256_text(stable_json(rule_snapshot)),
    )
    opened = _make_event(
        state_before=state,
        event_type="ACCOUNT_OPENED",
        note="v4A account initialized from versioned StarBase rulebook. Drawdown is reference-only until v4B.",
        metadata={"rule_snapshot_hash": state.rule_snapshot_hash, "coverage": coverage["status"]},
        timestamp_utc=timestamp_utc,
    )
    state = _apply_event_state(state, opened)
    return state, [opened]


def start_session(state: AccountState, ledger: List[AccountLedgerEvent], session_id: str,
                  *, timestamp_utc: Optional[str] = None, note: str = "") -> Tuple[AccountState, List[AccountLedgerEvent]]:
    if not session_id:
        raise AccountStateError("session_id is required")
    event = _make_event(
        state_before=state,
        event_type="SESSION_STARTED",
        session_id=session_id,
        note=note,
        timestamp_utc=timestamp_utc,
    )
    state = _apply_event_state(state, event)
    state = replace(state, current_session_id=session_id, session_net_pnl=0.0)
    return state, ledger + [event]


def post_trade(state: AccountState, ledger: List[AccountLedgerEvent], *, gross_pnl: float,
               commission: float, session_id: Optional[str] = None,
               timestamp_utc: Optional[str] = None, note: str = "",
               metadata: Optional[Dict[str, Any]] = None) -> Tuple[AccountState, List[AccountLedgerEvent]]:
    if commission < 0:
        raise AccountStateError("commission must be a non-negative cost")
    sid = session_id or state.current_session_id
    net = float(gross_pnl) - float(commission)
    event = _make_event(
        state_before=state,
        event_type="TRADE_REALIZED",
        balance_delta=net,
        gross_pnl=float(gross_pnl),
        commission=float(commission),
        session_id=sid,
        note=note,
        metadata=metadata,
        timestamp_utc=timestamp_utc,
    )
    state = _apply_event_state(state, event)
    state = replace(
        state,
        current_session_id=sid,
        session_net_pnl=state.session_net_pnl + net,
        lifetime_gross_pnl=state.lifetime_gross_pnl + float(gross_pnl),
        lifetime_commissions=state.lifetime_commissions + float(commission),
        lifetime_net_pnl=state.lifetime_net_pnl + net,
        trade_count=state.trade_count + 1,
    )
    return state, ledger + [event]


def post_account_cost(state: AccountState, ledger: List[AccountLedgerEvent], *, amount: float,
                      timestamp_utc: Optional[str] = None, note: str = "") -> Tuple[AccountState, List[AccountLedgerEvent]]:
    if amount < 0:
        raise AccountStateError("account cost must be non-negative")
    event = _make_event(
        state_before=state,
        event_type="ACCOUNT_COST",
        external_cash_delta=-float(amount),
        note=note,
        timestamp_utc=timestamp_utc,
    )
    state = _apply_event_state(state, event)
    state = replace(state, account_costs_paid=state.account_costs_paid + float(amount))
    return state, ledger + [event]


def set_status(state: AccountState, ledger: List[AccountLedgerEvent], *, status: str,
               timestamp_utc: Optional[str] = None, note: str = "") -> Tuple[AccountState, List[AccountLedgerEvent]]:
    if status not in ACCOUNT_STATUSES:
        raise AccountStateError(f"Unsupported account status: {status}")
    event = _make_event(
        state_before=state,
        event_type="STATUS_CHANGED",
        status_after=status,
        note=note,
        timestamp_utc=timestamp_utc,
    )
    state = _apply_event_state(state, event)
    return state, ledger + [event]


def state_to_dict(state: AccountState) -> Dict[str, Any]:
    return asdict(state)


def ledger_to_records(ledger: List[AccountLedgerEvent]) -> List[Dict[str, Any]]:
    return [asdict(event) for event in ledger]


def verify_account_ledger(ledger: List[AccountLedgerEvent]) -> Dict[str, Any]:
    previous = GENESIS_HASH
    errors: List[str] = []
    for idx, event in enumerate(ledger, start=1):
        if event.sequence != idx:
            errors.append(f"sequence mismatch at row {idx}")
        if event.previous_hash != previous:
            errors.append(f"previous_hash mismatch at row {idx}")
        core = {
            "schema": ACCOUNT_LEDGER_SCHEMA_VERSION,
            "sequence": event.sequence,
            "event_type": event.event_type,
            "timestamp_utc": event.timestamp_utc,
            "account_id": event.account_id,
            "session_id": event.session_id,
            "balance_before": round(float(event.balance_before), 10),
            "balance_delta": round(float(event.balance_delta), 10),
            "balance_after": round(float(event.balance_after), 10),
            "external_cash_delta": round(float(event.external_cash_delta), 10),
            "gross_pnl": round(float(event.gross_pnl), 10),
            "commission": round(float(event.commission), 10),
            "status_before": event.status_before,
            "status_after": event.status_after,
            "note": event.note,
            "metadata": event.metadata or {},
            "previous_hash": event.previous_hash,
        }
        if _event_hash(core) != event.event_hash:
            errors.append(f"event_hash mismatch at row {idx}")
        if abs((event.balance_before + event.balance_delta) - event.balance_after) > 1e-9:
            errors.append(f"balance arithmetic mismatch at row {idx}")
        previous = event.event_hash
    return {"valid": not errors, "event_count": len(ledger), "errors": errors, "last_hash": previous}
