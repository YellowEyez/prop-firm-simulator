"""Single source of truth for StarBase workspace labels and routing keys."""
from __future__ import annotations

WORKSPACES = [
    ("Strategy Dataset Library (v5D)", "dataset_library"),
    ("TradingView Import + Audit (v2)", "audit"),
    ("Prop-Firm Rulebook (v3)", "rulebook"),
    ("Research Integrity + Provenance (v3.5)", "integrity"),
    ("Single-Account State + Ledger (v4A)", "account_state"),
    ("Historical Single-Account Trader (v4B)", "historical_runner"),
    ("Lifecycle + Account Comparison (v4C)", "lifecycle"),
    ("Josh Fleet Economics + Fees (v5D)", "fleet_economics"),
    ("Legacy Simulator (reference only)", "legacy"),
]

WORKSPACE_LABELS = [label for label, _ in WORKSPACES]
_LABEL_TO_KEY = dict(WORKSPACES)


def workspace_key(label: str) -> str:
    """Return stable routing key for an exact displayed workspace label."""
    return _LABEL_TO_KEY.get(label, "legacy")
