from starbase_workspaces import WORKSPACE_LABELS, workspace_key


def test_josh_fleet_workspace_routes_to_fleet_not_legacy():
    label = "Josh Fleet Economics + Inventory (v5C)"
    assert label in WORKSPACE_LABELS
    assert workspace_key(label) == "fleet_economics"


def test_dataset_library_workspace_routes_correctly():
    label = "Strategy Dataset Library (v5C)"
    assert label in WORKSPACE_LABELS
    assert workspace_key(label) == "dataset_library"
