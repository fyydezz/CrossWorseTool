import unittest

from matplotlib.colors import to_hex
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

import pandas as pd

from defect_worse_ui import (
    BSL_SOURCE_CALCULATED_MEAN,
    BSL_SOURCE_FILE,
    BSL_SOURCE_LABELS,
    CHART_GROUP_MODE_CHAMBER,
    CHART_GROUP_MODE_EQUIPMENT,
    DefectWorseToolApp,
    add_equal_spacing_index,
    build_equal_spacing_time_ticks,
    prepare_trend_data,
    sample_tick_labels,
)


class _Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class DefectWorseUiStyleTests(unittest.TestCase):
    def test_box_rank_colors_run_from_red_to_blue(self):
        colors = DefectWorseToolApp._box_rank_colors(4)

        self.assertEqual(to_hex(colors[0]), "#b40426")
        self.assertEqual(to_hex(colors[-1]), "#3b4cc0")
        self.assertEqual(len(set(to_hex(color) for color in colors)), 4)

    def test_default_trend_palette_is_distinct_for_many_tools(self):
        app = object.__new__(DefectWorseToolApp)
        app.color_scheme = _Value("Distinct")
        app.custom_color = _Value("#1565C0")

        colors = app._colors(45)

        self.assertEqual(len(colors), 45)
        self.assertEqual(len(set(to_hex(color) for color in colors)), 45)

    def test_artist_override_is_scoped_by_context_key(self):
        app = object.__new__(DefectWorseToolApp)
        app.artist_style_overrides = {
            ("line", "DEFECT_A|STAGE_1|Chamber|CH-A"): {
                "color": "#102030",
                "linewidth": 3.4,
            }
        }

        selected = app._artist_style(
            "line", "DEFECT_A|STAGE_1|Chamber|CH-A", "#FFFFFF", 1.0
        )
        untouched = app._artist_style(
            "line", "DEFECT_A|STAGE_1|Equipment ID|CH-A", "#FFFFFF", 1.0
        )

        self.assertEqual(selected, ("#102030", 3.4))
        self.assertEqual(untouched, ("#FFFFFF", 1.0))

    def test_box_label_font_size_supports_auto_and_fixed_values(self):
        app = object.__new__(DefectWorseToolApp)
        app.box_label_font_size = _Value(0.0)
        self.assertEqual(app._box_stats_font_size(150), 11.5)
        self.assertEqual(app._box_stats_font_size(50), 8.0)

        app.box_label_font_size = _Value(13.5)
        self.assertEqual(app._box_stats_font_size(50), 13.5)

    def test_trend_data_preserves_duplicate_times_and_every_input_row(self):
        raw = pd.DataFrame(
            [
                {
                    "Chart_Group": "CH-A",
                    "Chart_Group_Type": "Chamber",
                    "Scan_Time": "2026-07-01 10:30",
                    "D1": 3.0,
                },
                {
                    "Chart_Group": "CH-A",
                    "Chart_Group_Type": "Chamber",
                    "Scan_Time": "2026-07-01 10:30",
                    "D1": 7.0,
                },
                {
                    "Chart_Group": "CH-A",
                    "Chart_Group_Type": "Chamber",
                    "Scan_Time": "2026-07-03 18:00",
                    "D1": 5.0,
                },
                {
                    "Chart_Group": "CH-B",
                    "Chart_Group_Type": "Chamber",
                    "Scan_Time": "2026-07-02 08:00",
                    "D1": 4.0,
                },
                {
                    "Chart_Group": "CH-B",
                    "Chart_Group_Type": "Chamber",
                    "Scan_Time": "2026-07-09 23:15",
                    "D1": 9.0,
                },
            ]
        )

        trend = prepare_trend_data(raw, "D1", "Scan_Time")
        spaced = add_equal_spacing_index(trend)

        self.assertEqual(len(trend), len(raw))
        self.assertEqual(trend.loc[trend["Chart_Group"] == "CH-A", "D1"].tolist(), [3.0, 7.0, 5.0])
        self.assertEqual(
            spaced.loc[spaced["Chart_Group"] == "CH-A", "Observation_Index"].tolist(),
            [1, 1, 3],
        )
        self.assertEqual(
            spaced.loc[spaced["Chart_Group"] == "CH-B", "Observation_Index"].tolist(),
            [2, 4],
        )

        tick_positions, tick_labels = build_equal_spacing_time_ticks(spaced, max_ticks=10)
        self.assertEqual(tick_positions, [1, 2, 3, 4])
        self.assertEqual(
            tick_labels,
            [
                "2026-07-01\n10:30",
                "2026-07-02\n08:00",
                "2026-07-03\n18:00",
                "2026-07-09\n23:15",
            ],
        )

    def test_time_tick_sampling_keeps_first_and_last_values(self):
        positions, labels = sample_tick_labels(
            list(range(1, 101)),
            ["time-{}".format(index) for index in range(1, 101)],
            max_ticks=12,
        )

        self.assertLessEqual(len(positions), 12)
        self.assertEqual((positions[0], labels[0]), (1, "time-1"))
        self.assertEqual((positions[-1], labels[-1]), (100, "time-100"))

    def test_chart_grouping_keeps_rows_with_missing_group_identifier(self):
        app = object.__new__(DefectWorseToolApp)
        raw = pd.DataFrame(
            [
                {"Equipment_ID": "KP1001", "Chamber_ID": ""},
                {"Equipment_ID": "", "Chamber_ID": "C2"},
            ]
        )

        by_chamber = app._filter_chart_group_mode(raw, CHART_GROUP_MODE_CHAMBER)
        by_equipment = app._filter_chart_group_mode(raw, CHART_GROUP_MODE_EQUIPMENT)

        self.assertEqual(len(by_chamber), len(raw))
        self.assertEqual(len(by_equipment), len(raw))
        self.assertEqual(by_chamber["Chart_Group"].tolist(), ["(Missing Chamber)", "C2"])
        self.assertEqual(by_equipment["Chart_Group"].tolist(), ["KP1001", "(Missing Equipment ID)"])

    def test_ui_bsl_source_labels_map_to_core_values(self):
        app = object.__new__(DefectWorseToolApp)

        app.bsl_source = _Value("Input BSL file")
        self.assertEqual(app._selected_bsl_source(), BSL_SOURCE_FILE)

        calculated_label = "Calculated defect mean (after outlier handling)"
        self.assertEqual(BSL_SOURCE_LABELS[calculated_label], BSL_SOURCE_CALCULATED_MEAN)
        app.bsl_source = _Value(calculated_label)
        self.assertEqual(app._selected_bsl_source(), BSL_SOURCE_CALCULATED_MEAN)

    def test_both_overlay_trends_use_equal_time_spacing_and_time_labels(self):
        raw = pd.DataFrame(
            [
                {"Chart_Group": "A", "Chart_Group_Type": "Chamber", "Scan_Time": "2026-08-01", "D1": 1.0},
                {"Chart_Group": "A", "Chart_Group_Type": "Chamber", "Scan_Time": "2026-08-20", "D1": 2.0},
                {"Chart_Group": "A", "Chart_Group_Type": "Chamber", "Scan_Time": "2026-08-20", "D1": 3.0},
                {"Chart_Group": "B", "Chart_Group_Type": "Chamber", "Scan_Time": "2026-08-05", "D1": 4.0},
                {"Chart_Group": "B", "Chart_Group_Type": "Chamber", "Scan_Time": "2026-08-06", "D1": 5.0},
            ]
        )
        trend = prepare_trend_data(raw, "D1", "Scan_Time")
        app = object.__new__(DefectWorseToolApp)
        app.fig = Figure(figsize=(6, 4), dpi=100)
        app.canvas = FigureCanvasAgg(app.fig)
        app.line_width = _Value(1.8)
        app.marker_size = _Value(4.0)
        app.color_scheme = _Value("Distinct")
        app.custom_color = _Value("#1565C0")
        app.y_min = _Value("")
        app.y_max = _Value("")
        app.selected_chart_item = _Value("")
        app.status = _Value("")
        app.selected_chart_artist = None
        app.chart_artist_registry = {}
        app.artist_style_overrides = {}

        for draw_method in (app._draw_trend, app._draw_trend_all_chambers):
            draw_method("D1", "S1_P1", "Scan_Time", trend)
            plotted = {
                line.get_label(): list(line.get_xdata())
                for line in app.fig.axes[0].lines
                if line.get_label() in {"A", "B"}
            }
            self.assertEqual(plotted, {"A": [1, 4, 4], "B": [2, 3]})
            tick_text = [label.get_text() for label in app.fig.axes[0].get_xticklabels()]
            self.assertIn("2026-08-01", tick_text)
            self.assertIn("2026-08-20", tick_text)
            self.assertIsNone(app.fig.axes[0].get_legend())
            self.assertIsNotNone(app.fig.axes[1].get_legend())
            renderer = app.canvas.get_renderer()
            tick_bounds = [
                label.get_window_extent(renderer)
                for label in app.fig.axes[0].get_xticklabels()
                if label.get_text()
            ]
            for index, bounds in enumerate(tick_bounds):
                for other_bounds in tick_bounds[index + 1 :]:
                    self.assertFalse(bounds.overlaps(other_bounds))

    def test_dense_box_uses_separate_non_overlapping_summary_panel(self):
        rows = []
        for tool_index in range(48):
            for value_index in range(6):
                rows.append(
                    {
                        "Chart_Group": "CHAMBER-{:02d}".format(tool_index),
                        "Chart_Group_Type": "Chamber",
                        "D1": float(200 - tool_index * 3 + value_index),
                    }
                )
        app = object.__new__(DefectWorseToolApp)
        app.fig = Figure(figsize=(8.8, 5.8), dpi=110)
        app.canvas = FigureCanvasAgg(app.fig)
        app.box_line_width = _Value(1.4)
        app.box_label_font_size = _Value(0.0)
        app.show_box_count = _Value(True)
        app.show_box_median = _Value(True)
        app.show_box_mean = _Value(True)
        app.y_min = _Value("")
        app.y_max = _Value("")
        app.selected_chart_item = _Value("")
        app.status = _Value("")
        app.selected_chart_artist = None
        app.chart_artist_registry = {}
        app.artist_style_overrides = {}

        app._draw_box("D1", "S1_P1", pd.DataFrame(rows))

        plot_ax, sidebar_ax = app.fig.axes
        self.assertEqual(len(plot_ax.texts), 0)
        self.assertIsNone(plot_ax.get_legend())
        self.assertIsNotNone(sidebar_ax.get_legend())
        summary_lines = [
            text for text in sidebar_ax.texts if text.get_text().startswith("T") and text.get_text() != "TOOL SUMMARY"
        ]
        self.assertEqual(len(summary_lines), 48)

        renderer = app.canvas.get_renderer()
        plot_bounds = plot_ax.get_window_extent(renderer)
        key_bounds = sidebar_ax.get_legend().get_window_extent(renderer)
        summary_bounds = [text.get_window_extent(renderer) for text in summary_lines]
        for index, bounds in enumerate(summary_bounds):
            self.assertFalse(bounds.overlaps(plot_bounds))
            self.assertFalse(bounds.overlaps(key_bounds))
            for other_index, other_bounds in enumerate(summary_bounds[index + 1 :], start=index + 1):
                self.assertFalse(
                    bounds.overlaps(other_bounds),
                    "{} overlaps {}".format(
                        summary_lines[index].get_text(),
                        summary_lines[other_index].get_text(),
                    ),
                )
        tick_bounds = [
            label.get_window_extent(renderer)
            for label in plot_ax.get_xticklabels()
            if label.get_text()
        ]
        tick_labels = [label.get_text() for label in plot_ax.get_xticklabels() if label.get_text()]
        for index, bounds in enumerate(tick_bounds):
            for other_index, other_bounds in enumerate(tick_bounds[index + 1 :], start=index + 1):
                self.assertFalse(
                    bounds.overlaps(other_bounds),
                    "tick {} overlaps {}".format(tick_labels[index], tick_labels[other_index]),
                )

    def test_sequential_trend_has_equal_spacing_time_ticks_and_no_top_tool_labels(self):
        raw = pd.DataFrame(
            [
                {"Chart_Group": "A", "Chart_Group_Type": "Chamber", "Scan_Time": "2026-08-01", "D1": 1.0},
                {"Chart_Group": "A", "Chart_Group_Type": "Chamber", "Scan_Time": "2026-08-20", "D1": 2.0},
                {"Chart_Group": "B", "Chart_Group_Type": "Chamber", "Scan_Time": "2026-08-05", "D1": 4.0},
                {"Chart_Group": "B", "Chart_Group_Type": "Chamber", "Scan_Time": "2026-08-06", "D1": 5.0},
            ]
        )
        trend = prepare_trend_data(raw, "D1", "Scan_Time")
        app = object.__new__(DefectWorseToolApp)
        app.fig = Figure(figsize=(6, 4), dpi=100)
        app.canvas = FigureCanvasAgg(app.fig)
        app.line_width = _Value(1.8)
        app.marker_size = _Value(4.0)
        app.color_scheme = _Value("Distinct")
        app.custom_color = _Value("#1565C0")
        app.y_min = _Value("")
        app.y_max = _Value("")
        app.selected_chart_item = _Value("")
        app.status = _Value("")
        app.selected_chart_artist = None
        app.chart_artist_registry = {}
        app.artist_style_overrides = {}

        app._draw_trend_sequence_by_tool("D1", "S1_P1", "Scan_Time", trend)

        plot_ax, sidebar_ax = app.fig.axes
        plotted_positions = sorted(
            int(value)
            for line in plot_ax.lines
            if line.get_label() in {"A", "B"}
            for value in line.get_xdata()
        )
        self.assertEqual(plotted_positions, [1, 2, 3, 4])
        self.assertEqual(len(plot_ax.texts), 0)
        self.assertIsNotNone(sidebar_ax.get_legend())
        tick_text = [label.get_text() for label in plot_ax.get_xticklabels()]
        self.assertIn("2026-08-01\n00:00", tick_text)
        self.assertIn("2026-08-06\n00:00", tick_text)

    def test_dense_sequential_tool_legend_stays_outside_plot_without_collisions(self):
        rows = []
        for tool_index in range(30):
            for point_index in range(3):
                rows.append(
                    {
                        "Chart_Group": "CHAMBER-LONG-{:02d}".format(tool_index),
                        "Chart_Group_Type": "Chamber",
                        "Scan_Time": "2026-08-{:02d} {:02d}:00".format(
                            1 + point_index,
                            tool_index % 24,
                        ),
                        "D1": float(tool_index + point_index),
                    }
                )
        trend = prepare_trend_data(pd.DataFrame(rows), "D1", "Scan_Time")
        app = object.__new__(DefectWorseToolApp)
        app.fig = Figure(figsize=(8.8, 5.8), dpi=110)
        app.canvas = FigureCanvasAgg(app.fig)
        app.line_width = _Value(1.8)
        app.marker_size = _Value(4.0)
        app.color_scheme = _Value("Distinct")
        app.custom_color = _Value("#1565C0")
        app.y_min = _Value("")
        app.y_max = _Value("")
        app.selected_chart_item = _Value("")
        app.status = _Value("")
        app.selected_chart_artist = None
        app.chart_artist_registry = {}
        app.artist_style_overrides = {}

        app._draw_trend_sequence_by_tool("D1", "S1_P1", "Scan_Time", trend)

        plot_ax, sidebar_ax = app.fig.axes
        renderer = app.canvas.get_renderer()
        plot_bounds = plot_ax.get_window_extent(renderer)
        legend = sidebar_ax.get_legend()
        legend_bounds = legend.get_window_extent(renderer)
        self.assertFalse(plot_bounds.overlaps(legend_bounds))
        self.assertEqual(len(plot_ax.texts), 0)

        legend_text_bounds = [text.get_window_extent(renderer) for text in legend.get_texts()]
        for index, bounds in enumerate(legend_text_bounds):
            for other_bounds in legend_text_bounds[index + 1 :]:
                self.assertFalse(bounds.overlaps(other_bounds))

        tick_bounds = [
            label.get_window_extent(renderer)
            for label in plot_ax.get_xticklabels()
            if label.get_text()
        ]
        for index, bounds in enumerate(tick_bounds):
            for other_bounds in tick_bounds[index + 1 :]:
                self.assertFalse(bounds.overlaps(other_bounds))


if __name__ == "__main__":
    unittest.main()
