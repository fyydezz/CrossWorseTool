from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from defect_worse_tool import (
    SPECIAL_STAGE_ID,
    add_grouping_columns,
    build_bsl_lookup,
    calculate_recent_trimmed_bsl,
    filter_by_recent_scan_time,
    filter_outliers_for_defect,
    handle_outliers_for_defect,
    OUTLIER_HANDLING_CAP,
    OUTLIER_HANDLING_FILTER,
    parse_special_process_rules,
    read_table,
    summarize_one_defect,
)
from defect_worse_ui import (
    CHART_GROUP_MODE_CHAMBER,
    CHART_GROUP_MODE_EQUIPMENT,
    DefectWorseToolApp,
)


class DefectWorseToolRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = DefectWorseToolApp.__new__(DefectWorseToolApp)

    def test_stage_bsl_does_not_overwrite_global_bsl(self) -> None:
        bsl = pd.DataFrame(
            [
                {"Defect type": "D1", "BSL count": 2.0, "Stage_ID": "S1", "Step_ID": "P1"},
                {"Defect type": "D1", "BSL count": 7.0, "Stage_ID": "S2", "Step_ID": "P1"},
                {"Defect type": "D1", "BSL count": 3.0, "Stage_ID": "", "Step_ID": ""},
            ]
        )

        stage_lookup, global_lookup = build_bsl_lookup(bsl)

        self.assertEqual(stage_lookup[("d1", "S1", "P1")], 2.0)
        self.assertEqual(stage_lookup[("d1", "S2", "P1")], 7.0)
        self.assertEqual(global_lookup, {"d1": 3.0})

    def test_conflicting_global_bsl_is_rejected(self) -> None:
        bsl = pd.DataFrame(
            [
                {"Defect type": "D1", "BSL count": 2.0},
                {"Defect type": "D1", "BSL count": 3.0},
            ]
        )

        with self.assertRaises(ValueError):
            build_bsl_lookup(bsl)

    def test_special_process_chart_matches_worse_tool_statistics(self) -> None:
        rows = []
        for stage, values in (("S1", [1, 2, 3, 4, 5]), ("S2", [2, 3, 4, 5, 6])):
            for index, value in enumerate(values, start=1):
                rows.append(
                    {
                        "Lot_ID": "L{}".format(stage),
                        "Wafer_NO": index,
                        "Scan_Time": "2026-07-{:02d}".format(index),
                        "D1": value,
                        "Stage_ID": stage,
                        "Step_ID": "P1",
                        "Equipment_ID": "KE1001",
                        "Chamber_ID": "C1",
                    }
                )
        raw = add_grouping_columns(pd.DataFrame(rows))
        rules = parse_special_process_rules("D1: S1_P1, S2_P1")
        result = summarize_one_defect(
            raw,
            "D1",
            {},
            {"d1": 0.0},
            min_wafers=1,
            special_process_rules=rules,
        )

        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(row["Stage_ID"], SPECIAL_STAGE_ID)

        filtered = filter_outliers_for_defect(raw, "D1")
        selected = self.app._format_step_only_option("P1")
        _, chart = self.app._filter_chart_process(filtered, "D1", selected, rules, "stage_step")
        chart = self.app._filter_chart_group_mode(chart, CHART_GROUP_MODE_CHAMBER)

        self.assertAlmostEqual(chart["D1"].mean(), row["Mean_Count"])
        self.assertAlmostEqual(chart["D1"].median(), row["Median_Count"])
        _, normal_stage = self.app._filter_chart_process(
            filtered, "D1", "S1_P1", rules, "stage_step"
        )
        self.assertTrue(normal_stage.empty)

    def test_every_row_can_be_charted_by_chamber_or_equipment(self) -> None:
        raw = add_grouping_columns(
            pd.DataFrame(
                [
                    {
                        "Lot_ID": "L1",
                        "Wafer_NO": 1,
                        "Scan_Time": "2026-07-01",
                        "D1": 1,
                        "Stage_ID": "S1",
                        "Step_ID": "P1",
                        "Equipment_ID": "KE1001",
                        "Chamber_ID": "C1",
                    },
                    {
                        "Lot_ID": "L2",
                        "Wafer_NO": 1,
                        "Scan_Time": "2026-07-01",
                        "D1": 1,
                        "Stage_ID": "S1",
                        "Step_ID": "P1",
                        "Equipment_ID": "KP1001",
                        "Chamber_ID": "C2",
                    },
                ]
            )
        )

        chamber = self.app._filter_chart_group_mode(raw, CHART_GROUP_MODE_CHAMBER)
        equipment = self.app._filter_chart_group_mode(raw, CHART_GROUP_MODE_EQUIPMENT)

        self.assertEqual(chamber["Chart_Group"].tolist(), ["C1", "C2"])
        self.assertEqual(equipment["Chart_Group"].tolist(), ["KE1001", "KP1001"])

    def test_outlier_values_can_be_removed_or_capped(self) -> None:
        raw = pd.DataFrame({"D1": [0.0, 0.0, 0.0, 100.0]})
        mean = raw["D1"].mean()
        std = raw["D1"].std(ddof=0)
        expected_limit = mean + std

        removed = handle_outliers_for_defect(
            raw,
            "D1",
            outlier_sigma=1.0,
            outlier_handling=OUTLIER_HANDLING_FILTER,
        )
        capped = handle_outliers_for_defect(
            raw,
            "D1",
            outlier_sigma=1.0,
            outlier_handling=OUTLIER_HANDLING_CAP,
        )

        self.assertEqual(len(removed), 3)
        self.assertEqual(len(capped), 4)
        self.assertAlmostEqual(capped["D1"].max(), expected_limit)

    def test_capped_chart_statistics_match_worse_tool(self) -> None:
        raw = add_grouping_columns(
            pd.DataFrame(
                [
                    {
                        "Lot_ID": "L1",
                        "Wafer_NO": index,
                        "Scan_Time": "2026-07-01",
                        "D1": value,
                        "Stage_ID": "S1",
                        "Step_ID": "P1",
                        "Equipment_ID": "KP1001",
                        "Chamber_ID": "C1",
                    }
                    for index, value in enumerate([0.0, 0.0, 0.0, 100.0], start=1)
                ]
            )
        )
        result = summarize_one_defect(
            raw,
            "D1",
            {},
            {"d1": 0.0},
            min_wafers=1,
            outlier_sigma=1.0,
            outlier_handling=OUTLIER_HANDLING_CAP,
        )
        chart = handle_outliers_for_defect(
            raw,
            "D1",
            outlier_sigma=1.0,
            outlier_handling=OUTLIER_HANDLING_CAP,
        )
        _, chart = self.app._filter_chart_process(chart, "D1", "S1_P1", {}, "stage_step")
        chart = self.app._filter_chart_group_mode(chart, CHART_GROUP_MODE_EQUIPMENT)

        self.assertEqual(result.iloc[0]["Outlier Handling"], OUTLIER_HANDLING_CAP)
        self.assertAlmostEqual(chart["D1"].mean(), result.iloc[0]["Mean_Count"])
        self.assertAlmostEqual(chart["D1"].median(), result.iloc[0]["Median_Count"])

    def test_recent_trimmed_bsl_does_not_filter_summary_rows(self) -> None:
        values = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 100.0]
        raw = add_grouping_columns(
            pd.DataFrame(
                [
                    {
                        "Lot_ID": "L1",
                        "Wafer_NO": index,
                        "Scan_Time": "2026-07-{:02d}".format(index),
                        "D1": value,
                        "Stage_ID": "S1",
                        "Step_ID": "P1",
                        "Equipment_ID": "KP1001",
                        "Chamber_ID": "C1",
                    }
                    for index, value in enumerate(values, start=1)
                ]
            )
        )
        original = raw.copy(deep=True)

        recent_bsl = calculate_recent_trimmed_bsl(raw, "D1")
        result = summarize_one_defect(
            raw,
            "D1",
            {},
            {"d1": 0.0},
            min_wafers=1,
            outlier_sigma=100.0,
            recent_trimmed_bsl=recent_bsl,
        )

        pd.testing.assert_frame_equal(raw, original)
        self.assertAlmostEqual(recent_bsl, 4.5)
        self.assertEqual(result.iloc[0]["Row_Count"], len(values))
        self.assertAlmostEqual(result.iloc[0]["Mean_Count"], sum(values) / len(values))
        self.assertAlmostEqual(result.iloc[0]["Recent Trimmed BSL"], 4.5)

    def test_recent_window_rejects_invalid_time_instead_of_dropping_row(self) -> None:
        raw = pd.DataFrame(
            {
                "Scan_Time": ["2026-07-01", "not-a-time"],
                "D1": [1.0, 2.0],
            }
        )

        with self.assertRaisesRegex(ValueError, "avoid silently omitting data"):
            filter_by_recent_scan_time(raw, data_window="14d")

    def test_csv_reader_preserves_na_like_tool_identifiers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "input.csv"
            path.write_text(
                "LOT_ID,WAFER_NO,SCAN_TIME,STAGE,STEP_ID,EQUIPMENT_ID,CHAMBER,D1\n"
                "L1,1,2026-07-01,S1,P1,NA,N/A,3\n",
                encoding="utf-8",
            )

            loaded = read_table(str(path))

        self.assertEqual(loaded.loc[0, "Equipment_ID"], "NA")
        self.assertEqual(loaded.loc[0, "Chamber_ID"], "N/A")


if __name__ == "__main__":
    unittest.main()
