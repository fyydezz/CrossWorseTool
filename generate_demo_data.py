from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    out_dir = Path(__file__).resolve().parent
    rng = np.random.default_rng(42)
    rows = []
    tools = ["KP1001", "KD2001", "KW3001", "KE4001", "KT5001"]
    chambers = ["A", "B", "C", "D"]
    stages = [("STG01", "STEP10"), ("STG01", "STEP20"), ("STG02", "STEP10")]

    for lot_idx in range(1, 22):
        lot = "LOT{:03d}".format(lot_idx)
        for wafer in range(1, 26):
            stage, step = stages[(lot_idx + wafer) % len(stages)]
            equip = tools[(lot_idx + wafer) % len(tools)]
            chamber = chambers[(lot_idx * wafer) % len(chambers)]
            base_a = 3
            base_b = 5
            base_c = 2
            if stage == "STG01" and step == "STEP10" and equip == "KE4001" and chamber == "B":
                base_a = 11
            if stage == "STG02" and step == "STEP10" and equip == "KP1001":
                base_b = 14
            rows.append(
                {
                    "Lot_ID": lot,
                    "Wafer_NO": wafer,
                    "Scan_Time": pd.Timestamp("2026-06-01") + pd.Timedelta(hours=len(rows) * 3),
                    "Defect Type1": int(rng.poisson(base_a)),
                    "Defect Type2": int(rng.poisson(base_b)),
                    "Defect Type3": int(rng.poisson(base_c)),
                    "Stage_ID": stage,
                    "Step_ID": step,
                    "Equipment_ID": equip,
                    "Chamber_ID": chamber,
                }
            )

    df = pd.DataFrame(rows)
    if len(df) > 10:
        df.loc[3, "Defect Type1"] = 200
        df.loc[10, "Defect Type2"] = 240
    df.to_csv(out_dir / "demo_defect_data.csv", index=False)
    df.to_excel(out_dir / "demo_defect_data.xlsx", index=False)

    bsl = pd.DataFrame(
        [
            {"Defect type": "Defect Type1", "BSL count": 6},
            {"Defect type": "Defect Type2", "BSL count": 7},
            {"Defect type": "Defect Type3", "BSL count": 5},
        ]
    )
    bsl.to_csv(out_dir / "demo_bsl.csv", index=False)
    print("Generated demo_defect_data.csv, demo_defect_data.xlsx, and demo_bsl.csv")


if __name__ == "__main__":
    main()
