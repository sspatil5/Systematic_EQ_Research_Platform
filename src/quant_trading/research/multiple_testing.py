"""Family-wise and false-discovery-rate p-value adjustments."""

from __future__ import annotations

import numpy as np
import pandas as pd


def adjust_pvalues(pvalues: pd.Series) -> pd.DataFrame:
    clean = pvalues.dropna().astype(float)
    count = len(clean)
    output = pd.DataFrame(index=pvalues.index, columns=["raw_p_value", "bonferroni_p_value", "fdr_q_value"], dtype=float)
    output["raw_p_value"] = pvalues
    if count == 0:
        return output
    output.loc[clean.index, "bonferroni_p_value"] = np.minimum(clean * count, 1.0)
    ordered = clean.sort_values()
    ranks = np.arange(1, count + 1)
    raw_q = ordered.to_numpy() * count / ranks
    monotone_q = np.minimum.accumulate(raw_q[::-1])[::-1]
    output.loc[ordered.index, "fdr_q_value"] = np.minimum(monotone_q, 1.0)
    return output

