from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ALLOWED_DRAWDOWNS = {"EOD_TRAILING", "INTRADAY_TRAILING", "STATIC", "NONE", "SELECTABLE_EOD_OR_INTRADAY"}
ALLOWED_STATUS = {"ACTIVE", "LEGACY", "UNAVAILABLE", "RESEARCH_ONLY"}
ALLOWED_RULE_GRADES = {
    "PRODUCTION_READY",
    "RULES_VERIFIED_ENGINE_PENDING",
    "VARIANT_SELECTION_REQUIRED",
    "RESEARCH_ONLY",
    "NOT_MODELED",
}


class RulebookValidationError(ValueError):
    pass


@dataclass(frozen=True)
class RulebookRow:
    firm_id: str
    firm: str
    product_id: str
    product: str
    status: str
    verification_status: str
    verified_date: str
    acquisition_model: str
    simulation_readiness: str
    account_size: int
    evaluation_drawdown: Optional[str]
    funded_drawdown: Optional[str]
    live_drawdown: Optional[str]
    profit_target: Optional[float]
    evaluation_max_loss: Optional[float]
    funded_max_loss: Optional[float]
    payout_qualifying_days: Optional[int]
    payout_qualifying_profit: Optional[float]
    payout_split_percent: Optional[float]
    evaluation_consistency: str
    funded_consistency: str
    evaluation_rule_grade: str
    funded_rule_grade: str
    evaluation_rankable: bool
    funded_rankable: bool
    source_count: int


def load_rulebook(path: Optional[Path] = None) -> Dict[str, Any]:
    path = path or Path(__file__).with_name("starbase_rules_v3.json")
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    validate_rulebook(data)
    return data


def validate_rulebook(data: Dict[str, Any]) -> None:
    if data.get("schema_version") not in {"3.0.0", "3.1.0"}:
        raise RulebookValidationError("Expected StarBase rulebook schema_version 3.0.0 or 3.1.0")
    taxonomy = set(data.get("drawdown_taxonomy", []))
    if not ALLOWED_DRAWDOWNS.issubset(taxonomy):
        raise RulebookValidationError("Rulebook drawdown taxonomy is incomplete")
    seen_products = set()
    if not data.get("firms"):
        raise RulebookValidationError("Rulebook contains no firms")
    for firm in data["firms"]:
        if not firm.get("firm_id") or not firm.get("display_name"):
            raise RulebookValidationError("Each firm needs firm_id and display_name")
        for product in firm.get("products", []):
            pid = product.get("product_id")
            if not pid or pid in seen_products:
                raise RulebookValidationError(f"Missing or duplicate product_id: {pid}")
            seen_products.add(pid)
            if product.get("status") not in ALLOWED_STATUS:
                raise RulebookValidationError(f"Invalid status for {pid}")
            if not product.get("verified_date"):
                raise RulebookValidationError(f"Missing verified_date for {pid}")
            if not product.get("sources"):
                raise RulebookValidationError(f"Missing official sources for {pid}")
            if not product.get("account_sizes"):
                raise RulebookValidationError(f"Missing account sizes for {pid}")
            for stage, rt in (product.get("rule_truth") or {}).items():
                if rt.get("grade") not in ALLOWED_RULE_GRADES:
                    raise RulebookValidationError(f"Invalid Rule Truth grade for {pid}/{stage}: {rt.get('grade')}")
            for size, size_rules in product["account_sizes"].items():
                try:
                    int(size)
                except Exception as exc:
                    raise RulebookValidationError(f"Non-numeric account size in {pid}: {size}") from exc
                for stage_name in ("evaluation", "sim_funded", "live"):
                    stage = size_rules.get(stage_name)
                    if not stage:
                        continue
                    dd = stage.get("drawdown_type")
                    if dd is not None and dd not in ALLOWED_DRAWDOWNS:
                        raise RulebookValidationError(f"Invalid {stage_name} drawdown for {pid}/{size}: {dd}")
                    dll = stage.get("dll")
                    if dll and dll.get("action") not in {None, "NONE", "SOFT_PAUSE_SESSION", "HARD_FAIL"}:
                        raise RulebookValidationError(f"Invalid DLL action for {pid}/{size}/{stage_name}")


def _first_payout(stage: Dict[str, Any]) -> Dict[str, Any]:
    return stage.get("payout") or {}


def consistency_label(stage: Dict[str, Any]) -> str:
    pct = stage.get("consistency_percent")
    if pct is not None:
        return f"{float(pct):g}%"
    payout = stage.get("payout") or {}
    pct = payout.get("consistency_percent")
    if pct is not None:
        return f"{float(pct):g}%"
    seq = payout.get("consistency_sequence_percent")
    if seq:
        return "VARIES " + "/".join(f"{float(v):g}%" for v in seq)
    return "NONE"


def rule_truth_for(product: Dict[str, Any], stage: str) -> Dict[str, Any]:
    rt = (product.get("rule_truth") or {}).get(stage)
    if rt:
        return dict(rt)
    # v3.0 backward-compatible inference.
    ready = product.get("simulation_readiness", "")
    verification = product.get("verification_status", "")
    if verification == "VERIFIED_CORE" and ready == "READY_FOR_V4_CORE":
        return {"grade": "PRODUCTION_READY", "rankable": True, "unmodeled_reasons": []}
    if "VARIANT" in ready or "REQUIRE" in ready:
        return {"grade": "VARIANT_SELECTION_REQUIRED", "rankable": False, "unmodeled_reasons": [ready]}
    return {"grade": "RESEARCH_ONLY", "rankable": False, "unmodeled_reasons": [ready or verification or "Not classified"]}


def flatten_rulebook(data: Dict[str, Any]) -> List[RulebookRow]:
    rows: List[RulebookRow] = []
    for firm in data["firms"]:
        for product in firm.get("products", []):
            sources = list(dict.fromkeys((firm.get("sources") or []) + (product.get("sources") or [])))
            ev_truth = rule_truth_for(product, "evaluation")
            fd_truth = rule_truth_for(product, "sim_funded")
            for size_s, sr in sorted(product["account_sizes"].items(), key=lambda kv: int(kv[0])):
                ev = sr.get("evaluation") or {}
                fd = sr.get("sim_funded") or {}
                lv = sr.get("live") or {}
                payout = _first_payout(fd)
                rows.append(RulebookRow(
                    firm_id=firm["firm_id"], firm=firm["display_name"],
                    product_id=product["product_id"], product=product["display_name"],
                    status=product["status"], verification_status=product.get("verification_status", "UNKNOWN"),
                    verified_date=product["verified_date"], acquisition_model=product.get("acquisition_model", "UNKNOWN"),
                    simulation_readiness=product.get("simulation_readiness", "UNKNOWN"), account_size=int(size_s),
                    evaluation_drawdown=ev.get("drawdown_type"), funded_drawdown=fd.get("drawdown_type"),
                    live_drawdown=lv.get("drawdown_type"), profit_target=ev.get("profit_target"),
                    evaluation_max_loss=ev.get("max_loss"), funded_max_loss=fd.get("max_loss"),
                    payout_qualifying_days=payout.get("qualifying_days"), payout_qualifying_profit=payout.get("qualifying_day_profit"),
                    payout_split_percent=payout.get("profit_split_percent") or fd.get("profit_split_percent"),
                    evaluation_consistency=consistency_label(ev), funded_consistency=consistency_label(fd),
                    evaluation_rule_grade=ev_truth.get("grade", "NOT_MODELED"), funded_rule_grade=fd_truth.get("grade", "NOT_MODELED"),
                    evaluation_rankable=bool(ev_truth.get("rankable")), funded_rankable=bool(fd_truth.get("rankable")),
                    source_count=len(sources)
                ))
    return rows


def filter_rows(rows: Iterable[RulebookRow], *, funded_drawdowns: Optional[Iterable[str]] = None,
                firms: Optional[Iterable[str]] = None, sizes: Optional[Iterable[int]] = None,
                evaluation_consistency: Optional[Iterable[str]] = None,
                funded_consistency: Optional[Iterable[str]] = None,
                rule_grades: Optional[Iterable[str]] = None,
                rankable_only: bool = False,
                active_only: bool = True) -> List[RulebookRow]:
    dds = set(funded_drawdowns or [])
    firmset = set(firms or [])
    sizeset = set(sizes or [])
    evc = set(evaluation_consistency or [])
    fdc = set(funded_consistency or [])
    grades = set(rule_grades or [])
    out = []
    for row in rows:
        if active_only and row.status != "ACTIVE":
            continue
        if dds and row.funded_drawdown not in dds:
            continue
        if firmset and row.firm_id not in firmset:
            continue
        if sizeset and row.account_size not in sizeset:
            continue
        if evc and row.evaluation_consistency not in evc:
            continue
        if fdc and row.funded_consistency not in fdc:
            continue
        if grades and row.funded_rule_grade not in grades and row.evaluation_rule_grade not in grades:
            continue
        if rankable_only and not (row.evaluation_rankable or row.funded_rankable):
            continue
        out.append(row)
    return out


def product_details(data: Dict[str, Any], product_id: str) -> Dict[str, Any]:
    for firm in data["firms"]:
        for product in firm.get("products", []):
            if product.get("product_id") == product_id:
                return {"firm": firm, "product": product}
    raise KeyError(product_id)


def rulebook_freshness(data: Dict[str, Any], as_of: Optional[date] = None) -> Dict[str, Any]:
    as_of = as_of or date.today()
    verified = date.fromisoformat(str(data["verified_as_of"]))
    age = (as_of - verified).days
    if age <= 14:
        grade = "FRESH"
    elif age <= 30:
        grade = "AGING"
    else:
        grade = "STALE"
    return {"verified_as_of": verified.isoformat(), "age_days": age, "grade": grade}
