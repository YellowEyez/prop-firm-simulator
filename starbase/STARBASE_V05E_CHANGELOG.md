# StarBase v5E — Rule Truth Layer

## Progress
- Deployment-certified entering this release: **26 / 60**.
- Implements Step 26; deployment certification pending.
- Next sequential target after certification: Step 27 Golden Single-Account Verification.

## Major changes
- Rulebook schema 3.1.0, verified as of 2026-08-12.
- Adds stage-level Rule Truth grades and rankability flags.
- Separates official rule verification from engine implementation coverage.
- Adds evaluation/funded consistency filters and trusted/rankable filter.
- Adds separate Tradeify Select Flex and Select Daily funded paths.
- Adds separate Topstep XFA Standard and XFA Consistency paths.
- Corrects FundedNext Flex 50K contract limit to 3 minis / 30 micros.
- Encodes FundedNext reward-share variants and current 95% new-purchase promotion, while flagging reward-share/withdrawal-fee variant dependence.
- Encodes Apex EOD PA tiered DLL/position scaling and current payout caps/qualifying-day rules.
- Corrects current Apex EOD Evaluation semantics so legacy/intraday platform trailing differences are not applied to the current EOD Evaluation.
- Encodes LucidDirect LucidScale DLL semantics, LucidDaily checkout variants/news rule, MFFU Flex scaling, MFFU Rapid payout structure, Topstep optional DLL paths, and current TPT 50K research semantics.
- Adds rulebook freshness status and visible unresolved-rule reasons.

## Safety behavior
Products can now be `RULES_VERIFIED_ENGINE_PENDING`, `VARIANT_SELECTION_REQUIRED`, or `RESEARCH_ONLY`. These remain visible for research but are not labeled production-ready merely because official documentation exists.
