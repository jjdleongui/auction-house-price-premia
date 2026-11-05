import json
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "public"


def test_released_metrics_match_archived_results():
    diagnostics = json.loads((DATA / "diagnostics.json").read_text())
    assert diagnostics["observations"] == 12364
    assert diagnostics["characteristic_matched_pairs"] == 292
    assert diagnostics["pooled_spanish_vs_catawiki"]["percent_difference"] == pytest.approx(96.9147410177395)


def test_public_data_have_declared_structure():
    data = pd.read_csv(DATA / "catawiki_classified_analysis_data.csv")
    dictionary = pd.read_csv(DATA / "data_dictionary.csv")
    assert len(data) > 10000
    assert set(data.columns).issubset(set(dictionary["variable"]))
    assert not data.columns.str.contains("description|image|bidder", case=False).any()


def test_no_restricted_directory_is_present():
    assert not (ROOT / "data" / "restricted").exists()
    assert not (ROOT / "paper").exists()
    assert not list(ROOT.rglob("*.docx"))
