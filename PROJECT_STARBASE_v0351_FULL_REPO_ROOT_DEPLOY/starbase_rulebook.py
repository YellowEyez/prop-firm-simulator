from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ALLOWED_DRAWDOWNS = {"EOD_TRAILING", "INTRADAY_TRAILING", "STATIC", "NONE", "SELECTABLE_EOD_OR_INTRADAY"}
ALLOWED_STATUS = {"ACTIVE", "LEGACY", "UNAVAILABLE", "RESEARCH_ONLY"}


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
    source_count: int


def load_rulebook(path: Optional[Path] = None) -> Dict[str, Any]:
    path = path or Path(__file__).with_name("starbase_rules_v3.json")
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    validate_rulebook(data)
    return data


def validate_rulebook(data: Dict[str, Any]) -> None:
    if data.get("schema_version") != "3.0.0":
        raise RulebookValidationError("Expected StarBase rulebook schema_version 3.0.0")
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
                    if dll and dll.get("action") not in {"NONE", "SOFT_PAUSE_SESSION", "HARD_FAIL"}:
                        raise RulebookValidationError(f"Invalid DLL action for {pid}/{size}/{stage_name}")


def _first_payout(stage: Dict[str, Any]) -> Dict[str, Any]:
    return stage.get("payout") or {}


def flatten_rulebook(data: Dict[str, Any]) -> List[RulebookRow]:
    rows: List[RulebookRow] = []
    for firm in data["firms"]:
        for product in firm.get("products", []):
            sources = list(dict.fromkeys((firm.get("sources") or []) + (product.get("sources") or [])))
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
                    payout_split_percent=payout.get("profit_split_percent") or fd.get("profit_split_percent"), source_count=len(sources)
                ))
    return rows


def filter_rows(rows: Iterable[RulebookRow], *, funded_drawdowns: Optional[Iterable[str]] = None,
                firms: Optional[Iterable[str]] = None, sizes: Optional[Iterable[int]] = None,
                active_only: bool = True) -> List[RulebookRow]:
    dds = set(funded_drawdowns or [])
    firmset = set(firms or [])
    sizeset = set(sizes or [])
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
        out.append(row)
    return out


def product_details(data: Dict[str, Any], product_id: str) -> Dict[str, Any]:
    for firm in data["firms"]:
        for product in firm.get("products", []):
            if product.get("product_id") == product_id:
                return {"firm": firm, "product": product}
    raise KeyError(product_id)
