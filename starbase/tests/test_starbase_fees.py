from starbase_fees import resolve_fee, instrument_spec, infer_instrument_from_profile


def test_instrument_specs_core_equity_futures():
    assert instrument_spec('NQ')['point_value'] == 20.0
    assert instrument_spec('MNQ')['point_value'] == 2.0
    assert instrument_spec('ES')['point_value'] == 50.0
    assert instrument_spec('MES')['point_value'] == 5.0


def test_profile_inference_prefers_micro_tokens():
    assert infer_instrument_from_profile('3MNQ_safe') == 'MNQ'
    assert infer_instrument_from_profile('2MES') == 'MES'
    assert infer_instrument_from_profile('Sydney_1NQ') == 'NQ'


def test_lucid_and_tradeify_nq_are_different():
    lucid = resolve_fee(firm_id='lucid', product_id='lucid_flex', instrument='NQ')
    tradeify = resolve_fee(firm_id='tradeify', product_id='tradeify_select_flex', instrument='NQ')
    assert lucid.round_trip_per_contract == 3.50
    assert tradeify.round_trip_per_contract == 5.76
    assert lucid.status == 'VERIFIED_OFFICIAL'
    assert tradeify.status == 'VERIFIED_OFFICIAL'


def test_apex_platform_fee_difference_is_explicit():
    rithmic = resolve_fee(firm_id='apex', product_id='apex_eod', instrument='NQ', platform_variant='RITHMIC')
    tradovate = resolve_fee(firm_id='apex', product_id='apex_eod', instrument='NQ', platform_variant='TRADOVATE')
    assert rithmic.round_trip_per_contract == 3.98
    assert tradovate.round_trip_per_contract == 3.10


def test_unresolved_fee_never_borrows_another_rate():
    q = resolve_fee(firm_id='fundednext', product_id='fundednext_flex', instrument='MES')
    assert q.round_trip_per_contract is None
    assert q.resolution == 'UNRESOLVED'


def test_manual_override_is_labeled():
    q = resolve_fee(firm_id='fundednext', product_id='fundednext_flex', instrument='MES', manual_override=1.91)
    assert q.round_trip_per_contract == 1.91
    assert q.status == 'USER_VERIFIED_OVERRIDE'
