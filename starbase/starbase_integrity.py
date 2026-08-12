from __future__ import annotations

import hashlib
import io
import json
import math
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from starbase_rulebook import rule_truth_for

STARBASE_VERSION = "3.5.0"
INTEGRITY_SCHEMA_VERSION = "1.0.0"
GENESIS_HASH = "0" * 64

EXECUTION_FIDELITY = {
    "EXACT_PROFILE": {
        "label": "Exact profile",
        "production_grade": True,
        "description": "Actual exported execution profile, such as a TradingView 1NQ or 2NQ run.",
    },
    "DERIVED_SHADOW": {
        "label": "Derived / shadow",
        "production_grade": False,
        "description": "Research replay derived from an exact profile using available path diagnostics such as MAE/MFE.",
    },
    "SYNTHETIC_GEOMETRY": {
        "label": "Synthetic geometry",
        "production_grade": False,
        "description": "Research-only scaling that preserves source price geometry rather than exact fixed-dollar execution behavior.",
    },
    "UNRESOLVED": {
        "label": "Unresolved / censored",
        "production_grade": False,
        "description": "The requested outcome needs price path information unavailable after the original exit.",
    },
}

RULE_COVERAGE_STATUS = {
    "VERIFIED": "Required core fields and official-source provenance are present for the requested stage.",
    "PARTIAL": "Some load-bearing numeric or lifecycle rules remain incomplete or conditional.",
    "UNVERIFIED": "Rule provenance or verification status is insufficient for trusted lifecycle execution.",
    "NOT_MODELED": "The requested stage or rule behavior is not yet implemented in trusted StarBase lifecycle logic.",
}

DRAW_DOWN_CLASS_DEFAULTS = {
    "EOD_TRAILING": {
        "floor_update_basis": "END_OF_SESSION",
        "breach_test_basis": "INTRADAY_EQUITY_OR_MAE",
        "inference_status": "CLASS_DEFAULT_REQUIRES_PRODUCT_CONFIRMATION",
    },
    "INTRADAY_TRAILING": {
        "floor_update_basis": "INTRADAY_HIGH_EQUITY",
        "breach_test_basis": "INTRADAY_EQUITY_OR_MAE",
        "inference_status": "CLASS_DEFAULT_REQUIRES_PRODUCT_CONFIRMATION",
    },
    "STATIC": {
        "floor_update_basis": "STATIC",
        "breach_test_basis": "INTRADAY_EQUITY_OR_MAE",
        "inference_status": "CLASS_DEFAULT_REQUIRES_PRODUCT_CONFIRMATION",
    },
    "NONE": {
        "floor_update_basis": "NONE",
        "breach_test_basis": "NONE",
        "inference_status": "NO_DRAWDOWN_CLASS",
    },
    "SELECTABLE_EOD_OR_INTRADAY": {
        "floor_update_basis": "CHECKOUT_SELECTION_REQUIRED",
        "breach_test_basis": "INTRADAY_EQUITY_OR_MAE",
        "inference_status": "VARIANT_SELECTION_REQUIRED",
    },
}


class IntegrityValidationError(ValueError):
    pass


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def make_run_id(config: Dict[str, Any], source_hashes: Dict[str, str], rulebook_hash: str,
                engine_version: str = STARBASE_VERSION) -> str:
    payload = {
        "engine_version": engine_version,
        "config": config,
        "source_hashes": dict(sorted(source_hashes.items())),
        "rulebook_hash": rulebook_hash,
    }
    digest = sha256_text(stable_json(payload))[:12]
    return f"SB-{engine_version.replace('.', '')}-{digest}"


def execution_fidelity_info(code: str) -> Dict[str, Any]:
    if code not in EXECUTION_FIDELITY:
        raise IntegrityValidationError(f"Unknown execution fidelity: {code}")
    return dict(EXECUTION_FIDELITY[code])


def drawdown_semantics(drawdown_type: Optional[str], explicit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    explicit = explicit or {}
    base = dict(DRAW_DOWN_CLASS_DEFAULTS.get(drawdown_type or "NONE", {
        "floor_update_basis": "UNKNOWN",
        "breach_test_basis": "UNKNOWN",
        "inference_status": "UNKNOWN_DRAWDOWN_CLASS",
    }))
    for key in ("floor_update_basis", "breach_test_basis", "breach_frequency", "floor_lock_behavior"):
        if explicit.get(key) is not None:
            base[key] = explicit[key]
    if explicit:
        base["inference_status"] = explicit.get("verification_status", "EXPLICIT_STAGE_OVERRIDE")
    base["drawdown_type"] = drawdown_type
    return base


def _find_product(rulebook: Dict[str, Any], product_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    for firm in rulebook.get("firms", []):
        for product in firm.get("products", []):
            if product.get("product_id") == product_id:
                return firm, product
    raise KeyError(product_id)


def assess_rule_coverage(rulebook: Dict[str, Any], product_id: str, account_size: int, stage: str) -> Dict[str, Any]:
    firm, product = _find_product(rulebook, product_id)
    size_rules = product.get("account_sizes", {}).get(str(int(account_size)))
    missing: List[str] = []
    warnings: List[str] = []
    if size_rules is None:
        return {
            "status": "NOT_MODELED", "missing": ["account_size"], "warnings": [],
            "product_id": product_id, "account_size": account_size, "stage": stage,
        }
    stage_rules = size_rules.get(stage)
    if not stage_rules:
        return {
            "status": "NOT_MODELED", "missing": [stage], "warnings": [],
            "product_id": product_id, "account_size": account_size, "stage": stage,
        }

    if not product.get("sources") and not firm.get("sources"):
        missing.append("official_sources")
    if not product.get("verified_date"):
        missing.append("verified_date")
    if stage_rules.get("drawdown_type") is None:
        missing.append("drawdown_type")

    if stage == "evaluation":
        for field in ("profit_target", "max_loss"):
            if stage_rules.get(field) is None:
                missing.append(field)
    elif stage == "sim_funded":
        if stage_rules.get("max_loss") is None:
            warnings.append("funded max_loss is not encoded")
        if not stage_rules.get("payout") and stage_rules.get("payout_cadence") is None:
            warnings.append("funded payout rules are incomplete")

    verification = product.get("verification_status", "UNKNOWN")
    readiness = product.get("simulation_readiness", "UNKNOWN")
    truth = rule_truth_for(product, stage)
    truth_grade = truth.get("grade", "NOT_MODELED")
    if missing:
        status = "PARTIAL"
    elif truth_grade == "PRODUCTION_READY":
        status = "VERIFIED"
    elif truth_grade in {"RULES_VERIFIED_ENGINE_PENDING", "VARIANT_SELECTION_REQUIRED", "RESEARCH_ONLY"}:
        status = "PARTIAL"
        warnings.extend(truth.get("unmodeled_reasons") or [])
    elif truth_grade == "NOT_MODELED":
        status = "NOT_MODELED"
        warnings.extend(truth.get("unmodeled_reasons") or [])
    elif verification.startswith("VERIFIED") and readiness in {"READY_FOR_V4_CORE", "READY_FOR_TRUSTED_CORE"}:
        status = "VERIFIED"
    else:
        status = "UNVERIFIED"

    return {
        "status": status,
        "description": RULE_COVERAGE_STATUS[status],
        "missing": missing,
        "warnings": warnings,
        "verification_status": verification,
        "simulation_readiness": readiness,
        "rule_truth_grade": truth_grade,
        "rankable": bool(truth.get("rankable")),
        "unmodeled_reasons": list(truth.get("unmodeled_reasons") or []),
        "product_id": product_id,
        "product": product.get("display_name"),
        "firm": firm.get("display_name"),
        "account_size": int(account_size),
        "stage": stage,
        "drawdown_semantics": drawdown_semantics(stage_rules.get("drawdown_type"), stage_rules.get("drawdown_semantics")),
    }


def independent_trial_max_abs_z(trials: int, familywise_confidence: float = 0.95) -> float:
    """Reference max-|Z| threshold under independent N(0,1) trials.

    This is a research warning, not a p-value correction for correlated strategy searches.
    """
    if trials < 1:
        raise ValueError("trials must be >= 1")
    if not 0 < familywise_confidence < 1:
        raise ValueError("familywise_confidence must be between 0 and 1")
    per_trial_cdf_abs = familywise_confidence ** (1.0 / trials)
    phi = (1.0 + per_trial_cdf_abs) / 2.0
    return NormalDist().inv_cdf(phi)


def bootstrap_futures_sessions(session_ids: Sequence[str], n_sessions: Optional[int] = None,
                               seed: int = 0) -> List[str]:
    """Deterministically sample whole futures sessions with replacement.

    A light-weight foundation for future Monte Carlo. Trade rows remain grouped by session.
    """
    import random
    unique = list(dict.fromkeys(str(x) for x in session_ids))
    if not unique:
        return []
    count = n_sessions if n_sessions is not None else len(unique)
    rng = random.Random(seed)
    return [rng.choice(unique) for _ in range(count)]


def build_run_manifest(*, config: Dict[str, Any], source_hashes: Dict[str, str], rulebook_hash: str,
                       execution_fidelity: str, rulebook_schema_version: str,
                       random_seed: Optional[int] = None, notes: str = "") -> Dict[str, Any]:
    fidelity = execution_fidelity_info(execution_fidelity)
    run_id = make_run_id(config, source_hashes, rulebook_hash)
    return {
        "manifest_schema_version": INTEGRITY_SCHEMA_VERSION,
        "starbase_version": STARBASE_VERSION,
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "execution_fidelity": execution_fidelity,
        "execution_fidelity_label": fidelity["label"],
        "production_grade_execution": bool(fidelity["production_grade"]),
        "rulebook_schema_version": rulebook_schema_version,
        "rulebook_hash": rulebook_hash,
        "source_hashes": dict(sorted(source_hashes.items())),
        "config": config,
        "random_seed": random_seed,
        "notes": notes,
    }


def parse_ledger_jsonl(raw: bytes | str | None) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    out = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise IntegrityValidationError(f"Invalid ledger JSON on line {line_no}") from exc
    return out


def validate_ledger_chain(entries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    prev = GENESIS_HASH
    for idx, entry in enumerate(entries):
        if entry.get("prev_hash") != prev:
            return {"valid": False, "index": idx, "reason": "prev_hash mismatch"}
        payload = {k: v for k, v in entry.items() if k != "entry_hash"}
        expected = sha256_text(stable_json(payload))
        if entry.get("entry_hash") != expected:
            return {"valid": False, "index": idx, "reason": "entry_hash mismatch"}
        prev = expected
    return {"valid": True, "entries": len(entries), "head_hash": prev}


def append_ledger_entry(entries: Sequence[Dict[str, Any]], payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    validation = validate_ledger_chain(entries)
    if not validation.get("valid"):
        raise IntegrityValidationError(f"Cannot append to invalid ledger: {validation}")
    prev = validation.get("head_hash", GENESIS_HASH)
    entry = dict(payload)
    entry.setdefault("created_at_utc", datetime.now(timezone.utc).isoformat())
    entry["prev_hash"] = prev
    entry["entry_hash"] = sha256_text(stable_json(entry))
    return list(entries) + [entry]


def ledger_to_jsonl(entries: Sequence[Dict[str, Any]]) -> bytes:
    return ("\n".join(stable_json(e) for e in entries) + ("\n" if entries else "")).encode("utf-8")


def build_research_bundle(manifest: Dict[str, Any], ledger_entries: Sequence[Dict[str, Any]],
                          extra_files: Optional[Dict[str, bytes]] = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("RUN_MANIFEST.json", json.dumps(manifest, indent=2, sort_keys=True))
        zf.writestr("EXPERIMENT_LEDGER.jsonl", ledger_to_jsonl(ledger_entries))
        integrity = {
            "run_id": manifest.get("run_id"),
            "ledger_validation": validate_ledger_chain(ledger_entries),
            "manifest_sha256": sha256_text(stable_json(manifest)),
        }
        zf.writestr("INTEGRITY.json", json.dumps(integrity, indent=2, sort_keys=True))
        for name, data in (extra_files or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()
