from starbase_economics import AcquisitionCostPolicy, load_cost_reference, cost_reference_for_product


def test_manual_cost_policy_is_known_and_charges_account():
    p=AcquisitionCostPolicy(mode='MANUAL_EFFECTIVE_FUNDED_COST', effective_cost_per_funded_account=123, refund_or_bonus_per_account=5)
    p.validate()
    assert p.cost_basis_known is True
    assert p.provision_external_cost()==123
    assert p.provision_refund_or_bonus()==5


def test_existing_inventory_cost_is_unknown_not_free_business_cost():
    p=AcquisitionCostPolicy()
    p.validate()
    assert p.cost_basis_known is False
    assert p.provision_external_cost()==0


def test_tradeify_current_reference_has_50k_price_and_reset():
    c=load_cost_reference()
    r=cost_reference_for_product(c,'tradeify_select_flex',50000)
    assert r['evaluation_purchase_price']==165.0
    assert r['evaluation_reset_fee']==95.0
    assert r['activation_fee']==0.0


def test_dynamic_checkout_products_require_confirmation():
    c=load_cost_reference()
    r=cost_reference_for_product(c,'lucid_flex',50000)
    assert 'USER_CONFIRMATION_REQUIRED' in r['pricing_status']
