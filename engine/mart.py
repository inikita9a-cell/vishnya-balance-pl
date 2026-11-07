"""MartAPI. Фильтры (И). Индексы при загрузке: значение -> np.array(row_idx)."""
from __future__ import annotations
import pathlib, pandas as pd, numpy as np


class Mart:
    def __init__(self, run_dir: str):
        p = pathlib.Path(run_dir) / "comparison.parquet"
        self.df = pd.read_parquet(p) if p.exists() else pd.DataFrame()
        self._idx = {}
        for col in ("PATH", "CHANGE_TYPE", "DIFF_FLAG", "APP_ID"):
            if col in self.df.columns:
                self._idx[col] = {v: np.where(self.df[col].values == v)[0] for v in self.df[col].unique()}

    def _mask(self, **f):
        if not f: return np.arange(len(self.df))
        masks = []
        for k, v in f.items():
            if k not in self.df.columns: continue
            if isinstance(v, (list, tuple, set)):
                masks.append(self.df[k].isin(list(v)).values)
            else:
                masks.append((self.df[k].values == v))
        m = masks[0]
        for x in masks[1:]: m = m & x
        return m

    def rows(self, **f):
        m = self._mask(**f)
        return self.df.loc[m].to_dict(orient="records")

    def count(self, **f) -> int:
        return int(len(self.df.loc[self._mask(**f)]))

    def app_ids(self, **f) -> list[str]:
        m = self._mask(**f)
        return sorted(self.df.loc[m, "APP_ID"].dropna().unique().tolist())

    def segments(self):
        p = pathlib.Path(self.df.attrs.get("run_dir", "")) / "segments.parquet"
        # ToDO: run_dir пробрасывать; fallback:
        return []

    def total_apps(self) -> int:
        return int(self.df["APP_ID"].nunique()) if "APP_ID" in self.df else 0
