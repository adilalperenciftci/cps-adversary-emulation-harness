import argparse
import json
from pathlib import Path

import pandas as pd


def analyze(path: Path, window: int = 15, threshold: float = 3.5) -> pd.DataFrame:
    frame = pd.read_json(path, lines=True)
    frame = frame.sort_values("timestamp")
    frame["delta_t"] = frame["timestamp"].diff()
    frame["ewma_latency"] = frame["latency_ms"].ewm(span=window, adjust=False).mean()
    frame["baseline"] = frame["latency_ms"].rolling(window, min_periods=5).median()
    deviation = (frame["latency_ms"] - frame["baseline"]).abs()
    mad = deviation.rolling(window, min_periods=5).median()
    denom = (1.4826 * mad).where(mad > 0)
    frame["anomaly_score"] = (deviation / denom).fillna(0.0)
    frame["anomaly"] = frame["anomaly_score"] > threshold
    frame["flow"] = frame["src"].astype(str) + "->" + frame["dst"].astype(str)
    return frame


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--threshold", type=float, default=3.5)
    args = parser.parse_args()
    result = analyze(args.input, threshold=args.threshold)
    cols = ["timestamp", "flow", "latency_ms", "baseline", "anomaly_score"]
    for record in result.loc[result["anomaly"], cols].to_dict("records"):
        print(json.dumps(record, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
