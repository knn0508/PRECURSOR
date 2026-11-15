"""Export the B0/E3 input scaler next to artifacts/model.pt and verify it reproduces artifacts/forecast.tif.

model.pt holds only network weights (state_dict). The Scaler (train-rows-only mean/std) is deterministic
given the processed stack, so it is rebuilt here with the exact notebook config (via v2common.load) and
saved to artifacts/scaler.npz. Verification: reload model.pt, issue the live forecast at the last
acquisition, and compare with the committed forecast.tif. Nothing is retrained.
"""
import json
import sys

import numpy as np
import rasterio
import torch

from precursor import v2common as V, models as M, train as TT
from precursor.dataset import build_samples

ART = V.ROOT / "artifacts"
D = V.load()
ss, sc, st = D["ss"], D["sc"], D["st"]
fi_norain = [i for i, n in enumerate(ss.feat_names) if not n.startswith("rain")]   # E3 = no rain

np.savez(ART / "scaler.npz", xm=sc.xm, xs=sc.xs, sm=sc.sm, sd=sc.sd, ym=np.float64(sc.ym), ys=np.float64(sc.ys),
         feat_names=np.array(ss.feat_names), static_names=np.array(ss.static_names), feat_idx=np.array(fi_norain))

# --- verify against the committed forecast ---
dev = "cuda" if torch.cuda.is_available() else "cpu"
sd = torch.load(ART / "model.pt", map_location=dev)
model = M.build("lstm_tcn", ss.X.shape[1], len(fi_norain), ss.S.shape[1], False, 64, 0.1).to(dev)
model.load_state_dict(sd); model.eval()
times = D["times"]
from precursor.ancillary import dem_on_grid
terr = dem_on_grid(st.x.values, st.y.values, st.attrs["crs_wkt"], V.AOI_PB)
static = np.stack([np.nan_to_num(terr[k]) for k in V.STATIC_NAMES]).astype(np.float32)
import pandas as pd
rain = pd.read_csv(V.ROOT / "data/processed/imerg_daily_aoi.csv", index_col=0, parse_dates=True).iloc[:, 0]
L = build_samples(st.cum_mm.values, st.valid.values, st.coherence.values, times, static, V.STATIC_NAMES, rain=rain,
                  window=6, horizon=12.0, min_valid_steps=4, pixel_stride=1, issue_indices=[len(times) - 1])
q, _, _ = TT.predict(model, L, sc, fi_norain, dev)
H, W = st.cum_mm.shape[1:]
g = np.full((H, W), np.nan, np.float32); g[L.pix[:, 0], L.pix[:, 1]] = q[:, 1]
if not (st.y[0] > st.y[-1]):
    g = g[::-1]
with rasterio.open(ART / "forecast.tif") as f:
    ref = f.read(2)
both = np.isfinite(g) & np.isfinite(ref)
res = dict(pixels_compared=int(both.sum()), nan_pattern_equal=bool((np.isfinite(g) == np.isfinite(ref)).all()),
           max_abs_diff_mm=float(np.abs(g[both] - ref[both]).max()), issue_time=str(L.issue_time.max())[:10])
print(json.dumps(res, indent=1))
json.dump(res, open(ART / "scaler_verification.json", "w"), indent=1)
sys.exit(0 if res["max_abs_diff_mm"] < 1e-3 and res["nan_pattern_equal"] else 1)
