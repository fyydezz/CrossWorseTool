import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from matplotlib.colors import to_hex

from chart_context import analysis_references, annotate_chart_data
from defect_worse_tool import (add_grouping_columns, build_worse_tool_result,
                              filter_by_recent_scan_time, handle_outliers_for_defect)
from defect_worse_ui import NAMED_COLORS
from ppt_report import make_renderer


def sample_data():
    rows = []
    for tool, mean, times in (("KP-A", 12, [0, 0, 1, 4, 8, 11]),
                              ("KP-B", 3, [0, 2, 2, 5, 10, 11]),
                              ("KP-HISTORY", 20, [-50, -49, -45, -44, -40, -39])):
        for index, day in enumerate(times):
            rows.append(dict(Lot_ID=tool, Wafer_NO=str(index), Equipment_ID=tool,
                             Chamber_ID=tool + "-C", Stage_ID="S", Step_ID="P",
                             Scan_Time=pd.Timestamp("2026-08-01") + pd.Timedelta(days=day),
                             Process_Time=pd.Timestamp("2026-07-31") + pd.Timedelta(days=day),
                             D1=mean + index))
    return add_grouping_columns(pd.DataFrame(rows))


def options():
    return dict(bsl_source="recent_mean", data_window="14d", min_wafers=5,
                bsl_multiplier=1.5, outlier_sigma=3, outlier_handling="cap",
                process_aggregation="stage_step", chart_group_mode="By Equipment ID")


def chart_data(renderer, raw, window):
    data = handle_outliers_for_defect(filter_by_recent_scan_time(raw, window), "D1", 3, "cap")
    data = renderer._filter_chart_group_mode(data, "By Equipment ID")
    return annotate_chart_data(renderer, raw, data, "D1", options(), window)


class ChartViewTests(unittest.TestCase):
    def test_all_trends_keep_every_row_at_unit_spacing(self):
        renderer = make_renderer()
        data = chart_data(renderer, sample_data(), "all")
        for method in (renderer._draw_trend, renderer._draw_trend_all_chambers,
                       renderer._draw_trend_sequence_by_tool):
            method("D1", "S/P", "Process_Time", data)
            xs = []
            for artist, part, kind in renderer._hover_points:
                values = artist.get_xdata()
                np.testing.assert_array_equal(np.diff(values), np.ones(len(values) - 1))
                self.assertTrue(part.Selected_Time.is_monotonic_increasing)
                xs.extend(values)
            self.assertEqual(len(xs), len(data))
            if "sequence" in method.__name__:
                np.testing.assert_array_equal(xs, np.arange(1, len(data) + 1))

    def test_shared_rank_and_focus_use_selected_tools_actual_times(self):
        renderer = make_renderer()
        raw = sample_data()
        box = chart_data(renderer, raw, "14d")
        trend = chart_data(renderer, raw, "all")
        self.assertEqual(box.attrs["tool_order"], ["KP-A", "KP-B", "KP-HISTORY"])
        self.assertEqual(box.attrs["tool_order"], trend.attrs["tool_order"])
        renderer._draw_box("D1", "S/P", box)
        renderer.focus_tool("KP-B")
        renderer._draw_trend("D1", "S/P", "Process_Time", trend)
        self.assertEqual(renderer.chart_focus[renderer._chart_context_key], "KP-B")
        self.assertIn("dates for T2", renderer.ax.get_xlabel())
        self.assertIn("2026-07-31", renderer.ax.get_xticklabels()[0].get_text())
        for artist, metadata in renderer.chart_artist_registry.items():
            self.assertEqual(artist.get_alpha(), 1 if metadata["label"] == "KP-B" else .25)
        renderer.focus_tool(None)
        self.assertIsNone(renderer.selected_chart_artist)

    def test_references_match_core_and_do_not_mutate_chart_rows(self):
        raw = sample_data()
        before = raw.copy(deep=True)
        refs = analysis_references(raw, "D1", options())[("S", "P")]
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "raw.csv"
            raw.to_csv(source, index=False)
            core_options = options()
            core_options.pop("chart_group_mode")
            core_options["bsl_multiplier"] = 0
            result = build_worse_tool_result(str(source), **core_options)
        self.assertEqual(refs["BSL"], result["BSL count"].iloc[0])
        self.assertEqual(refs["Golden"], result["Golden Mean_Count"].iloc[0])
        self.assertEqual(refs["Threshold"], refs["BSL"] * 1.5)
        data = chart_data(make_renderer(), raw, "all")
        self.assertEqual(len(data), len(raw))
        pd.testing.assert_frame_equal(raw, before)

    def test_missing_golden_does_not_hide_available_baseline(self):
        opts = options()
        opts["min_wafers"] = 100
        refs = analysis_references(sample_data(), "D1", opts)[("S", "P")]
        self.assertIsNone(refs["Golden"])
        self.assertIsNotNone(refs["BSL"])

    def test_reference_toggles_and_black_raw_points(self):
        renderer = make_renderer()
        data = chart_data(renderer, sample_data(), "14d")
        renderer.show_threshold_line.set(False)
        renderer._draw_box("D1", "S/P", data)
        labels = [line.get_label() for line in renderer.ax.lines]
        self.assertIn("_BSL", labels)
        self.assertIn("_Golden", labels)
        self.assertNotIn("_Threshold", labels)
        self.assertEqual(sum(len(artist.get_offsets()) for artist in renderer.ax.collections), len(data))
        self.assertTrue(all(to_hex(artist.get_facecolors()[0]) == "#000000" for artist in renderer.ax.collections))

    def test_dense_export_keeps_full_names_and_expands_without_changing_ui(self):
        renderer = make_renderer()
        rows = [{"Chart_Group": "KP-{:02d}-LONG-TOOL-NAME".format(tool), "D1": tool + index}
                for tool in range(30) for index in range(6)]
        renderer._draw_box("D1", "S/P", pd.DataFrame(rows))
        original_size = renderer.fig.get_size_inches().copy()
        exported = make_renderer()
        with tempfile.TemporaryDirectory() as folder, patch("ppt_report.make_renderer", return_value=exported):
            renderer.export_current_chart(str(Path(folder) / "chart.png"))
        self.assertEqual(len(exported._chart_groups), 30)
        self.assertGreater(exported.fig.get_figheight(), original_size[1])
        np.testing.assert_array_equal(renderer.fig.get_size_inches(), original_size)
        self.assertEqual(sum(len(a.get_offsets()) for a in exported.ax.collections), len(rows))
        text = " ".join(t.get_text().replace("\n", "") for t in exported._chart_side.texts)
        for group in exported._chart_groups:
            self.assertIn(group, text)
        canvas = exported.fig.canvas.get_renderer()
        bounds = [t.get_window_extent(canvas) for t in exported._chart_side.texts]
        for index, a in enumerate(bounds):
            self.assertLessEqual(a.x1, exported.fig.bbox.x1)
            self.assertGreaterEqual(a.y0, exported.fig.bbox.y0)
            self.assertTrue(all(not a.overlaps(b) for b in bounds[index + 1:]))

    def test_named_palette_has_readable_red_yellow_blue_and_valid_colors(self):
        for label in ("红色 / Red", "黄色 / Yellow", "蓝色 / Blue"):
            self.assertIn(label, NAMED_COLORS)
        self.assertEqual(len({to_hex(color) for color in NAMED_COLORS.values()}), len(NAMED_COLORS))


if __name__ == "__main__":
    unittest.main()
