from starbase_workspaces import WORKSPACE_LABELS, workspace_key


def test_josh_fleet_workspace_routes_to_fleet_not_legacy():
    label = "Josh Fleet Economics + Fees (v5F)"
    assert label in WORKSPACE_LABELS
    assert workspace_key(label) == "fleet_economics"


def test_dataset_library_workspace_routes_correctly():
    label = "Strategy Dataset Library (v5F)"
    assert label in WORKSPACE_LABELS
    assert workspace_key(label) == "dataset_library"


def test_golden_workspace_routes_exactly():
    from starbase_workspaces import workspace_key
    assert workspace_key("Golden Verification Lab (v5F)") == "golden"


def test_live_state_workspace_routes_exactly():
    assert workspace_key("Live Account State Lab (v5G)") == "live_state"


def test_live_transition_workspace_routes_exactly():
    assert workspace_key("Live Transition Lab (v5H)") == "live_transition"


def test_live_payout_workspace_routes_exactly():
    assert workspace_key("Live Payout / Withdrawal Lab (v5I)") == "live_payout"
