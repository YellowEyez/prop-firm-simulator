"""StarBase v5E Rule Truth helpers.

This layer distinguishes three separate questions:
1) Are the firm's current rules documented from official sources?
2) Does the requested product/stage require a variant selection or external event data?
3) Does StarBase have a trusted engine handler for that stage?

Rule documentation does not automatically imply simulation/ranking support.
"""
from __future__ import annotations
from typing import Any, Dict, List

from starbase_rulebook import product_details, rule_truth_for

RULE_TRUTH_LAYER_VERSION = "5E.1.0"


def stage_truth(rulebook: Dict[str, Any], product_id: str, stage: str) -> Dict[str, Any]:
    details = product_details(rulebook, product_id)
    p = details["product"]
    truth = rule_truth_for(p, stage)
    return {
        "firm_id": details["firm"]["firm_id"],
        "firm": details["firm"]["display_name"],
        "product_id": p["product_id"],
        "product": p["display_name"],
        "stage": stage,
        "verified_date": p.get("verified_date"),
        "verification_status": p.get("verification_status"),
        "grade": truth.get("grade", "NOT_MODELED"),
        "rankable": bool(truth.get("rankable")),
        "unmodeled_reasons": list(truth.get("unmodeled_reasons") or []),
        "source_urls": list(dict.fromkeys((details["firm"].get("sources") or []) + (p.get("sources") or []))),
    }


def rule_truth_matrix(rulebook: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for firm in rulebook.get("firms", []):
        for p in firm.get("products", []):
            for stage in ("evaluation", "sim_funded", "live"):
                t = stage_truth(rulebook, p["product_id"], stage)
                if not any(stage in sr for sr in p.get("account_sizes", {}).values()):
                    t["grade"] = "NOT_MODELED"
                    t["rankable"] = False
                    if not t["unmodeled_reasons"]:
                        t["unmodeled_reasons"] = [f"No {stage} stage exists for this product."]
                rows.append(t)
    return rows


def can_rank(rulebook: Dict[str, Any], product_id: str, stage: str) -> bool:
    return bool(stage_truth(rulebook, product_id, stage).get("rankable"))


def unresolved_reason_text(rulebook: Dict[str, Any], product_id: str, stage: str) -> str:
    reasons = stage_truth(rulebook, product_id, stage).get("unmodeled_reasons") or []
    return " | ".join(str(x) for x in reasons) if reasons else "None"
