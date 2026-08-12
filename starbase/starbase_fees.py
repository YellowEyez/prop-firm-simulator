"""Versioned instrument/firm/platform fee resolution for Project StarBase."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import json
from pathlib import Path
from typing import Optional

FEE_ENGINE_VERSION = "1.0.0"
FEE_PATH = Path(__file__).resolve().parent / "starbase_fees_v1.json"

@dataclass(frozen=True)
class FeeQuote:
    firm_id: str
    product_id: str
    instrument: str
    platform_variant: str
    round_trip_per_contract: Optional[float]
    status: str
    source: str
    effective_date: Optional[str]
    verified_as_of: str
    note: str
    resolution: str

    def to_dict(self):
        return asdict(self)


def load_fee_catalog() -> dict:
    return json.loads(FEE_PATH.read_text(encoding="utf-8"))


def instrument_spec(symbol: str) -> dict:
    cat = load_fee_catalog()
    return dict(cat.get("instruments", {}).get(str(symbol).upper(), {}))


def infer_instrument_from_profile(profile_id: str) -> Optional[str]:
    text = str(profile_id or "").upper().replace("_", "").replace("-", "")
    # Longest tokens first so MNQ is not mistaken for NQ, etc.
    for sym in ("MNQ", "MES", "NQ", "ES"):
        if sym in text:
            return sym
    return None


def available_platforms(firm_id: str) -> list[str]:
    firm = load_fee_catalog().get("firms", {}).get(firm_id, {})
    return [k for k in firm.keys() if k != "default"] or (["default"] if "default" in firm else [])


def resolve_fee(*, firm_id: str, product_id: str, instrument: str, platform_variant: Optional[str] = None, manual_override: Optional[float] = None) -> FeeQuote:
    cat = load_fee_catalog()
    instrument = str(instrument or "").upper()
    if manual_override is not None:
        return FeeQuote(
            firm_id=firm_id, product_id=product_id, instrument=instrument,
            platform_variant=str(platform_variant or "MANUAL"),
            round_trip_per_contract=float(manual_override), status="USER_VERIFIED_OVERRIDE",
            source="USER_INPUT", effective_date=None, verified_as_of=cat.get("verified_as_of", ""),
            note="User-supplied round-trip all-in fee override. Verify against the current prop-firm/platform schedule.",
            resolution="MANUAL_OVERRIDE",
        )
    firm = cat.get("firms", {}).get(firm_id, {})
    key = str(platform_variant or "default").upper()
    if key == "DEFAULT":
        key = "default"
    sched = firm.get(key) or firm.get(str(platform_variant or "")) or firm.get("default")
    if not sched:
        return FeeQuote(firm_id, product_id, instrument, str(platform_variant or "default"), None, "NOT_MODELED", "", None, cat.get("verified_as_of", ""), "No fee schedule is modeled for this firm/platform.", "UNRESOLVED")
    rate = sched.get("round_trip", {}).get(instrument)
    status = str(sched.get("status", "NOT_MODELED"))
    resolution = "OFFICIAL_SCHEDULE" if rate is not None and status.startswith("VERIFIED") else ("OFFICIAL_PARTIAL" if rate is not None else "UNRESOLVED")
    return FeeQuote(
        firm_id=firm_id, product_id=product_id, instrument=instrument,
        platform_variant=str(platform_variant or "default"),
        round_trip_per_contract=None if rate is None else float(rate),
        status=status, source=str(sched.get("source", "")), effective_date=sched.get("effective_date"),
        verified_as_of=str(cat.get("verified_as_of", "")), note=str(sched.get("note", "")), resolution=resolution,
    )
