from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "public"


def main() -> None:
    fixed_effects = pd.read_csv(DATA / "fixed_effects_results.csv")
    characteristic = pd.read_csv(DATA / "characteristic_match_summary.csv")
    title = pd.read_csv(DATA / "title_match_summary.csv")
    strict = pd.read_csv(DATA / "same_work_channel_effect.csv")
    segmentation = pd.read_csv(DATA / "channel_segmentation_tests.csv")
    synthetic = pd.read_csv(DATA / "synthetic_validation_data.csv")
    synthetic["log_price"] = np.log(synthetic["real_price_2025"])
    channel = pd.get_dummies(synthetic["channel"], drop_first=True, dtype=float)
    years = pd.get_dummies(synthetic["year"].astype(str), drop_first=True, dtype=float)
    design = sm.add_constant(pd.concat([channel, years], axis=1))
    demonstration = sm.OLS(synthetic["log_price"], design).fit()
    output = {
        "archived_public_results": {
            "fixed_effects_rows": int(len(fixed_effects)),
            "characteristic_match_rows": int(len(characteristic)),
            "title_match_rows": int(len(title)),
            "strict_pairs": int(strict.loc[0, "matched_pairs"]),
            "joint_premium_test_rows": int(len(segmentation)),
        },
        "synthetic_pipeline_check": {
            "observations": int(demonstration.nobs),
            "r_squared": float(demonstration.rsquared),
            "coefficients": {name: float(value) for name, value in demonstration.params.items()},
        },
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
