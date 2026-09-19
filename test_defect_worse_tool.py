from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from defect_worse_tool import (
    BSL_SOURCE_CALCULATED_MEAN,
    BSL_SOURCE_FILE,
    SPECIAL_STAGE_ID,
    add_grouping_columns,
    build_bsl_lookup,
    build_worse_tool_result,
    calculate_mean_bsl,
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

    def test_recent_trimmed_bsl_is_fixed_to_14_days_for_all_analysis_windows(self):
        rows = []
        for day, start in (("2026-06-01", 100), ("2026-09-05", 10), ("2026-09-19", 20)):
            for value in range(start, start + 10):
                rows.append(dict(Lot_ID=day, Wafer_NO=value, Scan_Time=day, D1=value,
                                 Stage_ID="S", Step_ID="P", Equipment_ID="KP01", Chamber_ID="A"))
        raw = pd.DataFrame(rows)
        with TemporaryDirectory() as folder:
            source, bsl = Path(folder) / "raw.csv", Path(folder) / "bsl.csv"
            raw.to_csv(source, index=False)
            pd.DataFrame({"Defect type": ["D1"], "BSL count": [1]}).to_csv(bsl, index=False)
            for window, count in (("all", 30), ("14d", 20), ("7d", 10)):
                with self.subTest(window=window):
                    result = build_worse_tool_result(str(source), str(bsl), defect_columns=["D1"],
                                                     data_window=window, outlier_sigma=100)
                    row = result.iloc[0]
                    self.assertAlmostEqual(row["Recent Trimmed BSL"], 19.5)
                    self.assertEqual(row["Row_Count"], count)
                    self.assertEqual(row["Wafer_Count"], count)
                    expected = raw.iloc[-count:].D1
                    self.assertAlmostEqual(row["Mean_Count"], expected.mean())
                    self.assertAlmostEqual(row["Median_Count"], expected.median())

    def test_recent_trimmed_bsl_uses_all_available_data_when_shorter_than_14_days(self):
        raw = pd.DataFrame([dict(Lot_ID="L", Wafer_NO=i, Scan_Time="2026-09-{:02d}".format(10 + i),
                                 D1=i, Stage_ID="S", Step_ID="P", Equipment_ID="KP01", Chamber_ID="A")
                            for i in range(10)])
        with TemporaryDirectory() as folder:
            source, bsl = Path(folder) / "raw.csv", Path(folder) / "bsl.csv"
            raw.to_csv(source, index=False)
            pd.DataFrame({"Defect type": ["D1"], "BSL count": [1]}).to_csv(bsl, index=False)
            for handling in (OUTLIER_HANDLING_FILTER, OUTLIER_HANDLING_CAP):
                result = build_worse_tool_result(str(source), str(bsl), defect_columns=["D1"],
                                                 outlier_handling=handling, outlier_sigma=1)
                self.assertAlmostEqual(result["Recent Trimmed BSL"].iloc[0], 4.5)

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
        self.assertEqual(row["BSL Source"], BSL_SOURCE_FILE)

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

    def test_calculated_mean_can_be_used_as_bsl_without_bsl_file(self) -> None:
        rows = []
        for equipment, value in (("KP_HIGH", 10.0), ("KP_LOW", 0.0)):
            for wafer in range(1, 6):
                rows.append(
                    {
                        "LOT_ID": "L_{}".format(equipment),
                        "WAFER_NO": wafer,
                        "SCAN_TIME": "2026-08-{:02d}".format(wafer),
                        "D1": value,
                        "STAGE": "S1",
                        "STEP_ID": "P1",
                        "EQUIPMENT_ID": equipment,
                        "CHAMBER": "C1",
                    }
                )
        for wafer in range(1, 6):
            rows.append(
                {
                    "LOT_ID": "L_OLD",
                    "WAFER_NO": wafer,
                    "SCAN_TIME": "2026-06-{:02d}".format(wafer),
                    "D1": 100.0,
                    "STAGE": "S1",
                    "STEP_ID": "P1",
                    "EQUIPMENT_ID": "KP_OLD",
                    "CHAMBER": "C1",
                }
            )

        with TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.csv"
            pd.DataFrame(rows).to_csv(input_path, index=False)
            result = build_worse_tool_result(
                input_path=str(input_path),
                bsl_source=BSL_SOURCE_CALCULATED_MEAN,
                bsl_multiplier=1.5,
                min_wafers=5,
                outlier_sigma=100.0,
                data_window="14d",
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["Equipment ID"], "KP_HIGH")
        self.assertAlmostEqual(result.iloc[0]["BSL count"], 5.0)
        self.assertEqual(result.iloc[0]["BSL Source"], BSL_SOURCE_CALCULATED_MEAN)
        self.assertAlmostEqual(result.iloc[0]["Recent Trimmed BSL"], 5.0)

    def test_calculated_mean_bsl_uses_selected_outlier_handling(self) -> None:
        raw = pd.DataFrame({"D1": [0.0, 0.0, 0.0, 100.0]})
        expected_cap = handle_outliers_for_defect(
            raw,
            "D1",
            outlier_sigma=1.0,
            outlier_handling=OUTLIER_HANDLING_CAP,
        )["D1"].mean()

        calculated = calculate_mean_bsl(
            raw,
            "D1",
            outlier_sigma=1.0,
            outlier_handling=OUTLIER_HANDLING_CAP,
        )

        self.assertAlmostEqual(calculated, expected_cap)


if __name__ == "__main__":
    unittest.main()
