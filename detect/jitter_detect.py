import argparse
import json
import math
from pathlib import Path

import pandas as pd

MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_RECORDS = 100_000


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _read_rows(path: Path) -> list[dict[str, object]]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("telemetry exceeds byte budget")
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line_number > MAX_RECORDS:
                raise ValueError("telemetry exceeds record budget")
            try:
                row = json.loads(line, parse_constant=_reject_constant)
                values = (float(row["timestamp"]), float(row["latency_ms"]))
                src, dst = row["src"], row["dst"]
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid telemetry at line {line_number}") from exc
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"non-finite telemetry at line {line_number}")
            if not isinstance(src, str) or not isinstance(dst, str):
                raise ValueError(f"invalid telemetry at line {line_number}")
            rows.append({
                "timestamp": values[0], "latency_ms": values[1],
                "src": src, "dst": dst,
            })
    return rows


def analyze(
    path: Path, window: int = 15, threshold: float = 3.5,
    minimum_shift_ms: float = 0.5,
) -> pd.DataFrame:
    frame = pd.DataFrame.from_records(_read_rows(path))
    frame = frame.sort_values("timestamp")
    frame["ewma_latency"] = frame["latency_ms"].ewm(span=window, adjust=False).mean()
    history = frame["latency_ms"].shift(1)
    frame["baseline"] = history.rolling(window, min_periods=5).median()
    deviation = (frame["latency_ms"] - frame["baseline"]).abs()
    mad = history.rolling(window, min_periods=5).apply(
        lambda values: (values - values.median()).abs().median(), raw=False
    )
    denom = 1.4826 * mad
    score = deviation / denom.where(denom > 0)
    frame["anomaly_score"] = score.where(
        denom > 0, deviation.where(deviation == 0, float("inf"))
    ).fillna(0.0)
    ewma_shift = (frame["ewma_latency"] - frame["baseline"]).abs()
    frame["anomaly"] = (
        (frame["anomaly_score"] > threshold)
        & (deviation >= minimum_shift_ms)
        & (ewma_shift >= minimum_shift_ms / 3.0)
    )
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
        print(json.dumps(record, separators=(",", ":"), default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
