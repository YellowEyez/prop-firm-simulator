import pandas as pd

from starbase_rulebook import load_rulebook
from starbase_lifecycle import LifecycleConfig, run_stage, run_lifecycle, comparison_rows


def _ledger(rows):
    base=[]
    for i,r in enumerate(rows, start=1):
        day=r.get('day',i)
        base.append({
            'strategy_id':'T','profile_id':'1NQ','source_file':'x.csv','source_trade_id':i,
            'entry_time_et':f"2026-01-{day:02d}T10:00:00-05:00",
            'exit_time_et':f"2026-01-{day:02d}T10:01:00-05:00",
            'futures_session_id':f"2026-01-{day:02d}", 'direction':'long',
            'entry_price':20000.0,'exit_price':20001.0,'contracts':r.get('contracts',1),
            'exported_net_pnl':r.get('pnl',0),'exported_commission':0.0,'normalized_gross_pnl':r.get('pnl',0),
            'firm_commission_pnl':0.0,'MFE':r.get('mfe', max(0,r.get('pnl',0))), 'MAE':r.get('mae', min(0,r.get('pnl',0))),
            'entry_signal':'E','exit_signal':'X','validity_status':'VALID','validity_reason':'','review_status':'CLEAR',
            'hold_seconds':60,'hold_minutes':1,'duration_bars':6,'seconds_per_bar':10,'implied_contracts_from_pnl':1,
            'pnl_math_difference':0,'exact_duplicate':False,'duplicate_of':'','source_sha256':'abc','audit_warnings':''
        })
    return pd.DataFrame(base)


def test_evaluation_stops_when_lucid_target_and_consistency_met():
    rb=load_rulebook()
    df=_ledger([{'day':1,'pnl':1500,'mae':-100},{'day':2,'pnl':1500,'mae':-100},{'day':3,'pnl':1000,'mae':-100}])
    r=run_stage(rb,df,LifecycleConfig('lucid_flex',50000,'EVALUATION_ONLY',commission_per_contract_round_trip=0),'evaluation')
    assert r.summary['status']=='PASSED'
    assert r.summary['pass_session']=='2026-01-02'
    assert r.summary['trades_routed']==2
    assert r.summary['ending_balance']==53000


def test_lucid_funded_takes_rule_based_payout():
    rb=load_rulebook()
    df=_ledger([{'day':d,'pnl':500,'mae':-100} for d in range(1,6)])
    r=run_stage(rb,df,LifecycleConfig('lucid_flex',50000,'FUNDED_ONLY',commission_per_contract_round_trip=0),'sim_funded')
    assert r.summary['payout_count']==1
    assert abs(r.summary['gross_payouts_deducted']-1250)<1e-9
    assert abs(r.summary['trader_wallet_cash']-1125)<1e-9
    assert abs(r.summary['ending_balance']-51250)<1e-9
    assert abs(r.summary['ending_failure_floor']-50100)<1e-9


def test_fundednext_payout_and_share_differ_from_lucid():
    rb=load_rulebook()
    df=_ledger([{'day':d,'pnl':500,'mae':-100} for d in range(1,6)])
    r=run_stage(rb,df,LifecycleConfig('fundednext_flex',50000,'FUNDED_ONLY',commission_per_contract_round_trip=0),'sim_funded')
    assert r.summary['payout_count']==1
    assert abs(r.summary['gross_payouts_deducted']-1250)<1e-9
    assert abs(r.summary['trader_wallet_cash']-1000)<1e-9
    assert abs(r.summary['ending_failure_floor']-50100)<1e-9


def test_mffu_funded_uses_zero_profit_balance_not_50k():
    rb=load_rulebook()
    df=_ledger([{'day':d,'pnl':500,'mae':-100} for d in range(1,6)])
    r=run_stage(rb,df,LifecycleConfig('mffu_flex_50k',50000,'FUNDED_ONLY',commission_per_contract_round_trip=0),'sim_funded')
    assert r.summary['starting_balance']==0
    assert r.summary['initial_failure_floor']==-2000
    assert r.summary['payout_count']==1
    assert r.summary['ending_balance']==1250
    assert r.summary['ending_failure_floor']==100


def test_apex_payout_uses_safety_net_and_100_percent_share():
    rb=load_rulebook()
    df=_ledger([{'day':d,'pnl':600,'mae':-100} for d in range(1,6)])
    r=run_stage(rb,df,LifecycleConfig('apex_eod',50000,'FUNDED_ONLY',commission_per_contract_round_trip=0),'sim_funded')
    assert r.summary['payout_count']==1
    assert abs(r.summary['trader_wallet_cash']-900)<1e-9
    assert abs(r.summary['ending_balance']-52100)<1e-9


def test_eval_to_funded_lineage_uses_only_later_sessions_for_funded():
    rb=load_rulebook()
    rows=[{'day':1,'pnl':1500,'mae':-100},{'day':2,'pnl':1500,'mae':-100}]
    rows += [{'day':d,'pnl':500,'mae':-100} for d in range(3,8)]
    r=run_lifecycle(rb,_ledger(rows),LifecycleConfig('lucid_flex',50000,'EVAL_TO_FUNDED',commission_per_contract_round_trip=0))
    assert r.summary['evaluation_status']=='PASSED'
    assert r.funded is not None
    assert r.funded.summary['trades_routed']==5
    assert r.summary['funded_payouts']==1


def test_comparison_lab_produces_distinct_wallet_cash():
    rb=load_rulebook()
    df=_ledger([{'day':d,'pnl':500,'mae':-100} for d in range(1,6)])
    configs=[
        LifecycleConfig('lucid_flex',50000,'FUNDED_ONLY',commission_per_contract_round_trip=0),
        LifecycleConfig('fundednext_flex',50000,'FUNDED_ONLY',commission_per_contract_round_trip=0),
    ]
    out=comparison_rows(rb,df,configs)
    assert len(out)==2
    assert out.loc[0,'wallet_cash'] != out.loc[1,'wallet_cash']


def test_session_ledger_separates_trading_pnl_from_payout_deduction():
    rb=load_rulebook()
    df=_ledger([{'day':d,'pnl':500,'mae':-100} for d in range(1,6)])
    r=run_stage(rb,df,LifecycleConfig('lucid_flex',50000,'FUNDED_ONLY',commission_per_contract_round_trip=0),'sim_funded')
    last=r.sessions.iloc[-1]
    assert last['session_source_trade_net_pnl']==500
    assert last['session_account_realized_trading_pnl']==500
    assert last['pre_payout_balance']==52500
    assert last['payout_deduction_gross']==1250
    assert last['payout_cash_to_trader']==1125
    assert last['session_end_balance']==51250
