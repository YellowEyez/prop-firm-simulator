"""Reusable Strategy Dataset Library for Project StarBase.

This module intentionally uses a runtime filesystem store that works locally and on
Streamlit Community Cloud while the app instance remains alive. Community Cloud
runtime storage is not guaranteed to survive redeploys/restarts, so every library can
be exported as a portable StarBase Dataset Vault ZIP and restored with one upload.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from starbase_paths import APP_DIR
from tradingview_audit import AuditPolicy, audit_tradingview_files

LIBRARY_DIR = APP_DIR / ".starbase_runtime_datasets"
MANIFEST_NAME = "dataset_manifest.json"
VAULT_SCHEMA_VERSION = "STARBASE_DATASET_VAULT_V1"


class NamedBytesIO(io.BytesIO):
    def __init__(self, data: bytes, name: str):
        super().__init__(data)
        self.name = name


@dataclass(frozen=True)
class IntervalInference:
    label: str
    seconds: Optional[float]
    confidence: float
    method: str
    sample_count: int
    ambiguous: bool = False


def _safe_slug(value: str, fallback: str = "dataset") -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._-")
    return text or fallback


def _source_bytes(source) -> bytes:
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    if isinstance(source, bytes):
        return source
    if hasattr(source, "getvalue"):
        return bytes(source.getvalue())
    if hasattr(source, "read"):
        pos = None
        try:
            pos = source.tell()
        except Exception:
            pass
        data = source.read()
        if pos is not None:
            try:
                source.seek(pos)
            except Exception:
                pass
        return bytes(data)
    raise TypeError(f"Unsupported source type: {type(source)!r}")


def _source_name(source, index: int) -> str:
    name = getattr(source, "name", None)
    if name:
        return Path(str(name)).name
    if isinstance(source, (str, Path)):
        return Path(source).name
    return f"source_{index:02d}.csv"


def _canonical_interval_label(seconds: float) -> str:
    if seconds < 60:
        s = int(round(seconds)) if abs(seconds - round(seconds)) < 0.05 else round(seconds, 2)
        return f"{s}s"
    if seconds < 3600:
        minutes = seconds / 60.0
        m = int(round(minutes)) if abs(minutes - round(minutes)) < 0.02 else round(minutes, 2)
        return f"{m}m"
    hours = seconds / 3600.0
    h = int(round(hours)) if abs(hours - round(hours)) < 0.02 else round(hours, 2)
    return f"{h}h"


def infer_chart_interval(ledger: pd.DataFrame) -> IntervalInference:
    """Infer likely TradingView chart interval from trade duration bars.

    TradingView exports include both elapsed entry->exit time and Duration (bars).
    Their ratio is a much stronger signal than filename text or timestamp alignment.
    It is still an inference because sessions/gaps and TradingView counting semantics
    can make some trades noisy. The UI therefore exposes the detected interval and a
    manual override instead of pretending this is metadata embedded in the CSV.
    """
    if ledger is None or ledger.empty or "seconds_per_bar" not in ledger.columns:
        return IntervalInference("Unknown", None, 0.0, "insufficient_data", 0, True)

    vals = pd.to_numeric(ledger["seconds_per_bar"], errors="coerce")
    vals = vals[np.isfinite(vals) & (vals > 0.25) & (vals <= 86400)]
    if vals.empty:
        return IntervalInference("Unknown", None, 0.0, "insufficient_data", 0, True)

    canonical = np.array([1, 2, 3, 5, 10, 15, 20, 30, 45, 60, 120, 180, 300, 600, 900, 1800, 3600, 7200, 14400, 86400], dtype=float)
    arr = vals.to_numpy(dtype=float)
    scores = []
    for candidate in canonical:
        tolerance = max(0.40, candidate * 0.075)
        close = np.abs(arr - candidate) <= tolerance
        # Favor exact-ish ratios while tolerating session/gap outliers.
        scores.append((float(close.mean()), int(close.sum()), candidate))
    scores.sort(reverse=True)
    score, count, best = scores[0]
    second_score = scores[1][0] if len(scores) > 1 else 0.0

    median = float(np.median(arr))
    # If the canonical hit rate is weak, report median as an uncertain estimate.
    if score < 0.45:
        return IntervalInference(_canonical_interval_label(median), median, score, "duration_bars_median_low_confidence", len(arr), True)

    ambiguous = score < 0.70 or (score - second_score) < 0.10
    method = "elapsed_seconds_divided_by_duration_bars"
    return IntervalInference(_canonical_interval_label(best), float(best), score, method, len(arr), ambiguous)


def infer_year_range(ledger: pd.DataFrame) -> tuple[Optional[int], Optional[int]]:
    if ledger is None or ledger.empty:
        return None, None
    ts = pd.to_datetime(ledger.get("entry_time_et"), errors="coerce", utc=True)
    ts = ts[ts.notna()]
    if ts.empty:
        return None, None
    return int(ts.dt.year.min()), int(ts.dt.year.max())


def suggested_dataset_name(strategy_id: str, interval_label: str, start_year: Optional[int], end_year: Optional[int]) -> str:
    base = re.sub(r"(?:[_-]?\d+)?$", "", str(strategy_id or "Strategy").strip()).strip("_- ") or "Strategy"
    pieces = [base]
    if interval_label and interval_label != "Unknown":
        pieces.append(interval_label)
    if start_year:
        pieces.append(str(start_year) if not end_year or end_year == start_year else f"{start_year}-{end_year}")
    return "_".join(pieces)


def library_dir() -> Path:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    return LIBRARY_DIR


def _dataset_dir(dataset_id: str) -> Path:
    return library_dir() / _safe_slug(dataset_id)


def list_datasets() -> List[dict]:
    out: List[dict] = []
    root = library_dir()
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        manifest_path = path / MANIFEST_NAME
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["_path"] = str(path)
            out.append(manifest)
        except Exception:
            continue
    out.sort(key=lambda x: x.get("created_at_utc", ""), reverse=True)
    return out


def get_dataset(dataset_id: str) -> Optional[dict]:
    p = _dataset_dir(dataset_id) / MANIFEST_NAME
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_dataset(
    sources: Sequence[object],
    *,
    display_name: str,
    strategy_id: str,
    profile_id: str,
    notes: str = "",
    point_value_per_contract: float = 20.0,
    chart_interval_override: Optional[str] = None,
) -> dict:
    if not sources:
        raise ValueError("At least one TradingView CSV source is required.")

    audit = audit_tradingview_files(
        sources,
        strategy_id=strategy_id,
        profile_id=profile_id,
        policy=AuditPolicy(point_value_per_contract=float(point_value_per_contract)),
    )
    interval = infer_chart_interval(audit.ledger)
    y0, y1 = infer_year_range(audit.ledger)
    chart_interval = (chart_interval_override or "").strip() or interval.label

    file_records = []
    hasher = hashlib.sha256()
    source_payloads = []
    for i, src in enumerate(sources, start=1):
        data = _source_bytes(src)
        name = _source_name(src, i)
        sha = hashlib.sha256(data).hexdigest()
        hasher.update(sha.encode("ascii"))
        source_payloads.append((name, data))
        file_records.append({"name": name, "sha256": sha, "bytes": len(data)})

    identity_payload = json.dumps(
        {
            "display_name": display_name,
            "strategy_id": strategy_id,
            "profile_id": profile_id,
            "source_hashes": [r["sha256"] for r in file_records],
        },
        sort_keys=True,
    ).encode("utf-8")
    dataset_id = f"ds_{hashlib.sha256(identity_payload).hexdigest()[:16]}"
    target = _dataset_dir(dataset_id)
    if target.exists():
        shutil.rmtree(target)
    (target / "raw").mkdir(parents=True, exist_ok=True)

    saved_files = []
    used_names = set()
    for idx, (name, data) in enumerate(source_payloads, start=1):
        safe = _safe_slug(name, f"source_{idx:02d}.csv")
        if not safe.lower().endswith(".csv"):
            safe += ".csv"
        original = safe
        n = 2
        while safe in used_names:
            stem, suffix = Path(original).stem, Path(original).suffix
            safe = f"{stem}_{n}{suffix}"
            n += 1
        used_names.add(safe)
        (target / "raw" / safe).write_bytes(data)
        saved_files.append(safe)

    manifest = {
        "schema_version": VAULT_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "display_name": display_name.strip() or suggested_dataset_name(strategy_id, chart_interval, y0, y1),
        "strategy_id": strategy_id.strip() or "Strategy_01",
        "profile_id": profile_id.strip() or "1NQ",
        "notes": notes,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "chart_interval": chart_interval,
        "chart_interval_detected": interval.label,
        "chart_interval_detection_confidence": round(float(interval.confidence), 6),
        "chart_interval_detection_method": interval.method,
        "chart_interval_detection_samples": int(interval.sample_count),
        "chart_interval_detection_ambiguous": bool(interval.ambiguous),
        "start_year": y0,
        "end_year": y1,
        "first_entry_et": audit.summary.get("first_entry_et"),
        "last_exit_et": audit.summary.get("last_exit_et"),
        "point_value_per_contract": float(point_value_per_contract),
        "files": file_records,
        "saved_raw_files": saved_files,
        "batch_sha256": hasher.hexdigest(),
        "audit_summary": audit.summary,
    }
    (target / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return manifest


def load_dataset_sources(dataset_id: str) -> List[NamedBytesIO]:
    manifest = get_dataset(dataset_id)
    if not manifest:
        raise FileNotFoundError(f"Dataset not found: {dataset_id}")
    root = _dataset_dir(dataset_id) / "raw"
    out = []
    for name in manifest.get("saved_raw_files", []):
        p = root / name
        if not p.exists():
            raise FileNotFoundError(f"Saved dataset source is missing: {p}")
        out.append(NamedBytesIO(p.read_bytes(), name))
    return out


def delete_dataset(dataset_id: str) -> bool:
    path = _dataset_dir(dataset_id)
    if not path.exists():
        return False
    shutil.rmtree(path)
    return True


def export_dataset_vault() -> bytes:
    payload = io.BytesIO()
    root = library_dir()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as zf:
        vault_manifest = {
            "schema_version": VAULT_SCHEMA_VERSION,
            "exported_at_utc": datetime.now(timezone.utc).isoformat(),
            "datasets": [d.get("dataset_id") for d in list_datasets()],
        }
        zf.writestr("VAULT_MANIFEST.json", json.dumps(vault_manifest, indent=2))
        for d in list_datasets():
            dataset_id = d["dataset_id"]
            base = _dataset_dir(dataset_id)
            for path in base.rglob("*"):
                if path.is_file():
                    rel = path.relative_to(root)
                    zf.write(path, arcname=str(Path("datasets") / rel))
    return payload.getvalue()


def import_dataset_vault(blob: bytes, *, replace_existing: bool = False) -> dict:
    if not blob:
        raise ValueError("Vault ZIP is empty.")
    root = library_dir()
    imported, skipped = [], []
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        names = set(zf.namelist())
        if "VAULT_MANIFEST.json" not in names:
            raise ValueError("Not a StarBase Dataset Vault ZIP: VAULT_MANIFEST.json is missing.")
        vault = json.loads(zf.read("VAULT_MANIFEST.json").decode("utf-8"))
        if vault.get("schema_version") != VAULT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported dataset vault schema: {vault.get('schema_version')}")
        for dataset_id in vault.get("datasets", []):
            prefix = f"datasets/{_safe_slug(dataset_id)}/"
            member_names = [n for n in names if n.startswith(prefix) and not n.endswith("/")]
            if not member_names:
                continue
            target = _dataset_dir(dataset_id)
            if target.exists() and not replace_existing:
                skipped.append(dataset_id)
                continue
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
            for member in member_names:
                rel = Path(member[len(prefix):])
                if any(part in {"..", ""} for part in rel.parts):
                    continue
                dest = target / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(member))
            if (target / MANIFEST_NAME).exists():
                imported.append(dataset_id)
    return {"imported": imported, "skipped": skipped, "total_library": len(list_datasets())}
