from __future__ import annotations

from pathlib import Path

import pandas as pd


def main() -> None:
    output_dir = Path(__file__).resolve().parent
    raw_path = output_dir / "step_only_test_defect_data.csv"
    bsl_path = output_dir / "step_only_test_bsl.csv"

    rows = []
    scan_start = pd.Timestamp("2026-07-01 08:00:00")

    # STEP10 intentionally appears in three stages with the same recipe/tool family.
    # Step-only aggregation should output one STEP10 worse-tool row per tool group,
    # not one row per Stage_ID + Step_ID.
    step10_stages = ["STG_A", "STG_B", "STG_C"]
    for stage_index, stage_id in enumerate(step10_stages):
        for wafer_no in range(1, 9):
            scan_time = scan_start + pd.Timedelta(hours=stage_index * 8 + wafer_no)
            rows.append(
                {
                    "LOT_ID": "LOT_STEP10_{:02d}".format(stage_index + 1),
                    "WAFER_NO": wafer_no,
                    "SCAN_TIME": scan_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "STAGE_ID": stage_id,
                    "STEP_ID": "STEP10",
                    "EQUIPMENT_ID": "KP1001",
                    "CHAMBER_ID": "",
                    "DEFECT TYPE1": 12 + (wafer_no % 3),
                    "DEFECT TYPE2": 2 + (wafer_no % 2),
                }
            )
            rows.append(
                {
                    "LOT_ID": "LOT_STEP10_{:02d}".format(stage_index + 1),
                    "WAFER_NO": wafer_no,
                    "SCAN_TIME": scan_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "STAGE_ID": stage_id,
                    "STEP_ID": "STEP10",
                    "EQUIPMENT_ID": "KE4001",
                    "CHAMBER_ID": "A",
                    "DEFECT TYPE1": 3 + (wafer_no % 2),
                    "DEFECT TYPE2": 11 + (wafer_no % 3),
                }
            )

    # STEP20 is included as a control step. It should remain a separate Step_ID group.
    for wafer_no in range(1, 9):
        scan_time = scan_start + pd.Timedelta(days=2, hours=wafer_no)
        rows.append(
            {
                "LOT_ID": "LOT_STEP20",
                "WAFER_NO": wafer_no,
                "SCAN_TIME": scan_time.strftime("%Y-%m-%d %H:%M:%S"),
                "STAGE_ID": "STG_D",
                "STEP_ID": "STEP20",
                "EQUIPMENT_ID": "KT3001",
                "CHAMBER_ID": "B",
                "DEFECT TYPE1": 8 + (wafer_no % 2),
                "DEFECT TYPE2": 2,
            }
        )

    pd.DataFrame(rows).to_csv(raw_path, index=False)
    pd.DataFrame(
        [
            {"Defect type": "DEFECT TYPE1", "BSL count": 5},
            {"Defect type": "DEFECT TYPE2", "BSL count": 5},
        ]
    ).to_csv(bsl_path, index=False)

    print("Wrote {}".format(raw_path))
    print("Wrote {}".format(bsl_path))
    print("Expected step-only highlights:")
    print("- DEFECT TYPE1 / ALL_STAGES / STEP10 / KP1001")
    print("- DEFECT TYPE2 / ALL_STAGES / STEP10 / KE4001 chamber A")
    print("- DEFECT TYPE1 / ALL_STAGES / STEP20 / KT3001 chamber B")


if __name__ == "__main__":
    main()
