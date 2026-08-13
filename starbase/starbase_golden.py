"""StarBase v5F hand-calculated golden-account verification suite.

Expected values in this file are intentionally hard-coded independent controls. They are
not calculated from the rulebook. Each fixture supplies a tiny synthetic trade history to
the lifecycle engine and compares actual account state against a hand-calculated expected
result. This makes rule-engine drift visible instead of letting a large backtest hide it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import math

import pandas as pd

from starbase_lifecycle import LifecycleConfig, comparison_rows, run_lifecycle, run_stage
from starbase_rulebook import load_rulebook

GOLDEN_SUITE_VERSION = "5F.1.0"


@dataclass(frozen=True)
class GoldenFixture:
    fixture_id: str
    title: str
    product_id: str
    account_size: int
    stage: str
    pnls: List[float]
    expected: Dict[str, Any]
    purpose: str
    confidence: str = "FULL_CORE"
    mae_values: Optional[List[float]] = None
    mode: Optional[str] = None
    reward_share_override_percent: Optional[float] = None


def _ledger(pnls: List[float], mae_values: Optional[List[float]] = None) -> pd.DataFrame:
    rows = []
    for i, pnl in enumerate(pnls, start=1):
        mae = (mae_values[i - 1] if mae_values is not None else min(0.0, float(pnl)))
        rows.append({
            "strategy_id": "GOLDEN",
            "profile_id": "1NQ_GOLDEN",
            "source_file": "golden_fixture.csv",
            "source_trade_id": i,
            "entry_time_et": f"2026-01-{i:02d}T10:00:00-05:00",
            "exit_time_et": f"2026-01-{i:02d}T10:01:00-05:00",
            "futures_session_id": f"2026-01-{i:02d}",
            "direction": "long",
            "entry_price": 20000.0,
            "exit_price": 20001.0,
            "contracts": 1,
            "exported_net_pnl": float(pnl),
            "exported_commission": 0.0,
            "normalized_gross_pnl": float(pnl),
            "firm_commission_pnl": 0.0,
            "MFE": max(0.0, float(pnl)),
            "MAE": float(mae),
            "entry_signal": "GOLDEN_ENTRY",
            "exit_signal": "GOLDEN_EXIT",
            "validity_status": "VALID",
            "validity_reason": "",
            "review_status": "CLEAR",
            "hold_seconds": 60,
            "hold_minutes": 1,
            "duration_bars": 6,
            "seconds_per_bar": 10,
            "implied_contracts_from_pnl": 1,
            "pnl_math_difference": 0.0,
            "exact_duplicate": False,
            "duplicate_of": "",
            "source_sha256": "golden_fixture",
            "audit_warnings": "",
        })
    return pd.DataFrame(rows)


FIXTURES: List[GoldenFixture] = [
    GoldenFixture(
        "G01_LUCID_EVAL_PASS_STOP",
        "LucidFlex 50K evaluation passes and stops",
        "lucid_flex", 50000, "evaluation", [1500, 1500, 900],
        {"status": "PASSED", "pass_session": "2026-01-02", "trades_routed": 2,
         "signals_skipped_after_account_inactive": 1, "ending_balance": 53000.0},
        "Certifies Step 19: once the target/consistency path passes, later source trades are not credited to the finished evaluation.",
    ),
    GoldenFixture(
        "G02_LUCID_FUNDED_PAYOUT",
        "LucidFlex 50K funded first payout",
        "lucid_flex", 50000, "sim_funded", [500] * 5,
        {"starting_balance": 50000.0, "ending_balance": 51250.0, "ending_failure_floor": 50100.0,
         "payout_count": 1, "gross_payouts_deducted": 1250.0, "trader_wallet_cash": 1125.0},
        "Five +$500 sessions create $2,500 profit; 50% gross payout = $1,250 and 90% trader share = $1,125.",
    ),
    GoldenFixture(
        "G03_TRADEIFY_EVAL",
        "Tradeify Select Flex 50K evaluation target + 40% consistency + 3 days",
        "tradeify_select_flex", 50000, "evaluation", [1200, 900, 900],
        {"status": "PASSED", "pass_session": "2026-01-03", "trades_routed": 3,
         "ending_balance": 53000.0, "minimum_days_met": True, "consistency_pass": True},
        "$1,200 is exactly 40% of the $3,000 total; three sessions satisfy the minimum-day path.",
    ),
    GoldenFixture(
        "G04_TRADEIFY_FUNDED_PAYOUT",
        "Tradeify Select Flex 50K funded first payout core arithmetic",
        "tradeify_select_flex", 50000, "sim_funded", [500] * 5,
        {"ending_balance": 51250.0, "ending_failure_floor": 50100.0,
         "payout_count": 1, "gross_payouts_deducted": 1250.0, "trader_wallet_cash": 1125.0},
        "Core payout arithmetic fixture. Product remains engine-pending for funded contract-tier enforcement until later exact-profile work.",
        confidence="CORE_ARITHMETIC_ONLY",
    ),
    GoldenFixture(
        "G05_FUNDEDNEXT_EVAL",
        "FundedNext Flex 50K evaluation target + 40% consistency",
        "fundednext_flex", 50000, "evaluation", [1000, 750, 750],
        {"status": "PASSED", "pass_session": "2026-01-03", "trades_routed": 3,
         "ending_balance": 52500.0, "consistency_pass": True},
        "$1,000 is 40% of the $2,500 target, so the tiny path reaches target without violating the encoded consistency ceiling.",
    ),
    GoldenFixture(
        "G06_FUNDEDNEXT_FUNDED_95",
        "FundedNext Flex 50K funded first payout, 95% current-share variant",
        "fundednext_flex", 50000, "sim_funded", [500] * 5,
        {"ending_balance": 51250.0, "ending_failure_floor": 50100.0, "payout_count": 1,
         "gross_payouts_deducted": 1250.0, "trader_wallet_cash": 1187.50},
        "Tests the explicit 95% reward-share variant. Production ranking still requires a selected withdrawal-processing fee/share variant.",
        confidence="VARIANT_SPECIFIC",
    ),
    GoldenFixture(
        "G07_MFFU_EVAL",
        "MFFU Flex 50K evaluation passes after 2 balanced days",
        "mffu_flex_50k", 50000, "evaluation", [1500, 1500],
        {"status": "PASSED", "pass_session": "2026-01-02", "trades_routed": 2,
         "ending_balance": 53000.0, "minimum_days_met": True, "consistency_pass": True},
        "Balanced $1,500 + $1,500 reaches the $3,000 target with 50% consistency and two trading days.",
    ),
    GoldenFixture(
        "G08_MFFU_FUNDED_ZERO_BALANCE",
        "MFFU Flex 50K funded $0 P&L balance + first payout floor reset",
        "mffu_flex_50k", 50000, "sim_funded", [500] * 5,
        {"starting_balance": 0.0, "ending_balance": 1250.0, "ending_failure_floor": 100.0,
         "payout_count": 1, "gross_payouts_deducted": 1250.0, "trader_wallet_cash": 1000.0},
        "Protects the special $0 simulated-funded P&L accounting and $100 post-first-payout floor behavior.",
        confidence="CORE_ARITHMETIC_ONLY",
    ),
    GoldenFixture(
        "G09_APEX_EOD_EVAL",
        "Apex EOD 50K evaluation target termination",
        "apex_eod", 50000, "evaluation", [1500, 1500, 500],
        {"status": "PASSED", "pass_session": "2026-01-02", "trades_routed": 2,
         "signals_skipped_after_account_inactive": 1, "ending_balance": 53000.0},
        "Verifies current EOD evaluation target termination without applying the separate intraday-product platform assumptions.",
    ),
    GoldenFixture(
        "G10_APEX_EOD_FUNDED_PAYOUT",
        "Apex EOD 50K funded safety-net payout arithmetic",
        "apex_eod", 50000, "sim_funded", [600] * 5,
        {"ending_balance": 52100.0, "ending_failure_floor": 50100.0, "payout_count": 1,
         "gross_payouts_deducted": 900.0, "trader_wallet_cash": 900.0},
        "Five +$600 sessions reach $53,000; with the encoded $52,100 safety net the first available gross payout is $900.",
        confidence="CORE_ARITHMETIC_ONLY",
    ),
    GoldenFixture(
        "G11_LUCIDDIRECT_PAYOUT",
        "LucidDirect 50K first payout goal + 20% consistency core arithmetic",
        "lucid_direct", 50000, "sim_funded", [600] * 5,
        {"ending_balance": 51000.0, "ending_failure_floor": 50100.0, "payout_count": 1,
         "gross_payouts_deducted": 2000.0, "trader_wallet_cash": 1800.0},
        "Five equal $600 sessions produce $3,000 and exactly 20% largest-day consistency; first payout is capped at $2,000 gross.",
        confidence="CORE_ARITHMETIC_ONLY",
    ),
]


def _equal(a: Any, b: Any) -> bool:
    if isinstance(b, float):
        try:
            return math.isclose(float(a), b, rel_tol=0.0, abs_tol=1e-6)
        except Exception:
            return False
    return a == b


def run_fixture(fixture: GoldenFixture, rulebook: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rb = rulebook or load_rulebook()
    cfg = LifecycleConfig(
        fixture.product_id,
        fixture.account_size,
        mode=fixture.mode or ("FUNDED_ONLY" if fixture.stage == "sim_funded" else "EVALUATION_ONLY"),
        commission_per_contract_round_trip=0.0,
        include_review_rows=False,
        reward_share_override_percent=fixture.reward_share_override_percent,
    )
    stage = run_stage(rb, _ledger(fixture.pnls, fixture.mae_values), cfg, fixture.stage)
    actual = stage.summary
    checks = []
    for key, expected in fixture.expected.items():
        got = actual.get(key)
        checks.append({"field": key, "expected": expected, "actual": got, "pass": _equal(got, expected)})
    passed = all(x["pass"] for x in checks)
    return {
        "fixture_id": fixture.fixture_id,
        "title": fixture.title,
        "product_id": fixture.product_id,
        "account_size": fixture.account_size,
        "stage": fixture.stage,
        "purpose": fixture.purpose,
        "confidence": fixture.confidence,
        "pass": passed,
        "checks": checks,
        "summary": actual,
        "sessions": stage.sessions,
        "trades": stage.trades,
        "payouts": stage.payouts,
    }


def run_lineage_fixture(rulebook: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rb = rulebook or load_rulebook()
    result = run_lifecycle(
        rb,
        _ledger([1500, 1500, 500, 500, 500, 500, 500]),
        LifecycleConfig("lucid_flex", 50000, "EVAL_TO_FUNDED", commission_per_contract_round_trip=0.0),
    )
    expected = {
        "evaluation_status": "PASSED",
        "evaluation_pass_session": "2026-01-02",
        "funded_status": "ACTIVE",
        "funded_payouts": 1,
        "trader_wallet_cash": 1125.0,
        "ending_funded_balance": 51250.0,
    }
    checks = [{"field": k, "expected": v, "actual": result.summary.get(k), "pass": _equal(result.summary.get(k), v)} for k, v in expected.items()]
    # Critical anti-bug check: funded stage starts at 50k, not evaluation ending 53k.
    funded_start = None if result.funded is None else result.funded.summary.get("starting_balance")
    checks.append({"field": "funded_starting_balance", "expected": 50000.0, "actual": funded_start, "pass": _equal(funded_start, 50000.0)})
    return {
        "fixture_id": "G12_EVAL_TO_FRESH_FUNDED",
        "title": "LucidFlex evaluation -> fresh funded lineage",
        "purpose": "Certifies Step 20: evaluation profit does not carry into the funded account; only later sessions feed the fresh funded stage.",
        "confidence": "FULL_CORE",
        "pass": all(x["pass"] for x in checks),
        "checks": checks,
        "summary": result.summary,
    }


def run_comparison_fixture(rulebook: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rb = rulebook or load_rulebook()
    configs = [
        LifecycleConfig("lucid_flex", 50000, "FUNDED_ONLY", commission_per_contract_round_trip=0.0),
        LifecycleConfig("fundednext_flex", 50000, "FUNDED_ONLY", commission_per_contract_round_trip=0.0),
    ]
    rows = comparison_rows(rb, _ledger([500] * 5), configs)
    wallets = list(rows.get("wallet_cash", pd.Series(dtype=float)))
    passed = len(rows) == 2 and len(wallets) == 2 and math.isclose(float(wallets[0]), 1125.0, abs_tol=1e-6) and math.isclose(float(wallets[1]), 1187.5, abs_tol=1e-6) and wallets[0] != wallets[1]
    return {
        "fixture_id": "G13_COMPARISON_DIFFERENTIATION",
        "title": "Same exact trade path produces different product cash outcomes",
        "purpose": "Certifies Step 23: the comparison lab is using product-specific lifecycle rules rather than returning one generic funded result.",
        "confidence": "FULL_CORE",
        "pass": passed,
        "checks": [
            {"field": "comparison_row_count", "expected": 2, "actual": len(rows), "pass": len(rows) == 2},
            {"field": "Lucid wallet cash", "expected": 1125.0, "actual": wallets[0] if len(wallets) > 0 else None, "pass": len(wallets) > 0 and math.isclose(float(wallets[0]), 1125.0, abs_tol=1e-6)},
            {"field": "FundedNext wallet cash", "expected": 1187.5, "actual": wallets[1] if len(wallets) > 1 else None, "pass": len(wallets) > 1 and math.isclose(float(wallets[1]), 1187.5, abs_tol=1e-6)},
            {"field": "distinct outcomes", "expected": True, "actual": len(wallets) == 2 and wallets[0] != wallets[1], "pass": len(wallets) == 2 and wallets[0] != wallets[1]},
        ],
        "rows": rows,
    }


def run_golden_suite(rulebook: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rb = rulebook or load_rulebook()
    results = [run_fixture(x, rb) for x in FIXTURES]
    results.append(run_lineage_fixture(rb))
    results.append(run_comparison_fixture(rb))
    passed = sum(1 for x in results if x["pass"])
    summary_rows = [{
        "Fixture": x["fixture_id"],
        "Scenario": x["title"],
        "Confidence": x.get("confidence"),
        "Result": "PASS" if x["pass"] else "FAIL",
        "Purpose": x["purpose"],
    } for x in results]
    return {
        "suite_version": GOLDEN_SUITE_VERSION,
        "rulebook_schema": rb.get("schema_version"),
        "rulebook_verified_as_of": rb.get("verified_as_of"),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "all_pass": passed == len(results),
        "summary": pd.DataFrame(summary_rows),
        "results": results,
    }
