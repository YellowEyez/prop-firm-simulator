import pandas as pd

from starbase_rulebook import load_rulebook
from starbase_fleet import FleetConfig, raw_strategy_baseline, run_single_product_fleet


def _ledger(rows):
    base=[]
    for i,r in enumerate(rows, start=1):
        day=r.get('day',1)
        minute=r.get('minute',i)
        pnl=r.get('pnl',0)
        base.append({
            'strategy_id':'T','profile_id':'1NQ','source_file':'x.csv','source_trade_id':i,
            'entry_time_et':f"2026-01-{day:02d}T10:{minute%60:02d}:00-05:00",
            'exit_time_et':f"2026-01-{day:02d}T10:{(minute+1)%60:02d}:00-05:00",
            'futures_session_id':f"2026-01-{day:02d}", 'direction':'long',
            'entry_price':20000.0,'exit_price':20001.0,'contracts':r.get('contracts',1),
            'exported_net_pnl':pnl,'exported_commission':0.0,'normalized_gross_pnl':pnl,
            'firm_commission_pnl':0.0,'MFE':r.get('mfe', max(0,pnl)),'MAE':r.get('mae', min(0,pnl)),
            'entry_signal':'E','exit_signal':'X','validity_status':'VALID','validity_reason':'','review_status':'CLEAR',
            'hold_seconds':60,'hold_minutes':1,'duration_bars':6,'seconds_per_bar':10,'implied_contracts_from_pnl':1,
            'pnl_math_difference':0,'exact_duplicate':False,'duplicate_of':'','source_sha256':'abc','audit_warnings':''
        })
    return pd.DataFrame(base)


def test_raw_baseline_uses_every_signal_and_commission():
    df=_ledger([{'day':1,'pnl':100},{'day':1,'pnl':-50},{'day':2,'pnl':200}])
    r=raw_strategy_baseline(df, include_review_rows=False, commission_per_contract_round_trip=3.5)
    assert r['eligible_trades']==3
    assert r['futures_sessions']==2
    assert abs(r['gross_pnl']-250)<1e-9
    assert abs(r['commissions']-10.5)<1e-9
    assert abs(r['net_after_firm_commission']-239.5)<1e-9


def test_fixed_three_accounts_route_three_signals_per_session_at_cap_one():
    rb=load_rulebook()
    rows=[]
    for day in range(1,4):
        for j in range(3):
            rows.append({'day':day,'minute':j,'pnl':100,'mae':-10})
    run=run_single_product_fleet(rb,_ledger(rows),FleetConfig('lucid_flex',50000,'FIXED_FLEET',fixed_accounts=3,max_trades_per_account_per_session=1,commission_per_contract_round_trip=0,payout_request_mode='NONE'))
    assert run.summary['signals_routed']==9
    assert run.summary['signals_unrouted_capacity']==0
    assert run.summary['accounts_provisioned']==3
    assert (run.household_sessions['accounts_traded']==3).all()


def test_fixed_two_accounts_leave_third_signal_unrouted_each_session():
    rb=load_rulebook()
    rows=[]
    for day in range(1,4):
        for j in range(3):
            rows.append({'day':day,'minute':j,'pnl':100,'mae':-10})
    run=run_single_product_fleet(rb,_ledger(rows),FleetConfig('lucid_flex',50000,'FIXED_FLEET',fixed_accounts=2,max_trades_per_account_per_session=1,commission_per_contract_round_trip=0,payout_request_mode='NONE'))
    assert run.summary['signals_routed']==6
    assert run.summary['signals_unrouted_capacity']==3
    assert abs(run.summary['signal_capture_percent']-66.66666666666666)<1e-9


def test_force_100_capture_provisions_enough_accounts():
    rb=load_rulebook()
    df=_ledger([{'day':1,'minute':j,'pnl':100,'mae':-10} for j in range(5)])
    run=run_single_product_fleet(rb,df,FleetConfig('lucid_flex',50000,'FORCE_100_CAPTURE',fixed_accounts=1,max_trades_per_account_per_session=1,commission_per_contract_round_trip=0,payout_request_mode='NONE'))
    assert run.summary['signals_routed']==5
    assert run.summary['signals_unrouted_capacity']==0
    assert run.summary['signal_capture_percent']==100
    assert run.summary['accounts_provisioned']==5
    assert run.household_sessions.iloc[0]['accounts_traded']==5


def test_five_lucid_accounts_each_receive_one_trade_per_day_and_each_payout():
    rb=load_rulebook()
    rows=[]
    for day in range(1,6):
        for j in range(5):
            rows.append({'day':day,'minute':j,'pnl':500,'mae':-50})
    run=run_single_product_fleet(rb,_ledger(rows),FleetConfig('lucid_flex',50000,'FIXED_FLEET',fixed_accounts=5,max_trades_per_account_per_session=1,commission_per_contract_round_trip=0,payout_request_mode='MAX_ALLOWED'))
    assert run.summary['signals_routed']==25
    assert run.summary['completed_payouts']==5
    assert abs(run.summary['payout_cash_received']-5625)<1e-9
    assert len(run.payouts)==5
    assert set(run.accounts['payout_count'])=={1}


def test_force_capture_replaces_capacity_after_account_failure():
    rb=load_rulebook()
    # First session account fails; second session still must route all 2 signals by provisioning.
    df=_ledger([
        {'day':1,'minute':1,'pnl':-3000,'mae':-3000},
        {'day':2,'minute':1,'pnl':100,'mae':-10},
        {'day':2,'minute':2,'pnl':100,'mae':-10},
    ])
    run=run_single_product_fleet(rb,df,FleetConfig('lucid_flex',50000,'FORCE_100_CAPTURE',fixed_accounts=1,max_trades_per_account_per_session=1,commission_per_contract_round_trip=0,payout_request_mode='NONE'))
    assert run.summary['signals_routed']==3
    assert run.summary['signals_unrouted_capacity']==0
    assert run.summary['failed_accounts']==1
    assert run.summary['accounts_provisioned']>=3


def test_fleet_does_not_claim_final_business_net_before_cost_engine():
    rb=load_rulebook()
    df=_ledger([{'day':1,'pnl':100,'mae':-10}])
    run=run_single_product_fleet(rb,df,FleetConfig('lucid_flex',50000,'FIXED_FLEET',fixed_accounts=1,commission_per_contract_round_trip=0,payout_request_mode='NONE'))
    assert run.summary['account_acquisition_costs'] is None
    assert run.summary['realized_household_net_after_all_costs'] is None
    assert 'NOT_YET_MODELED' in run.summary['economics_status']


def test_manual_effective_cost_charges_every_provisioned_account_and_calculates_net():
    rb=load_rulebook()
    df=_ledger([{'day':1,'minute':j,'pnl':100,'mae':-10} for j in range(3)])
    run=run_single_product_fleet(
        rb, df,
        FleetConfig('lucid_flex',50000,'FORCE_100_CAPTURE',fixed_accounts=1,
                    max_trades_per_account_per_session=1,commission_per_contract_round_trip=0,
                    payout_request_mode='NONE',acquisition_cost_mode='MANUAL_EFFECTIVE_FUNDED_COST',
                    effective_cost_per_funded_account=125)
    )
    assert run.summary['accounts_provisioned']==3
    assert abs(run.summary['account_and_household_external_costs']-375)<1e-9
    assert run.summary['cost_basis_known'] is True
    assert abs(run.summary['realized_household_net_cash_after_modeled_external_costs']+375)<1e-9
    assert abs(run.accounts['acquisition_cost_basis'].sum()-375)<1e-9


def test_maintain_n_replaces_failed_account_and_charges_replacement():
    rb=load_rulebook()
    df=_ledger([
        {'day':1,'minute':1,'pnl':-3000,'mae':-3000},
        {'day':2,'minute':1,'pnl':100,'mae':-10},
        {'day':2,'minute':2,'pnl':100,'mae':-10},
    ])
    run=run_single_product_fleet(
        rb, df,
        FleetConfig('lucid_flex',50000,'MAINTAIN_FIXED_ACTIVE',fixed_accounts=2,
                    max_trades_per_account_per_session=1,commission_per_contract_round_trip=0,
                    payout_request_mode='NONE',acquisition_cost_mode='MANUAL_EFFECTIVE_FUNDED_COST',
                    effective_cost_per_funded_account=100)
    )
    assert run.summary['signals_routed']==3
    assert run.summary['signals_unrouted_capacity']==0
    assert run.summary['failed_accounts']==1
    assert run.summary['accounts_provisioned']==3
    assert abs(run.summary['account_and_household_external_costs']-300)<1e-9
    assert run.summary['active_accounts_at_end']==2


def test_active_account_reports_accrued_but_blocked_payout_capacity():
    rb=load_rulebook()
    # LucidFlex has enough profit for payout capacity but not five qualifying days.
    df=_ledger([{'day':1,'pnl':1200,'mae':-10}])
    run=run_single_product_fleet(rb,df,FleetConfig('lucid_flex',50000,'FIXED_FLEET',fixed_accounts=1,
        commission_per_contract_round_trip=0,payout_request_mode='MAX_ALLOWED'))
    row=run.accounts.iloc[0]
    assert row['claimable_now_gross']==0
    assert row['accrued_but_blocked_gross_capacity']>0
    assert 'MORE_QUALIFYING_DAY' in row['payout_blockers']
    assert run.summary['accrued_but_not_claimable_gross_capacity_at_end']>0


def test_strict_and_review_mode_are_explicit_in_summary():
    rb=load_rulebook()
    df=_ledger([{'day':1,'pnl':100,'mae':-10}])
    run=run_single_product_fleet(rb,df,FleetConfig('lucid_flex',50000,'FIXED_FLEET',fixed_accounts=1,
        commission_per_contract_round_trip=0,payout_request_mode='NONE',include_review_rows=False))
    assert run.summary['data_mode']=='STRICT_CERTIFICATION'


def test_failed_account_positive_residual_is_recorded_as_confirmed_forfeiture():
    rb=load_rulebook()
    # Build account above start, then fail after the floor has locked above start.
    df=_ledger([
        {'day':1,'pnl':2200,'mae':-10},
        {'day':2,'pnl':-3000,'mae':-3000},
    ])
    run=run_single_product_fleet(rb,df,FleetConfig('lucid_flex',50000,'FIXED_FLEET',fixed_accounts=1,
        commission_per_contract_round_trip=0,payout_request_mode='NONE'))
    assert run.summary['failed_accounts']==1
    assert run.summary['confirmed_forfeited_residual_sim_profit']>=0
    if run.summary['confirmed_forfeited_residual_sim_profit']>0:
        assert (run.forfeitures['status']=='CONFIRMED').any()
