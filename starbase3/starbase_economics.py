"""Project StarBase economics/provenance helpers (v5B).

This module intentionally separates:
  * external household cash costs (account purchases, resets, activations, etc.)
  * trading commissions that are debited inside prop-account P&L
  * payout cash actually received by the household

Funded-only fleet research cannot infer the true cost of manufacturing an evaluation-based
funded account without running the evaluation factory. For those runs StarBase accepts an
explicit *effective funded acquisition cost* assumption, or can mark the inventory as
pre-existing/unknown-cost. It must never silently pretend the cost is zero business-wide.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, Optional

ECONOMICS_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class AcquisitionCostPolicy:
    mode: str = "EXISTING_INVENTORY_UNKNOWN_COST"  # EXISTING_INVENTORY_UNKNOWN_COST | MANUAL_EFFECTIVE_FUNDED_COST
    effective_cost_per_funded_account: float = 0.0
    refund_or_bonus_per_account: float = 0.0
    one_time_household_external_cost: float = 0.0

    @property
    def cost_basis_known(self) -> bool:
        return self.mode == "MANUAL_EFFECTIVE_FUNDED_COST"

    def validate(self) -> None:
        if self.mode not in {"EXISTING_INVENTORY_UNKNOWN_COST", "MANUAL_EFFECTIVE_FUNDED_COST"}:
            raise ValueError(f"Unsupported acquisition-cost mode: {self.mode}")
        if self.effective_cost_per_funded_account < 0:
            raise ValueError("effective_cost_per_funded_account must be >= 0")
        if self.refund_or_bonus_per_account < 0:
            raise ValueError("refund_or_bonus_per_account must be >= 0")
        if self.one_time_household_external_cost < 0:
            raise ValueError("one_time_household_external_cost must be >= 0")

    def provision_external_cost(self) -> float:
        if self.mode == "MANUAL_EFFECTIVE_FUNDED_COST":
            return float(self.effective_cost_per_funded_account)
        return 0.0

    def provision_refund_or_bonus(self) -> float:
        if self.mode == "MANUAL_EFFECTIVE_FUNDED_COST":
            return float(self.refund_or_bonus_per_account)
        return 0.0


def load_cost_reference(path: Optional[str | Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else Path(__file__).resolve().parent / "starbase_costs_v1.json"
    return json.loads(p.read_text(encoding="utf-8"))


def cost_reference_for_product(catalog: Dict[str, Any], product_id: str, account_size: int) -> Dict[str, Any]:
    p = (catalog.get("products") or {}).get(product_id) or {}
    size = (p.get("account_sizes") or {}).get(str(int(account_size))) or {}
    return {
        "product_id": product_id,
        "account_size": int(account_size),
        "pricing_status": p.get("pricing_status", "NOT_MODELED"),
        "acquisition_model": p.get("acquisition_model"),
        "notes": p.get("notes"),
        "sources": p.get("sources", []),
        **size,
    }
