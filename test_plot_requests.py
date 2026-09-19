import queue
import threading
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from defect_worse_tool import add_grouping_columns
from defect_worse_ui import DefectWorseToolApp, CHART_TYPE_BOX
from ppt_report import Value


class PlotRequestTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(DefectWorseToolApp)
        self.app._plot_request_id = 0
        self.app.result_queue = queue.Queue()
        self.app.status = Value("Ready")
        self.app.busy = False
        self.app.after = Mock(return_value="timer")
        self.app._draw_box = Mock()
        self.app._draw_trend = Mock()
        self.app._draw_trend_all_chambers = Mock()
        self.app._draw_trend_sequence_by_tool = Mock()
        self.raw = add_grouping_columns(pd.DataFrame([
            dict(Lot_ID="L", Wafer_NO=i, Scan_Time="2026-09-19", D1=i,
                 Stage_ID="S", Step_ID="P", Equipment_ID="KP01", Chamber_ID="A")
            for i in range(6)]))

    def worker(self, request_id, data, time_col="Scan_Time"):
        self.app._plot_worker(request_id, data, "D1", "S_P", CHART_TYPE_BOX, time_col,
                              3, {}, "stage_step", "all", "By Equipment ID", "filter")

    def test_slow_old_completion_cannot_replace_new_plot(self):
        old_id = self.app._invalidate_plot_requests()
        entered, release = threading.Event(), threading.Event()
        from defect_worse_ui import filter_by_recent_scan_time
        def delay_old(data, data_window):
            if data is self.raw:
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Test synchronization timeout")
            return filter_by_recent_scan_time(data, data_window)
        newer = self.raw.copy()
        newer["D1"] = newer.D1 + 100
        with patch("defect_worse_ui.filter_by_recent_scan_time", side_effect=delay_old):
            thread = threading.Thread(target=self.worker, args=(old_id, self.raw), daemon=True)
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                new_id = self.app._invalidate_plot_requests()
                self.worker(new_id, newer)
                self.app._poll_results()
                self.assertEqual(self.app._draw_box.call_count, 1)
                self.assertGreaterEqual(self.app._draw_box.call_args.args[2].D1.min(), 100)
            finally:
                release.set()
                thread.join(5)
            self.assertFalse(thread.is_alive())
            self.app._poll_results()
            self.assertEqual(self.app._draw_box.call_count, 1)

    def test_old_error_is_ignored_but_current_error_is_reported(self):
        old_id = self.app._invalidate_plot_requests()
        new_id = self.app._invalidate_plot_requests()
        self.worker(old_id, self.raw, "Missing_Time")
        with patch("defect_worse_ui.messagebox.showerror") as error:
            self.app._poll_results()
            error.assert_not_called()
            self.assertEqual(self.app.status.get(), "Ready")
            self.worker(new_id, self.raw, "Missing_Time")
            self.app._poll_results()
            error.assert_called_once()
            self.assertFalse(self.app.busy)

    def test_worker_uses_submitted_dataset_not_reloaded_data(self):
        request_id = self.app._invalidate_plot_requests()
        self.app.raw_df = pd.DataFrame({"unrelated": [1]})
        self.worker(request_id, self.raw)
        self.app._poll_results()
        self.assertEqual(self.app._draw_box.call_args.args[2].D1.tolist(), list(range(6)))

    def test_loading_or_analysis_invalidates_pending_plot_results(self):
        request_id = self.app._invalidate_plot_requests()
        self.worker(request_id, self.raw)
        self.app.run_button = Mock()
        self.app.ppt_button = Mock()
        self.app.progress = Mock()
        self.app._set_busy(True, "Loading new data")
        self.app._poll_results()
        self.app._draw_box.assert_not_called()
        self.assertTrue(self.app.busy)
        self.assertEqual(self.app.status.get(), "Loading new data")

    def test_render_failure_does_not_stop_queue_polling(self):
        request_id = self.app._invalidate_plot_requests()
        self.worker(request_id, self.raw)
        self.app._draw_box.side_effect = ValueError("Invalid scale")
        with patch("defect_worse_ui.messagebox.showerror") as error:
            self.app._poll_results()
            error.assert_called_once()
        self.app.after.assert_called_with(150, self.app._poll_results)

    def test_each_trend_kind_passes_through_the_request_gate(self):
        request_id = self.app._invalidate_plot_requests()
        for kind in ("trend", "trend_all_chambers", "trend_sequence_by_tool"):
            with self.subTest(kind=kind):
                handler = getattr(self.app, "_draw_" + kind)
                self.app._apply_plot_result((request_id - 1, kind, ("old",)))
                handler.assert_not_called()
                self.app._apply_plot_result((request_id, kind, ("new",)))
                handler.assert_called_once_with("new")


if __name__ == "__main__":
    unittest.main()
