import math
import pandas as pd

from starbase_historical_runner import RunnerConfig, capacity_slots_for_capture, resolve_drawdown_policy, run_single_account_history, theoretical_tp_sl
from starbase_rulebook import load_rulebook


def _ledger(rows):
    base=[]
    for i,r in enumerate(rows, start=1):
        base.append({
            'strategy_id':'T','profile_id':'1NQ','source_file':'x.csv','source_trade_id':i,
            'entry_time_et':f"2026-01-{r.get('day',1):02d}T10:{i%60:02d}:00-05:00",
            'exit_time_et':f"2026-01-{r.get('day',1):02d}T10:{(i+1)%60:02d}:00-05:00",
            'futures_session_id':f"2026-01-{r.get('day',1):02d}", 'direction':'long',
            'entry_price':20000.0,'exit_price':20001.0,'contracts':r.get('contracts',1),
            'exported_net_pnl':r.get('pnl',0),'exported_commission':0.0,'normalized_gross_pnl':r.get('pnl',0),
            'firm_commission_pnl':0.0,'MFE':r.get('mfe', max(0,r.get('pnl',0))), 'MAE':r.get('mae', min(0,r.get('pnl',0))),
            'entry_signal':'E','exit_signal':'X','validity_status':r.get('status','VALID'),'validity_reason':'','review_status':'CLEAR',
            'hold_seconds':60,'hold_minutes':1,'duration_bars':6,'seconds_per_bar':10,'implied_contracts_from_pnl':1,
            'pnl_math_difference':0,'exact_duplicate':False,'duplicate_of':'','source_sha256':'abc','audit_warnings':''
        })
    return pd.DataFrame(base)


def test_one_trade_per_session_cap_preserves_unused_signals():
    rb=load_rulebook()
    df=_ledger([{'day':1,'pnl':300,'mae':-100},{'day':1,'pnl':300,'mae':-100},{'day':1,'pnl':300,'mae':-100}])
    r=run_single_account_history(rb, df, RunnerConfig('lucid_flex',50000,'evaluation',max_trades_per_session=1,commission_per_contract_round_trip=0))
    assert r.summary['trades_routed']==1
    assert r.summary['signals_skipped_by_session_cap_or_pause']==2
    assert r.summary['ending_balance']==50300


def test_mae_breach_kills_winner_before_recovery():
    rb=load_rulebook()
    # Initial Lucid50 floor 48k. A +325 winner with -2100 MAE must die first.
    df=_ledger([{'day':1,'pnl':325,'mae':-2100,'mfe':400}])
    r=run_single_account_history(rb, df, RunnerConfig('lucid_flex',50000,'evaluation',commission_per_contract_round_trip=0))
    assert r.summary['status']=='FAILED'
    assert r.summary['ending_balance']==48000
    assert bool(r.trades.iloc[0]['breach']) is True


def test_lucid_eod_floor_ratchets_and_locks_at_50100():
    rb=load_rulebook()
    rows=[{'day':1,'pnl':1000,'mae':-100},{'day':2,'pnl':1200,'mae':-100}]
    r=run_single_account_history(rb,_ledger(rows),RunnerConfig('lucid_flex',50000,'evaluation',commission_per_contract_round_trip=0))
    # Day1 close 51k -> floor 49k. Day2 close 52.2k -> raw 50.2k, capped to 50.1k.
    assert abs(r.summary['ending_failure_floor']-50100)<1e-9


def test_tradeify_evaluation_does_not_lock_floor():
    rb=load_rulebook()
    pol=resolve_drawdown_policy(rb,RunnerConfig('tradeify_select_flex',50000,'evaluation'))
    assert pol.floor_lock_behavior=='NO_LOCK_EVALUATION'
    assert pol.lock_floor is None


def test_apex_eval_requires_platform_for_production_grade_policy():
    rb=load_rulebook()
    p0=resolve_drawdown_policy(rb,RunnerConfig('apex_eod',50000,'evaluation',platform_variant='DEFAULT'))
    assert p0.confidence=='PARTIAL_REQUIRES_PLATFORM'
    p1=resolve_drawdown_policy(rb,RunnerConfig('apex_eod',50000,'evaluation',platform_variant='RITHMIC'))
    assert p1.lock_floor==53000


def test_commission_is_per_contract():
    rb=load_rulebook()
    df=_ledger([{'day':1,'pnl':300,'contracts':2,'mae':-100}])
    r=run_single_account_history(rb,df,RunnerConfig('lucid_flex',50000,'evaluation',commission_per_contract_round_trip=3.5))
    assert abs(r.summary['total_firm_commissions']-7.0)<1e-9
    assert abs(r.summary['ending_balance']-50293.0)<1e-9


def test_tp_sl_calculator_does_not_mutate_history():
    x=theoretical_tp_sl(observed_win_rate=.65, proposed_tp=315, proposed_sl=500, commission=3.5)
    assert 0 < x['break_even_win_rate'] < 1
    assert math.isfinite(x['theoretical_expectancy_at_observed_win_rate'])


def test_capacity_slots_for_capture_uses_whole_session_signal_counts():
    df=_ledger([{'day':1,'pnl':1},{'day':1,'pnl':1},{'day':1,'pnl':1},{'day':2,'pnl':1}])
    slots=capacity_slots_for_capture(df,targets=(0.5,0.75,1.0))
    assert slots[0.5]==1
    assert slots[0.75]==2
    assert slots[1.0]==3
