# StarBase v5E Validation Report

## Release status

- Release: **StarBase v5E — Current Prop-Firm Rule Truth Layer**
- User-certified entering release: **26 / 60 core steps**
- Implemented here: **Step 26 — Complete current rule semantics / Rule Truth Layer**
- Deployment certification: **PENDING USER SMOKE TEST**
- Next sequential target after certification: **Step 27 — Golden Single-Account Verification**
- Rulebook schema: **3.1.0**
- Rulebook verified-as-of date: **2026-08-12**

## What v5E validates

v5E separates three concepts that must not be conflated:

1. Official firm documentation exists and has been re-verified.
2. StarBase has encoded the current rule semantics and variants.
3. StarBase has a dedicated, golden-tested lifecycle handler that is safe to rank as production-grade.

A product can therefore be current and documented while still being `RULES_VERIFIED_ENGINE_PENDING`, `VARIANT_SELECTION_REQUIRED`, or `RESEARCH_ONLY`.

## Key current-rule corrections / additions

- Apex EOD Evaluation: current 30-day EOD product; 50K target $3,000, EOD MDD $2,000, soft DLL $1,000, max 6 minis, no consistency, no minimum trading days. Current EOD evaluation no longer uses the old StarBase platform-variant gate for passing logic.
- Apex EOD PA: current tier-based position sizing / DLL structure and six-payout sequence encoded; remains engine-pending until tier behavior is golden-tested.
- Tradeify Select: funded path is split into Select Flex and Select Daily because their DLL/buffer/payout structures differ materially.
- FundedNext Flex 50K: max 3 minis / 30 micros; five $200 Benchmark Days, $500 cycle minimum, max $1,500 withdrawal, current Flex reward share 95%, first reward MLL locks at $50,100. Reward/withdrawal-processing variants are recorded rather than silently generalized.
- Topstep XFA: Standard and Consistency payout paths are separate. Standard uses five $150 winning days; Consistency uses three days and a 40% consistency target.
- Current rule-truth / rankability status is explicit for Lucid, Apex, Tradeify, FundedNext, MFFU, Topstep, and Take Profit Trader products currently represented in the rulebook.

## Automated validation

### Complete pytest suite

Command:

```text
PYTHONPATH=. pytest -q
```

Result:

```text
98 passed
```

This is the broadest automated suite and includes pytest-style and unittest-compatible tests.

### unittest subset

Command:

```text
python -m unittest discover -s tests -q
```

Result:

```text
Ran 52 tests
OK
```

The unittest count is smaller because not every pytest-style test is discoverable by unittest.

### Python compilation

Command:

```text
python -m py_compile *.py tests/*.py
```

Result: **PASS**

### Deployment file audit

Command:

```text
python verify_starbase_install.py --files-only
```

Result: **PASS**

The local build environment used for packaging does not include Streamlit itself, so dependency imports are intentionally skipped with `--files-only`; Streamlit dependencies remain declared in `requirements.txt` and will be exercised by Community Cloud deployment.

## Rule Truth regression tests added

v5E includes dedicated tests covering:

- rulebook verified date / freshness;
- FundedNext Flex 50K contract limit = 3 minis;
- FundedNext current 95% Flex reward share and explicit 80% standard override path;
- Tradeify Select Flex vs Select Daily separation;
- Topstep Standard vs Consistency separation;
- consistency-category filtering;
- Take Profit Trader research-only / not-rankable status;
- LucidDaily variant-selection requirement;
- production/rankability gating;
- Apex EOD PA tier-DLL data;
- current Apex EOD evaluation platform-agnostic pass path.

## TradingView source regression

Six Sydney 10s source segments were re-audited after the v5E changes.

Expected / observed:

- Files parsed: **6**
- Parsed records: **4,465**
- Strict valid: **4,342**
- Review: **96**
- Invalid: **27**
- Futures sessions: **326**
- Strict normalized gross P&L: **$22,230.00**
- Strict win rate: **61.4924%**

Result: **PASS — source trading path unchanged by Step 26**

## Deliberately not promoted to production-ready yet

Rule verification is not engine certification. v5E intentionally leaves several documented paths non-rankable until Step 27 proves their mechanics with hand-calculated fixtures. Examples include:

- Apex EOD PA tiered DLL / contract scaling;
- Tradeify Select Flex / Daily scaling and payout path details;
- FundedNext Flex reward-share / withdrawal-processing selection;
- LucidDirect dynamic LucidScale DLL;
- LucidDaily selectable variants and news-rule implications;
- MFFU tier scaling;
- Topstep Standard / Consistency dedicated lifecycle handlers;
- Take Profit Trader news-window / discretionary live-review behavior.

This is a safety feature, not missing data.

## Deployment certification test

The user should verify the v5E Rule Truth workspace shows the 2026-08-12 verified date and that the following representative rows are visible:

1. **FundedNext Flex 50K**: 3 minis, evaluation consistency 40%, funded consistency none, five $200 Benchmark Days, current 95% Flex reward share; non-rankable until variant/engine selection is certified.
2. **Tradeify Select 50K**: separate Flex and Daily paths. Flex has no funded DLL; Daily has a $1,000 DLL, $2,100 buffer, and $250 minimum payout.
3. **Topstep 50K**: separate Standard and Consistency XFA paths. Standard = five $150 winning days; Consistency = three days + 40% consistency.
4. **Apex EOD 50K Evaluation**: no consistency, $1,000 soft DLL, 30-day access period, max 6 minis, current EOD evaluation path does not require an Rithmic/Tradovate selection to determine pass/fail.

If those checks pass in deployed Streamlit, Step 26 can be marked deployment-certified and the official scoreboard becomes **27 / 60**.
