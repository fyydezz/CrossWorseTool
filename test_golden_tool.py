import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

import pandas as pd

from defect_worse_tool import (
    GOLDEN_COLUMNS, add_grouping_columns, summarize_one_defect,
    parse_special_process_rules, write_result_to_excel,
)
from ppt_report import make_renderer


class GoldenToolTests(unittest.TestCase):
    def data(self):
        rows = []
        for stage, tool, chamber, count, wafers in (
            ("S1", "KE_BAD", "A", 20, 8),
            ("S1", "KE_SMALL", "B", 0, 4),
            ("S1", "KE_GOOD", "C", 2, 5),
            ("S2", "KE_GOOD2", "D", 1, 6),
            ("S2", "KE_BAD2", "E", 15, 8),
        ):
            for wafer in range(wafers):
                rows.append(dict(Lot_ID=tool, Wafer_NO=wafer, Scan_Time="2026-09-10",
                                 Stage_ID=stage, Step_ID="P", Equipment_ID=tool,
                                 Chamber_ID=chamber, D1=count))
        # Repeated cross records must not turn 4 wafers into 5 eligible wafers.
        rows += [row.copy() for row in rows if row["Equipment_ID"] == "KE_SMALL"]
        return add_grouping_columns(pd.DataFrame(rows))

    def test_golden_selected_from_all_eligible_tools_before_worse_filter(self):
        result = summarize_one_defect(self.data(), "D1", {}, {"d1": 5}, min_wafers=1)
        first = result.loc[result["Stage_ID"] == "S1"].iloc[0]
        self.assertEqual(first["Golden Equipment ID"], "KE_GOOD")
        self.assertEqual(first["Golden Chamber ID"], "C")
        self.assertEqual(first["Golden Wafer_Count"], 5)
        self.assertEqual(first["Golden Mean_Count"], 2)
        self.assertEqual(first["Mean minus Golden"], 18)
        self.assertEqual(first["Mean / Golden"], 10)
        second = result.loc[result["Stage_ID"] == "S2"].iloc[0]
        self.assertEqual(second["Golden Mean_Count"], 1)

    def test_step_only_and_special_layers_share_the_correct_golden(self):
        for options in (
            {"process_aggregation": "step"},
            {"special_process_rules": parse_special_process_rules("D1: S1_P, S2_P")},
        ):
            with self.subTest(options=options):
                result = summarize_one_defect(self.data(), "D1", {}, {"d1": 5}, **options)
                self.assertEqual(set(result["Golden Equipment ID"]), {"KE_GOOD2"})
                self.assertEqual(set(result["Golden Mean_Count"]), {1})

    def test_zero_golden_and_no_eligible_reference(self):
        data = self.data()
        data.loc[data["Equipment_ID"] == "KE_GOOD", "D1"] = 0
        result = summarize_one_defect(data, "D1", {}, {"d1": 5})
        self.assertTrue(pd.isna(result.loc[result["Stage_ID"] == "S1", "Mean / Golden"].iloc[0]))
        tiny = data.loc[data["Equipment_ID"] == "KE_BAD"].head(3)
        result = summarize_one_defect(tiny, "D1", {}, {"d1": 5}, min_wafers=1)
        self.assertTrue(result["Golden Mean_Count"].isna().all())
        # Raising the analysis minimum also raises the golden minimum.
        result = summarize_one_defect(data, "D1", {}, {"d1": 5}, min_wafers=6)
        self.assertEqual(result.loc[result["Stage_ID"] == "S1", "Golden Equipment ID"].iloc[0], "KE_BAD")

    def test_append_old_schema_preserves_old_rows_and_adds_golden_columns(self):
        result = summarize_one_defect(self.data(), "D1", {}, {"d1": 5})
        with TemporaryDirectory() as folder:
            path = Path(folder) / "result.xlsx"
            write_result_to_excel(result.drop(columns=GOLDEN_COLUMNS), str(path))
            write_result_to_excel(result, str(path))
            loaded = pd.read_excel(path)
            self.assertEqual(len(loaded), len(result) * 2)
            self.assertTrue(loaded.iloc[:len(result)]["Golden Mean_Count"].isna().all())
            self.assertTrue(loaded.iloc[len(result):]["Golden Mean_Count"].notna().all())

    def test_raw_scatter_is_black_and_every_row_drawn_once(self):
        renderer = make_renderer()
        data = pd.DataFrame({"Chart_Group": ["A"] * 10, "D1": [1] * 9 + [100]})
        renderer._draw_box("D1", "S", data)
        scatter = renderer.fig.axes[0].collections
        self.assertEqual(sum(len(item.get_offsets()) for item in scatter), 10)
        for item in scatter:
            self.assertTrue((item.get_facecolors()[:, :3] == 0).all())
            self.assertTrue((item.get_facecolors()[:, 3] == 1).all())


if __name__ == "__main__":
    unittest.main()
