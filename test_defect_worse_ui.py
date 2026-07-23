import unittest

from matplotlib.colors import to_hex

import pandas as pd

from defect_worse_ui import (
    CHART_GROUP_MODE_CHAMBER,
    CHART_GROUP_MODE_EQUIPMENT,
    DefectWorseToolApp,
    add_equal_spacing_index,
    prepare_trend_data,
)


class _Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


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
            [1, 2, 3],
        )
        self.assertEqual(
            spaced.loc[spaced["Chart_Group"] == "CH-B", "Observation_Index"].tolist(),
            [1, 2],
        )

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


if __name__ == "__main__":
    unittest.main()
