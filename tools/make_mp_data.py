#!/usr/bin/env python3
"""Build the two Parquet files the miniproject downloads, from the Rieth et al. data.

    uv run --with pyreadr --with polars --with pyarrow python tools/make_mp_data.py OUTDIR

WHY THIS EXISTS. The Rieth faulty training file is 494 MB as RData and cannot be
read in pieces: loading it with pyreadr peaked at 8.9 GB of resident memory on
2026-09-16 (5,000,000 rows x 55 columns, 2.16 GB as a dataframe). That crashes an
8 GB laptop. The miniproject needs only runs 1 to 20 of each fault, which is
200,000 rows and about 20 MB as Parquet, so we build that subset once and host it.
The data are CC0 (Rieth, Amsel, Tran and Cook 2017,
https://doi.org/10.7910/DVN/6C3JR1), so redistributing a subset is allowed, and the
spec still cites the original.

OUTPUTS, written to OUTDIR (not to the repository; CLAUDE.md forbids committing
datasets):

    tep_fault_free_training.parquet        all 500 fault-free training runs
    tep_faulty_training_runs01-20.parquet  faults 1-20, simulation runs 1-20
    SHA256SUMS                             checksums, also committed as
                                           course/miniproject-data.sha256

Deploy by copying OUTDIR to the directory served by stream/deploy/nginx-data.conf.
Both files are sorted by (faultNumber, simulationRun, sample), and the three key
columns are Int64, so a rebuild with the same Polars version is byte-identical.
"""
from __future__ import annotations

import hashlib
import shutil
import sys
import urllib.request
from pathlib import Path

import polars as pl

FILES = {
    "fault_free_training": ("https://dataverse.harvard.edu/api/access/datafile/3031241",
                            "TEP_FaultFree_Training.RData",
                            "tep_fault_free_training.parquet", None),
    "faulty_training": ("https://dataverse.harvard.edu/api/access/datafile/3031242",
                        "TEP_Faulty_Training.RData",
                        "tep_faulty_training_runs01-20.parquet", 20),
}
KEYS = ["faultNumber", "simulationRun", "sample"]


def fetch(url: str, dest: Path) -> None:
    if dest.exists():
        return
    print(f"fetching {url} -> {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out = Path(sys.argv[1])
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    import pyreadr

    sums = []
    for obj, (url, rname, pname, max_run) in FILES.items():
        fetch(url, raw / rname)
        pdf = pyreadr.read_r(str(raw / rname))[obj]
        frame = pl.from_pandas(pdf.reset_index(drop=True))
        del pdf
        frame = frame.with_columns([pl.col(k).cast(pl.Int64) for k in KEYS])
        if max_run is not None:
            frame = frame.filter(pl.col("simulationRun") <= max_run)
        frame = frame.sort(KEYS)
        frame.write_parquet(out / pname, statistics=False)
        digest = hashlib.sha256((out / pname).read_bytes()).hexdigest()
        sums.append(f"{digest}  {pname}")
        print(f"{pname}: {frame.height:,} rows, {(out / pname).stat().st_size / 1e6:.1f} MB")
        del frame
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    print((out / "SHA256SUMS").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
