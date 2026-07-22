import unittest

from matplotlib.colors import to_hex

from defect_worse_ui import DefectWorseToolApp


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


if __name__ == "__main__":
    unittest.main()
