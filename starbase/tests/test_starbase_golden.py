from starbase_golden import run_golden_suite, run_lineage_fixture, run_comparison_fixture


def test_full_golden_suite_passes():
    s = run_golden_suite()
    assert s["total"] == 13
    assert s["passed"] == 13
    assert s["failed"] == 0
    assert s["all_pass"] is True
    assert s["rulebook_schema"] == "3.1.0"


def test_golden_lineage_proves_fresh_funded_start():
    r = run_lineage_fixture()
    assert r["pass"] is True
    check = {x["field"]: x for x in r["checks"]}
    assert check["funded_starting_balance"]["actual"] == 50000.0
    assert check["funded_starting_balance"]["expected"] == 50000.0


def test_golden_comparison_proves_distinct_product_outcomes():
    r = run_comparison_fixture()
    assert r["pass"] is True
    assert list(r["rows"]["wallet_cash"]) == [1125.0, 1187.5]
