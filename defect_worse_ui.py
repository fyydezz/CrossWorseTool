from __future__ import annotations

import queue
import random
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import is_color_like, to_hex

from defect_worse_tool import (
    DEFAULT_SHEET_NAME,
    STEP_ONLY_STAGE_ID,
    SpecialProcessRules,
    add_grouping_columns,
    apply_process_aggregation,
    apply_special_process_rules,
    build_worse_tool_result,
    detect_defect_columns,
    handle_outliers_for_defect,
    normalize_outlier_handling,
    parse_defect_columns,
    parse_special_process_rules,
    normalize_process_aggregation,
    PROCESS_AGGREGATION_STAGE_STEP,
    PROCESS_AGGREGATION_STEP,
    DATA_WINDOW_ALL,
    DATA_WINDOW_14D,
    DATA_WINDOW_7D,
    OUTLIER_HANDLING_CAP,
    OUTLIER_HANDLING_FILTER,
    BSL_SOURCE_CALCULATED_MEAN,
    BSL_SOURCE_FILE,
    BSL_SOURCE_RECENT_MEAN,
    GOLDEN_COLUMNS,
    normalize_bsl_source,
    read_table,
    filter_by_recent_scan_time,
    validate_required_columns,
    write_result_to_excel,
)
from ppt_integration import PPTGenerationContext, run_ppt_generation
from chart_view import ChartViewMixin

NAMED_COLORS = {
    "红色 / Red": "#D32F2F", "黄色 / Yellow": "#FBC02D",
    "蓝色 / Blue": "#1565C0", "绿色 / Green": "#2E7D32",
    "橙色 / Orange": "#EF6C00", "紫色 / Purple": "#7B1FA2",
    "粉色 / Pink": "#D81B60", "青色 / Cyan": "#0097A7",
    "黑色 / Black": "#000000", "灰色 / Gray": "#757575",
}


DATA_FILE_TYPES = [
    ("Data files", "*.csv *.xlsx *.xlsm *.xls"),
    ("All files", "*.*"),
]

STEP_ONLY_PREFIX = "Step-only | Step_ID="
PROCESS_AGGREGATION_LABELS = {
    "Stage_ID + Step_ID": PROCESS_AGGREGATION_STAGE_STEP,
    "Step_ID only": PROCESS_AGGREGATION_STEP,
}
DATA_WINDOW_LABELS = {
    "All data": DATA_WINDOW_ALL,
    "Latest 2 weeks": DATA_WINDOW_14D,
    "Latest 1 week": DATA_WINDOW_7D,
}
DATA_WINDOW_VALUE_LABELS = {value: label for label, value in DATA_WINDOW_LABELS.items()}
OUTLIER_HANDLING_LABELS = {
    "Remove values above mean + N*sigma": OUTLIER_HANDLING_FILTER,
    "Cap values at mean + N*sigma": OUTLIER_HANDLING_CAP,
}
BSL_SOURCE_LABELS = {
    "Input BSL file": BSL_SOURCE_FILE,
    "Latest 2 weeks mean": BSL_SOURCE_RECENT_MEAN,
    "Calculated defect mean (after outlier handling)": BSL_SOURCE_CALCULATED_MEAN,
}
CHART_GROUP_MODE_CHAMBER = "By Chamber"
CHART_GROUP_MODE_EQUIPMENT = "By Equipment ID"
CHART_GROUP_MODES = (CHART_GROUP_MODE_CHAMBER, CHART_GROUP_MODE_EQUIPMENT)
CHART_TYPE_BOX = "Box chart by selected group"
CHART_TYPE_TREND = "Trend overlay equal point spacing"
CHART_TYPE_ALL_GROUPS = "Trend all tools equal point spacing"
CHART_TYPE_SEQUENCE = "Sequential trend by selected group"


def prepare_trend_data(df: pd.DataFrame, defect: str, time_col: str) -> pd.DataFrame:
    trend = df.copy()
    trend["Selected_Time"] = pd.to_datetime(trend[time_col], errors="coerce")
    invalid_time_count = int(trend["Selected_Time"].isna().sum())
    if invalid_time_count:
        raise ValueError(
            "{} row(s) have an invalid {}. Trend drawing stopped to avoid silently omitting data.".format(
                invalid_time_count,
                time_col,
            )
        )
    trend[defect] = pd.to_numeric(trend[defect], errors="coerce")
    invalid_value_count = int(trend[defect].isna().sum())
    if invalid_value_count:
        raise ValueError(
            "{} row(s) have a non-numeric or blank value for {}. Trend drawing stopped to avoid silently omitting data.".format(
                invalid_value_count,
                defect,
            )
        )
    trend["_Trend_Row_Order"] = list(range(len(trend)))
    trend = trend.sort_values(
        ["Chart_Group", "Selected_Time", "_Trend_Row_Order"],
        kind="mergesort",
    ).drop(columns=["_Trend_Row_Order"])
    return trend.reset_index(drop=True)


def add_equal_spacing_index(trend: pd.DataFrame) -> pd.DataFrame:
    spaced = trend.copy()
    spaced = spaced.sort_values(["Chart_Group", "Selected_Time"], kind="mergesort")
    spaced["Observation_Index"] = spaced.groupby("Chart_Group", sort=False, dropna=False).cumcount() + 1
    return spaced


def sample_tick_labels(
    positions: Sequence[int],
    labels: Sequence[str],
    max_ticks: int = 12,
) -> Tuple[List[int], List[str]]:
    if len(positions) != len(labels):
        raise ValueError("Tick positions and labels must have the same length.")
    if len(positions) == 0:
        return [], []
    limit = max(2, int(max_ticks))
    if len(positions) <= limit:
        return list(positions), list(labels)

    last_index = len(positions) - 1
    selected_indexes = sorted(
        {
            int(round(step * last_index / float(limit - 1)))
            for step in range(limit)
        }
    )
    return (
        [int(positions[index]) for index in selected_indexes],
        [str(labels[index]) for index in selected_indexes],
    )


def rank_worse_results(result: pd.DataFrame) -> pd.DataFrame:
    ranked = result.copy()
    if ranked.empty:
        ranked["Priority Score"] = pd.Series(dtype=float)
        return ranked
    mean = pd.to_numeric(ranked["Mean_Count"], errors="coerce").fillna(0)
    bsl = pd.to_numeric(ranked["BSL count"], errors="coerce")
    ratio = mean / bsl.where(bsl > 0)
    ratio = ratio.mask((bsl == 0) & (mean > 0), float("inf")).fillna(0)
    count = pd.to_numeric(ranked["Wafer_Count"], errors="coerce").fillna(0)
    ranked["Priority Score"] = 100 * (0.7 * ratio.rank(pct=True) + 0.3 * count.rank(pct=True))
    return ranked.sort_values("Priority Score", ascending=False, kind="mergesort")


def build_equal_spacing_time_ticks(
    spaced_trend: pd.DataFrame,
    max_ticks: int = 12,
    reference_tool: Optional[str] = None,
) -> Tuple[List[int], List[str]]:
    if reference_tool is None and not spaced_trend.empty:
        reference_tool = spaced_trend.groupby("Chart_Group", sort=False).size().idxmax()
    spaced_trend = spaced_trend.loc[spaced_trend["Chart_Group"] == reference_tool]
    timeline = (
        spaced_trend[["Observation_Index", "Selected_Time"]]
        .drop_duplicates(subset=["Observation_Index"])
        .sort_values("Observation_Index", kind="mergesort")
    )
    timestamps = [pd.Timestamp(value) for value in timeline["Selected_Time"]]
    show_clock = any(
        timestamp.hour or timestamp.minute or timestamp.second or timestamp.microsecond
        for timestamp in timestamps
    )
    time_format = "%Y-%m-%d\n%H:%M:%S" if any(
        timestamp.second or timestamp.microsecond for timestamp in timestamps
    ) else "%Y-%m-%d\n%H:%M"
    if not show_clock:
        time_format = "%Y-%m-%d"
    labels = [timestamp.strftime(time_format) for timestamp in timestamps]
    return sample_tick_labels(
        timeline["Observation_Index"].astype(int).tolist(),
        labels,
        max_ticks=max_ticks,
    )


class DefectWorseToolApp(ChartViewMixin, tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Defect Worse Tool Cross")
        self.geometry("1280x820")
        self.minsize(1060, 680)

        self.input_path = tk.StringVar()
        self.input_sheet = tk.StringVar()
        self.bsl_path = tk.StringVar()
        self.bsl_source = tk.StringVar(value="Input BSL file")
        self.output_path = tk.StringVar()
        self.output_sheet = tk.StringVar(value=DEFAULT_SHEET_NAME)
        self.ppt_output_path = tk.StringVar()
        self.ppt_template_path = tk.StringVar()
        self.ppt_input_image_path = tk.StringVar()
        self.defect_override = tk.StringVar()
        self.bsl_multiplier = tk.DoubleVar(value=1.5)
        self.min_wafers = tk.IntVar(value=5)
        self.outlier_sigma = tk.DoubleVar(value=3.0)
        self.outlier_handling = tk.StringVar(value="Remove values above mean + N*sigma")
        self.write_mode = tk.StringVar(value="append")
        self.process_aggregation = tk.StringVar(value="Stage_ID + Step_ID")
        self.analysis_data_window = tk.StringVar(value="Latest 2 weeks")

        self.worse_path = tk.StringVar()
        self.defect_type = tk.StringVar()
        self.process_stage = tk.StringVar()
        self.time_column = tk.StringVar(value="Scan_Time")
        self.chart_type = tk.StringVar(value=CHART_TYPE_BOX)
        self.chart_data_window = tk.StringVar(value="Latest 2 weeks")
        self.chart_group_mode = tk.StringVar(value=CHART_GROUP_MODE_CHAMBER)
        self.special_step_rules = tk.StringVar()
        self.line_width = tk.DoubleVar(value=1.8)
        self.marker_size = tk.DoubleVar(value=4.0)
        self.color_scheme = tk.StringVar(value="Distinct")
        self.custom_color = tk.StringVar(value="#1565C0")
        self.box_line_width = tk.DoubleVar(value=1.2)
        self.box_label_font_size = tk.DoubleVar(value=0.0)
        self.show_box_count = tk.BooleanVar(value=True)
        self.show_box_median = tk.BooleanVar(value=True)
        self.show_box_mean = tk.BooleanVar(value=True)
        self.show_bsl_line = tk.BooleanVar(value=True)
        self.show_threshold_line = tk.BooleanVar(value=True)
        self.show_golden_line = tk.BooleanVar(value=True)
        self.y_min = tk.StringVar()
        self.y_max = tk.StringVar()
        self.selected_chart_item = tk.StringVar(value="No chart item selected")
        self.status = tk.StringVar(value="Select raw data and configure the BSL source to start.")

        self.raw_df: Optional[pd.DataFrame] = None
        self.last_result: Optional[pd.DataFrame] = None
        self.all_columns: List[str] = []
        self.defect_columns: List[str] = []
        self.stage_values: List[str] = []
        self.result_queue: queue.Queue = queue.Queue()
        self._plot_request_id = 0
        self.busy = False
        self.chart_style_window: Optional[tk.Toplevel] = None
        self.selected_chart_artist = None
        self.chart_artist_registry: Dict[object, Dict[str, object]] = {}
        self.artist_style_overrides: Dict[Tuple[str, str], Dict[str, object]] = {}

        self._configure_style()
        self._build_ui()
        self.bsl_source.trace_add("write", lambda *_: self._sync_bsl_source_state())
        self.special_step_rules.trace_add("write", lambda *_: self._refresh_process_stage_options())
        self.process_aggregation.trace_add("write", lambda *_: self._refresh_process_stage_options())
        self._poll_job = self.after(150, self._poll_results)

    def destroy(self) -> None:
        for name in ("_poll_job", "_chart_resize_job"):
            job = self.__dict__.get(name)
            if job is not None:
                self.after_cancel(job)
        super().destroy()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        self.configure(background="#F1EFE9")
        style.configure("TFrame", background="#F1EFE9")
        style.configure("Card.TFrame", background="#FCFBF7")
        style.configure("Toolbar.TFrame", background="#E9E5DC")
        style.configure("TLabel", background="#F1EFE9", foreground="#25343C", font=("Segoe UI", 9))
        style.configure("Card.TLabel", background="#FCFBF7", foreground="#25343C")
        style.configure("Toolbar.TLabel", background="#E9E5DC", foreground="#465760")
        style.configure("Title.TLabel", font=("Bahnschrift SemiBold", 18), foreground="#173642")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 9), foreground="#65727A")
        style.configure(
            "Section.TLabel",
            background="#FCFBF7",
            foreground="#A54F32",
            font=("Bahnschrift SemiBold", 9),
        )
        style.configure(
            "Accent.TButton",
            font=("Segoe UI Semibold", 10),
            foreground="#FFFFFF",
            background="#176F69",
            padding=(12, 8),
        )
        style.map("Accent.TButton", background=[("active", "#125A56"), ("disabled", "#9DB5B2")])
        style.configure("Quiet.TButton", padding=(10, 7))
        style.configure("TNotebook", background="#F1EFE9", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(20, 9), font=("Segoe UI Semibold", 10))
        style.map("TNotebook.Tab", background=[("selected", "#FCFBF7")], foreground=[("selected", "#173642")])
        style.configure("Treeview", rowheight=25, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9))
        style.configure("TLabelframe", background="#FCFBF7", bordercolor="#D8D3C8")
        style.configure("TLabelframe.Label", background="#FCFBF7", foreground="#173642", font=("Segoe UI Semibold", 9))

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(20, 14, 20, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Defect Worse Tool Cross", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Run the screening workflow and inspect process-stage charts in one place.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Label(header, text="ANALYSIS WORKBENCH", style="Section.TLabel").grid(
            row=0, column=1, rowspan=2, sticky="e"
        )

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=14, pady=(2, 8))
        self.run_tab = ttk.Frame(self.notebook, padding=10)
        self.chart_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.run_tab, text="Run Worse Tool")
        self.notebook.add(self.chart_tab, text="Charts")

        self._build_run_tab()
        self._build_chart_tab()

        footer = ttk.Frame(self, padding=(18, 4, 18, 10))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status).grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=180)
        self.progress.grid(row=0, column=1, sticky="e")

    def _build_run_tab(self) -> None:
        self.run_tab.columnconfigure(0, weight=1)
        self.run_tab.rowconfigure(1, weight=1)

        controls = ttk.Frame(self.run_tab, style="Card.TFrame", padding=14)
        controls.grid(row=0, column=0, sticky="ew")
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(4, weight=1)

        self._file_row(controls, 0, "Raw defect data", self.input_path, self.browse_raw)
        self.bsl_entry, self.bsl_browse_button = self._file_row(
            controls, 1, "BSL file", self.bsl_path, self.browse_bsl
        )
        self._file_row(controls, 2, "Output Excel", self.output_path, self.browse_output)

        ttk.Label(controls, text="Input sheet", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=(10, 2))
        ttk.Entry(controls, textvariable=self.input_sheet, width=18).grid(row=4, column=0, sticky="ew", padx=(0, 10))
        ttk.Label(controls, text="Output sheet", style="Card.TLabel").grid(row=3, column=1, sticky="w", pady=(10, 2))
        ttk.Entry(controls, textvariable=self.output_sheet, width=18).grid(row=4, column=1, sticky="ew", padx=(0, 14))
        ttk.Label(controls, text="BSL multiplier", style="Card.TLabel").grid(row=3, column=2, sticky="w", pady=(10, 2))
        ttk.Spinbox(
            controls, from_=0.1, to=20.0, increment=0.1, textvariable=self.bsl_multiplier, width=10
        ).grid(row=4, column=2, sticky="ew", padx=(0, 10))
        ttk.Label(controls, text="Minimum wafers", style="Card.TLabel").grid(row=3, column=3, sticky="w", pady=(10, 2))
        ttk.Spinbox(controls, from_=1, to=10000, increment=1, textvariable=self.min_wafers, width=10).grid(
            row=4, column=3, sticky="ew", padx=(0, 10)
        )
        ttk.Label(controls, text="Outlier sigma", style="Card.TLabel").grid(row=3, column=4, sticky="w", pady=(10, 2))
        ttk.Spinbox(
            controls, from_=0.1, to=20.0, increment=0.1, textvariable=self.outlier_sigma, width=10
        ).grid(row=4, column=4, sticky="ew")

        ttk.Label(controls, text="Process aggregation", style="Card.TLabel").grid(
            row=5, column=0, sticky="w", pady=(10, 2)
        )
        ttk.Combobox(
            controls,
            textvariable=self.process_aggregation,
            values=list(PROCESS_AGGREGATION_LABELS.keys()),
            state="readonly",
            width=18,
        ).grid(row=6, column=0, sticky="ew", padx=(0, 10))

        ttk.Label(controls, text="Analysis data window", style="Card.TLabel").grid(
            row=5, column=1, sticky="w", pady=(10, 2)
        )
        ttk.Combobox(
            controls,
            textvariable=self.analysis_data_window,
            values=list(DATA_WINDOW_LABELS.keys()),
            state="readonly",
            width=18,
        ).grid(row=6, column=1, sticky="ew", padx=(0, 10))

        ttk.Label(
            controls,
            text="Defect columns (comma-separated; leave blank for auto-detection)",
            style="Card.TLabel",
        ).grid(row=5, column=2, columnspan=2, sticky="w", pady=(10, 2))
        ttk.Entry(controls, textvariable=self.defect_override).grid(
            row=6, column=2, columnspan=2, sticky="ew", padx=(0, 12)
        )
        mode_frame = ttk.Frame(controls, style="Card.TFrame")
        mode_frame.grid(row=5, column=4, rowspan=2, sticky="nsew")
        ttk.Label(mode_frame, text="Write mode", style="Card.TLabel").pack(anchor="w")
        write_options = ttk.Frame(mode_frame, style="Card.TFrame")
        write_options.pack(anchor="w", fill="x", pady=(2, 4))
        ttk.Radiobutton(write_options, text="Append", variable=self.write_mode, value="append").pack(side="left")
        ttk.Radiobutton(
            write_options,
            text="Replace sheet",
            variable=self.write_mode,
            value="replace",
        ).pack(side="left", padx=(8, 0))
        ttk.Label(mode_frame, text="Outlier handling", style="Card.TLabel").pack(anchor="w")
        ttk.Combobox(
            mode_frame,
            textvariable=self.outlier_handling,
            values=list(OUTLIER_HANDLING_LABELS.keys()),
            state="readonly",
            width=30,
        ).pack(anchor="w", fill="x", pady=(2, 0))
        ttk.Label(mode_frame, text="BSL source", style="Card.TLabel").pack(anchor="w", pady=(6, 0))
        ttk.Combobox(
            mode_frame,
            textvariable=self.bsl_source,
            values=list(BSL_SOURCE_LABELS.keys()),
            state="readonly",
            width=30,
        ).pack(anchor="w", fill="x", pady=(2, 0))
        self._sync_bsl_source_state()

        ttk.Label(
            controls,
            text="Special process rules for analysis/chart (Defect: STAGE_STEP or STEP)",
            style="Card.TLabel",
        ).grid(row=7, column=0, columnspan=5, sticky="w", pady=(10, 2))
        ttk.Entry(controls, textvariable=self.special_step_rules).grid(
            row=8, column=0, columnspan=5, sticky="ew"
        )
        ttk.Label(
            controls,
            text="Example: Defect Type1: STG01_STEP10, STG02_STEP10; Defect Type2: STEP30",
            style="Subtitle.TLabel",
        ).grid(row=9, column=0, columnspan=5, sticky="w", pady=(2, 0))

        self._file_row(controls, 10, "PPT output path", self.ppt_output_path, self.browse_ppt_output)
        self._file_row(controls, 11, "PPT template", self.ppt_template_path, self.browse_ppt_template)
        self._file_row(
            controls,
            12,
            "Chart export folder",
            self.ppt_input_image_path,
            self.browse_ppt_image,
        )

        action_frame = ttk.Frame(controls, style="Card.TFrame")
        action_frame.grid(row=13, column=0, columnspan=5, sticky="ew", pady=(14, 0))
        action_frame.columnconfigure(0, weight=1)
        self.run_button = ttk.Button(
            action_frame,
            text="Run Worse Tool",
            style="Accent.TButton",
            command=self.start_analysis,
        )
        self.run_button.grid(row=0, column=0, sticky="ew")
        ttk.Button(action_frame, text="Load Data Only", command=self.start_load_raw).grid(
            row=0, column=1, padx=(10, 0)
        )
        ttk.Button(action_frame, text="Open Result in Charts", command=self.open_result_in_charts).grid(
            row=0, column=2, padx=(8, 0)
        )
        self.ppt_button = ttk.Button(
            action_frame,
            text="Generate Worse Tool PPT",
            command=self.start_ppt_generation,
        )
        self.ppt_button.grid(row=0, column=3, padx=(8, 0))

        result_card = ttk.Frame(self.run_tab, style="Card.TFrame", padding=12)
        result_card.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        result_card.columnconfigure(0, weight=1)
        result_card.rowconfigure(1, weight=1)
        ttk.Label(result_card, text="Worse-tool result preview", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        columns = (
            "Priority Score",
            "Defect type",
            "BSL count",
            "BSL Source",
            "Stage_ID",
            "Step_ID",
            "Equipment ID",
            "Chamber ID",
            "Mean_Count",
            "Median_Count",
            "Wafer_Count",
            *GOLDEN_COLUMNS,
            "Outlier Handling",
            "Recent Trimmed BSL",
            "Data Window",
            "Trigger",
        )
        self.result_tree = ttk.Treeview(result_card, columns=columns, show="headings")
        for column in columns:
            self.result_tree.heading(column, text=column)
            width = 110
            if column in {"Defect type", "Equipment ID"}:
                width = 145
            self.result_tree.column(column, width=width, minwidth=75, anchor="center")
        self.result_tree.grid(row=1, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(result_card, orient="vertical", command=self.result_tree.yview)
        x_scroll = ttk.Scrollbar(result_card, orient="horizontal", command=self.result_tree.xview)
        self.result_tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        y_scroll.grid(row=1, column=1, sticky="ns")
        x_scroll.grid(row=2, column=0, sticky="ew")

    def _file_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command,
    ) -> Tuple[ttk.Entry, ttk.Button]:
        ttk.Label(parent, text=label, style="Card.TLabel", width=17).grid(
            row=row, column=0, sticky="w", pady=3
        )
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, columnspan=3, sticky="ew", padx=(0, 8), pady=3)
        button = ttk.Button(parent, text="Browse", command=command)
        button.grid(row=row, column=4, sticky="ew", pady=3)
        return entry, button

    def _sync_bsl_source_state(self) -> None:
        if not hasattr(self, "bsl_entry"):
            return
        state = "normal" if self._selected_bsl_source() == BSL_SOURCE_FILE else "disabled"
        self.bsl_entry.configure(state=state)
        self.bsl_browse_button.configure(state=state)

    def _build_chart_tab(self) -> None:
        self.chart_tab.columnconfigure(1, weight=1)
        self.chart_tab.rowconfigure(0, weight=1)

        panel_canvas = tk.Canvas(self.chart_tab, width=330, background="#FCFBF7", highlightthickness=0)
        panel_canvas.grid(row=0, column=0, sticky="ns")
        panel_scroll = ttk.Scrollbar(self.chart_tab, orient="vertical", command=panel_canvas.yview)
        panel_scroll.grid(row=0, column=0, sticky="nse")
        panel_canvas.configure(yscrollcommand=panel_scroll.set)

        panel = ttk.Frame(panel_canvas, style="Card.TFrame", padding=12)
        panel_window = panel_canvas.create_window((0, 0), window=panel, anchor="nw")
        panel.bind(
            "<Configure>",
            lambda _event: panel_canvas.configure(scrollregion=panel_canvas.bbox("all")),
        )
        panel_canvas.bind(
            "<Configure>",
            lambda event: panel_canvas.itemconfigure(panel_window, width=event.width),
        )
        panel_canvas.bind_all(
            "<MouseWheel>",
            lambda event: panel_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"),
        )
        panel.columnconfigure(0, weight=1)

        ttk.Label(panel, text="01  DATA SOURCE", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(panel, text="Raw defect data", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(panel, textvariable=self.input_path, width=40).grid(row=2, column=0, sticky="ew", pady=(2, 4))
        ttk.Button(panel, text="Browse / Load Raw Data", command=self.browse_raw).grid(row=3, column=0, sticky="ew")

        ttk.Label(panel, text="Worse-tool result (optional)", style="Card.TLabel").grid(
            row=4, column=0, sticky="w", pady=(10, 0)
        )
        ttk.Entry(panel, textvariable=self.worse_path, width=40).grid(row=5, column=0, sticky="ew", pady=(2, 4))
        ttk.Button(panel, text="Browse Result", command=self.browse_worse).grid(row=6, column=0, sticky="ew")

        ttk.Separator(panel).grid(row=7, column=0, sticky="ew", pady=14)
        ttk.Label(panel, text="02  VIEW", style="Section.TLabel").grid(row=8, column=0, sticky="w")
        ttk.Label(panel, text="Defect type", style="Card.TLabel").grid(row=9, column=0, sticky="w", pady=(8, 0))
        self.defect_combo = ttk.Combobox(panel, textvariable=self.defect_type, state="readonly", width=38)
        self.defect_combo.grid(row=10, column=0, sticky="ew", pady=(2, 7))
        self.defect_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_process_stage_options())

        ttk.Label(panel, text="Process stage", style="Card.TLabel").grid(row=11, column=0, sticky="w")
        self.stage_combo = ttk.Combobox(panel, textvariable=self.process_stage, state="readonly", width=38)
        self.stage_combo.grid(row=12, column=0, sticky="ew", pady=(2, 7))

        ttk.Label(panel, text="Chart grouping", style="Card.TLabel").grid(row=13, column=0, sticky="w")
        ttk.Combobox(
            panel,
            textvariable=self.chart_group_mode,
            values=CHART_GROUP_MODES,
            state="readonly",
            width=38,
        ).grid(row=14, column=0, sticky="ew", pady=(2, 7))

        ttk.Label(panel, text="Chart type", style="Card.TLabel").grid(row=15, column=0, sticky="w")
        ttk.Combobox(
            panel,
            textvariable=self.chart_type,
            values=[CHART_TYPE_BOX, CHART_TYPE_TREND, CHART_TYPE_ALL_GROUPS, CHART_TYPE_SEQUENCE],
            state="readonly",
            width=38,
        ).grid(row=16, column=0, sticky="ew", pady=(2, 7))

        ttk.Separator(panel).grid(row=17, column=0, sticky="ew", pady=14)
        ttk.Label(panel, text="03  DATA PREPARATION", style="Section.TLabel").grid(row=18, column=0, sticky="w")
        ttk.Label(panel, text="Time column", style="Card.TLabel").grid(row=19, column=0, sticky="w", pady=(8, 0))
        self.time_combo = ttk.Combobox(panel, textvariable=self.time_column, width=38)
        self.time_combo.grid(row=20, column=0, sticky="ew", pady=(2, 7))

        ttk.Label(panel, text="Chart data window", style="Card.TLabel").grid(row=21, column=0, sticky="w")
        ttk.Combobox(
            panel,
            textvariable=self.chart_data_window,
            values=list(DATA_WINDOW_LABELS.keys()),
            state="readonly",
            width=38,
        ).grid(row=22, column=0, sticky="ew", pady=(2, 7))

        ttk.Label(panel, text="Outlier handling", style="Card.TLabel").grid(row=23, column=0, sticky="w")
        ttk.Combobox(
            panel,
            textvariable=self.outlier_handling,
            values=list(OUTLIER_HANDLING_LABELS.keys()),
            state="readonly",
            width=38,
        ).grid(row=24, column=0, sticky="ew", pady=(2, 7))

        ttk.Label(panel, text="Special step-only rules", style="Card.TLabel").grid(row=25, column=0, sticky="w")
        ttk.Entry(panel, textvariable=self.special_step_rules, width=40).grid(
            row=26, column=0, sticky="ew", pady=(2, 4)
        )
        ttk.Label(
            panel,
            text="Example: Defect Type1: STEP10, STEP20; Defect Type2: STEP30",
            style="Subtitle.TLabel",
            wraplength=280,
        ).grid(row=27, column=0, sticky="w", pady=(0, 10))

        ttk.Button(panel, text="Plot Chart", style="Accent.TButton", command=self.start_plot).grid(
            row=28, column=0, sticky="ew", pady=(2, 6)
        )
        ttk.Button(panel, text="Chart Style...", style="Quiet.TButton", command=self.open_chart_style_dialog).grid(
            row=29, column=0, sticky="ew"
        )

        chart_frame = ttk.Frame(self.chart_tab, style="Card.TFrame", padding=8)
        chart_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        chart_frame.columnconfigure(0, weight=1)
        chart_frame.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(chart_frame, style="Toolbar.TFrame", padding=(10, 7))
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.columnconfigure(0, weight=1)
        ttk.Label(toolbar, textvariable=self.selected_chart_item, style="Toolbar.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(toolbar, text="Edit Selected", command=self.edit_selected_chart_item).grid(
            row=0, column=1, padx=(8, 0)
        )
        ttk.Button(toolbar, text="Save PNG", command=self.save_png).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(toolbar, text="Tool Details", command=self.open_tool_details).grid(row=0, column=3, padx=(8, 0))
        ttk.Button(toolbar, text="Clear highlight", command=lambda: self.focus_tool(None)).grid(row=0, column=4)
        self.fig, self.ax = plt.subplots(figsize=(8.8, 5.8), dpi=110)
        self.ax.set_title("Load raw data to begin")
        self.ax.grid(True, color="#D7DEE8", linewidth=0.7, alpha=0.8)
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew")
        self.canvas.mpl_connect("pick_event", self._on_chart_pick)
        self.canvas.mpl_connect("motion_notify_event", self._on_chart_hover)
        self.canvas.mpl_connect("resize_event", self._on_chart_resize)

    def _on_chart_resize(self, event) -> None:
        if "_chart_request" not in self.__dict__:
            return
        pending = self.__dict__.get("_chart_resize_job")
        if pending is not None:
            self.after_cancel(pending)
        def redraw():
            self._chart_resize_job = None
            self._render_chart(*self._chart_request)
        self._chart_resize_job = self.after(250, redraw)

    def _spin_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable,
        from_value: float,
        to_value: float,
        increment: float,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(4 if row else 0, 0))
        ttk.Spinbox(
            parent,
            from_=from_value,
            to=to_value,
            increment=increment,
            textvariable=variable,
            width=8,
        ).grid(row=row, column=1, sticky="ew", padx=(6, 0), pady=(4 if row else 0, 0))

    def open_chart_style_dialog(self) -> None:
        if self.chart_style_window is not None and self.chart_style_window.winfo_exists():
            self.chart_style_window.lift()
            self.chart_style_window.focus_force()
            return

        window = tk.Toplevel(self)
        self.chart_style_window = window
        window.title("Chart Style")
        dialog_height = min(620, max(400, window.winfo_screenheight() - 140))
        window.geometry("450x{}".format(dialog_height))
        window.minsize(400, 360)
        window.resizable(True, True)
        window.transient(self)
        window.configure(background="#F1EFE9")
        window.protocol("WM_DELETE_WINDOW", self._close_chart_style_dialog)

        outer = ttk.Frame(window, style="Card.TFrame")
        outer.pack(fill="both", expand=True, padx=12, pady=12)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)
        style_canvas = tk.Canvas(
            outer,
            background="#FCFBF7",
            highlightthickness=0,
            borderwidth=0,
        )
        style_canvas.grid(row=0, column=0, sticky="nsew")
        style_scroll = ttk.Scrollbar(outer, orient="vertical", command=style_canvas.yview)
        style_scroll.grid(row=0, column=1, sticky="ns")
        style_canvas.configure(yscrollcommand=style_scroll.set)
        body = ttk.Frame(style_canvas, style="Card.TFrame", padding=18)
        body_window = style_canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind(
            "<Configure>",
            lambda _event: style_canvas.configure(scrollregion=style_canvas.bbox("all")),
        )
        style_canvas.bind(
            "<Configure>",
            lambda event: style_canvas.itemconfigure(body_window, width=event.width),
        )
        def scroll_style_dialog(event):
            style_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        window.bind("<MouseWheel>", scroll_style_dialog)
        body.columnconfigure(0, weight=1)

        ttk.Label(body, text="CHART STYLE", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text="Global defaults apply to the next redraw. Individual edits override them.",
            style="Card.TLabel",
            wraplength=370,
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))

        box_frame = ttk.LabelFrame(body, text="Box chart", padding=10)
        box_frame.grid(row=2, column=0, sticky="ew")
        box_frame.columnconfigure(1, weight=1)
        self._spin_row(box_frame, 0, "Outline width", self.box_line_width, 0.5, 8.0, 0.2)
        self._spin_row(box_frame, 1, "Label size (0 = Auto)", self.box_label_font_size, 0.0, 30.0, 0.5)
        annotation_frame = ttk.Frame(box_frame, style="Card.TFrame")
        annotation_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(annotation_frame, text="Show labels:", style="Card.TLabel").pack(side="left")
        ttk.Checkbutton(annotation_frame, text="Count", variable=self.show_box_count).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(annotation_frame, text="Median", variable=self.show_box_median).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(annotation_frame, text="Mean", variable=self.show_box_mean).pack(side="left", padx=(8, 0))

        trend_frame = ttk.LabelFrame(body, text="Trend chart", padding=10)
        trend_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        trend_frame.columnconfigure(1, weight=1)
        self._spin_row(trend_frame, 0, "Line width", self.line_width, 0.5, 8.0, 0.2)
        self._spin_row(trend_frame, 1, "Marker size", self.marker_size, 0.0, 12.0, 0.5)
        ttk.Label(trend_frame, text="Line palette").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Combobox(
            trend_frame,
            textvariable=self.color_scheme,
            values=["Distinct", "Viridis", "Plasma", "Custom single"],
            state="readonly",
            width=18,
        ).grid(row=2, column=1, sticky="ew", padx=(6, 0), pady=(6, 0))
        ttk.Label(trend_frame, text="Custom color").grid(row=3, column=0, sticky="w", pady=(6, 0))
        color_row = ttk.Frame(trend_frame, style="Card.TFrame")
        color_row.grid(row=3, column=1, sticky="ew", padx=(6, 0), pady=(6, 0))
        self._color_controls(color_row, self.custom_color)
        ttk.Label(trend_frame, text="自选单色请将 Line palette 设为 Custom single",
                  wraplength=300).grid(row=4, column=0, columnspan=2, sticky="w", pady=(5, 0))

        axis_frame = ttk.LabelFrame(body, text="Y axis", padding=10)
        axis_frame.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        axis_frame.columnconfigure(1, weight=1)
        ttk.Label(axis_frame, text="Minimum").grid(row=0, column=0, sticky="w")
        ttk.Entry(axis_frame, textvariable=self.y_min).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Label(axis_frame, text="Maximum").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(axis_frame, textvariable=self.y_max).grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(6, 0))
        for row, (label, variable) in enumerate((("BSL reference", self.show_bsl_line),
                ("Worse threshold", self.show_threshold_line), ("Golden Mean", self.show_golden_line)), 2):
            ttk.Checkbutton(axis_frame, text=label, variable=variable).grid(row=row, column=0, columnspan=2, sticky="w")

        actions = ttk.Frame(body, style="Card.TFrame")
        actions.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        actions.columnconfigure(0, weight=1)
        ttk.Button(actions, text="Apply & Redraw", style="Accent.TButton", command=self._apply_chart_style).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(actions, text="Close", command=self._close_chart_style_dialog).grid(
            row=0, column=1, padx=(8, 0)
        )

    def _close_chart_style_dialog(self) -> None:
        if self.chart_style_window is not None:
            self.chart_style_window.destroy()
        self.chart_style_window = None

    def _apply_chart_style(self) -> None:
        try:
            self._get_y_limits()
            float(self.line_width.get())
            float(self.marker_size.get())
            float(self.box_line_width.get())
            box_label_font_size = float(self.box_label_font_size.get())
            if box_label_font_size < 0:
                raise ValueError("Box label size must be 0 (Auto) or a positive number.")
            if self.color_scheme.get() == "Custom single" and not is_color_like(self.custom_color.get().strip()):
                raise ValueError("Custom color is not a valid Matplotlib color.")
        except (tk.TclError, ValueError) as exc:
            messagebox.showwarning("Invalid chart style", str(exc), parent=self.chart_style_window)
            return
        if self.raw_df is not None and self.defect_type.get().strip() and self.process_stage.get().strip():
            self.start_plot()

    def _choose_color(self, variable: tk.StringVar) -> None:
        value = variable.get().strip()
        chosen = colorchooser.askcolor(color=to_hex(value) if is_color_like(value) else "#1565C0", parent=self)[1]
        if chosen:
            variable.set(chosen)

    def _color_controls(self, parent, variable) -> None:
        parent.columnconfigure(0, weight=1)
        name = tk.StringVar(parent)
        combo = ttk.Combobox(parent, textvariable=name, values=list(NAMED_COLORS), state="readonly", width=16)
        combo.grid(row=0, column=0, sticky="ew")
        swatch = tk.Label(parent, width=3, relief="solid", borderwidth=1)
        swatch.grid(row=0, column=1, padx=(5, 0))
        combo.bind("<<ComboboxSelected>>", lambda event: variable.set(NAMED_COLORS[name.get()]))
        ttk.Entry(parent, textvariable=variable, width=14).grid(row=1, column=0, sticky="ew", pady=(5, 0))
        ttk.Button(parent, text="自定义…", command=lambda: self._choose_color(variable)).grid(
            row=1, column=1, padx=(5, 0), pady=(5, 0))
        def refresh(*_):
            value = variable.get().strip()
            if is_color_like(value):
                value = to_hex(value)
                name.set(next((label for label, hex_value in NAMED_COLORS.items()
                               if hex_value.lower() == value.lower()), "自定义 / Custom"))
                swatch.configure(background=value)
        token = variable.trace_add("write", refresh)
        parent.bind("<Destroy>", lambda event: variable.trace_remove("write", token)
                    if event.widget == parent else None, add="+")
        refresh()

    def _on_chart_pick(self, event) -> None:
        metadata = self.chart_artist_registry.get(event.artist)
        if metadata is None:
            return
        self.selected_chart_artist = event.artist
        self.focus_tool(metadata["label"])
        self.selected_chart_item.set(
            "Selected {}: {}".format(metadata["kind"], metadata["label"])
        )
        self.status.set("Selected {}. Use Edit Selected to change its color or width.".format(metadata["label"]))

    def edit_selected_chart_item(self) -> None:
        artist = self.selected_chart_artist
        metadata = self.chart_artist_registry.get(artist)
        if metadata is None:
            messagebox.showinfo("Select a chart item", "Click a box or trend line first.")
            return

        color_var = tk.StringVar(value=str(metadata["color"]))
        width_var = tk.DoubleVar(value=float(metadata["linewidth"]))
        window = tk.Toplevel(self)
        window.title("Edit Selected Chart Item")
        window.geometry("450x320")
        window.resizable(False, False)
        window.transient(self)
        body = ttk.Frame(window, style="Card.TFrame", padding=18)
        body.pack(fill="both", expand=True, padx=12, pady=12)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="SELECTED ITEM", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text=str(metadata["label"]), style="Card.TLabel", wraplength=360).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 14)
        )
        ttk.Label(body, text="Color", style="Card.TLabel").grid(row=2, column=0, sticky="w")
        color_row = ttk.Frame(body, style="Card.TFrame")
        color_row.grid(row=2, column=1, sticky="ew", padx=(8, 0))
        self._color_controls(color_row, color_var)
        ttk.Label(body, text="Width", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(body, from_=0.5, to=12.0, increment=0.2, textvariable=width_var).grid(
            row=3, column=1, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

        def apply_selected_style() -> None:
            color = color_var.get().strip()
            try:
                width = float(width_var.get())
                if not is_color_like(color):
                    raise ValueError("Enter a valid Matplotlib color.")
                if width <= 0:
                    raise ValueError("Width must be greater than zero.")
            except (tk.TclError, ValueError) as exc:
                messagebox.showwarning("Invalid item style", str(exc), parent=window)
                return
            if metadata["kind"] == "box":
                artist.set_facecolor(color)
                artist.set_edgecolor(color)
            else:
                artist.set_color(color)
            artist.set_linewidth(width)
            metadata["color"] = color
            metadata["linewidth"] = width
            self.artist_style_overrides[(str(metadata["kind"]), str(metadata["key"]))] = {
                "color": color,
                "linewidth": width,
            }
            self._render_chart(*self._chart_request)
            self.status.set("Updated {} style.".format(metadata["label"]))
            window.destroy()

        ttk.Button(body, text="Apply", style="Accent.TButton", command=apply_selected_style).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(16, 0)
        )

    def browse_raw(self) -> None:
        path = filedialog.askopenfilename(filetypes=DATA_FILE_TYPES)
        if path:
            self.input_path.set(path)
            if not self.output_path.get().strip():
                source = Path(path)
                self.output_path.set(str(source.with_name(source.stem + "_worse_tool.xlsx")))
            self.start_load_raw()

    def browse_bsl(self) -> None:
        path = filedialog.askopenfilename(filetypes=DATA_FILE_TYPES)
        if path:
            self.bsl_path.set(path)

    def browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
        )
        if path:
            self.output_path.set(path)

    def browse_ppt_output(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".pptx",
            filetypes=[("PowerPoint presentation", "*.pptx")],
        )
        if path:
            self.ppt_output_path.set(path)

    def browse_ppt_template(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("PowerPoint presentation", "*.pptx *.pptm *.potx"), ("All files", "*.*")]
        )
        if path:
            self.ppt_template_path.set(path)

    def browse_ppt_image(self) -> None:
        path = filedialog.askdirectory(title="Select input image folder")
        if path:
            self.ppt_input_image_path.set(path)

    def browse_worse(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Excel files", "*.xlsx *.xlsm *.xls"), ("All files", "*.*")]
        )
        if path:
            self.worse_path.set(path)
            self._load_stage_filter_from_worse(path, self.output_sheet.get().strip() or None)

    def _set_busy(self, busy: bool, message: str) -> None:
        if busy:
            self._invalidate_plot_requests()
        self.busy = busy
        self.status.set(message)
        self.run_button.configure(state="disabled" if busy else "normal")
        self.ppt_button.configure(state="disabled" if busy else "normal")
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def start_load_raw(self) -> None:
        if self.busy:
            return
        path = self.input_path.get().strip()
        if not path:
            messagebox.showwarning("Missing file", "Please select a raw defect data file first.")
            return
        sheet = self.input_sheet.get().strip() or None
        process_aggregation = self._selected_process_aggregation()
        self._set_busy(True, "Loading raw data...")
        threading.Thread(target=self._load_raw_worker, args=(path, sheet, process_aggregation), daemon=True).start()

    def _load_raw_worker(self, path: str, sheet: Optional[str], process_aggregation: str) -> None:
        try:
            df = read_table(path, sheet_name=sheet)
            validate_required_columns(df)
            df = add_grouping_columns(df)
            defects = detect_defect_columns(df)
            stages = self._build_process_stage_values(df, process_aggregation)
            self.result_queue.put(("loaded", (df, defects, stages, list(df.columns))))
        except Exception as exc:
            self.result_queue.put(("error", exc))

    def start_analysis(self) -> None:
        if self.busy:
            return
        try:
            options = self._collect_analysis_options()
        except (ValueError, tk.TclError) as exc:
            messagebox.showwarning("Invalid settings", str(exc))
            return
        self._set_busy(True, "Running worse-tool analysis...")
        threading.Thread(target=self._analysis_worker, args=(options,), daemon=True).start()

    def _collect_analysis_options(self) -> dict:
        input_path = self.input_path.get().strip()
        bsl_path = self.bsl_path.get().strip()
        bsl_source = self._selected_bsl_source()
        output_path = self.output_path.get().strip()
        if not input_path or not Path(input_path).is_file():
            raise ValueError("Select a valid raw defect data file.")
        if bsl_source == BSL_SOURCE_FILE and (not bsl_path or not Path(bsl_path).is_file()):
            raise ValueError("Select a valid BSL file.")
        if not output_path:
            raise ValueError("Choose an output Excel path.")
        if Path(output_path).suffix.lower() != ".xlsx":
            raise ValueError("Output path must use the .xlsx extension.")
        multiplier = float(self.bsl_multiplier.get())
        min_wafers = int(self.min_wafers.get())
        sigma = float(self.outlier_sigma.get())
        if multiplier <= 0 or min_wafers < 1 or sigma <= 0:
            raise ValueError("BSL multiplier and outlier sigma must be positive; minimum wafers must be at least 1.")
        special_process_rules = parse_special_process_rules(self.special_step_rules.get())
        process_aggregation = self._selected_process_aggregation()
        data_window = self._selected_data_window(self.analysis_data_window)
        outlier_handling = self._selected_outlier_handling()
        output_sheet = self.output_sheet.get().strip()
        if not output_sheet:
            raise ValueError("Output sheet cannot be blank.")
        return {
            "input_path": input_path,
            "bsl_path": bsl_path,
            "bsl_source": bsl_source,
            "output_path": output_path,
            "input_sheet": self.input_sheet.get().strip() or None,
            "output_sheet": output_sheet,
            "defect_columns": parse_defect_columns(self.defect_override.get()),
            "bsl_multiplier": multiplier,
            "min_wafers": min_wafers,
            "outlier_sigma": sigma,
            "outlier_handling": outlier_handling,
            "special_process_rules": special_process_rules,
            "process_aggregation": process_aggregation,
            "data_window": data_window,
            "write_mode": self.write_mode.get(),
        }

    def _analysis_worker(self, options: dict) -> None:
        try:
            result = build_worse_tool_result(
                input_path=options["input_path"],
                bsl_path=options["bsl_path"],
                defect_columns=options["defect_columns"],
                input_sheet=options["input_sheet"],
                bsl_multiplier=options["bsl_multiplier"],
                min_wafers=options["min_wafers"],
                outlier_sigma=options["outlier_sigma"],
                outlier_handling=options["outlier_handling"],
                special_process_rules=options["special_process_rules"],
                process_aggregation=options["process_aggregation"],
                data_window=options["data_window"],
                bsl_source=options["bsl_source"],
            )
            output = write_result_to_excel(
                result,
                options["output_path"],
                sheet_name=options["output_sheet"],
                write_mode=options["write_mode"],
            )
            raw = read_table(options["input_path"], sheet_name=options["input_sheet"])
            validate_required_columns(raw)
            raw = add_grouping_columns(raw)
            defects = detect_defect_columns(raw, options["defect_columns"])
            stages = self._build_process_stage_values(raw, options["process_aggregation"])
            self.result_queue.put(
                (
                    "analysis_done",
                    (result, output, raw, defects, stages, list(raw.columns), options["data_window"]),
                )
            )
        except Exception as exc:
            self.result_queue.put(("error", exc))

    def _load_stage_filter_from_worse(self, path: str, sheet_name: Optional[str] = None) -> None:
        try:
            worse = pd.read_excel(path, sheet_name=sheet_name or 0)
            if "Stage_ID" in worse.columns and "Step_ID" in worse.columns:
                if (worse["Stage_ID"].astype(str).str.strip() == STEP_ONLY_STAGE_ID).any():
                    values = [
                        self._format_step_only_option(step)
                        for step in sorted(worse["Step_ID"].dropna().astype(str).str.strip().unique().tolist())
                    ]
                else:
                    values = (
                        worse["Stage_ID"].astype(str).str.strip()
                        + "_"
                        + worse["Step_ID"].astype(str).str.strip()
                    ).unique().tolist()
                if values:
                    self.stage_values = sorted(values)
                    self._refresh_process_stage_options()
                    self.status.set("Loaded process stages from the worse-tool result.")
        except Exception as exc:
            messagebox.showerror("Load result failed", str(exc))

    def open_result_in_charts(self) -> None:
        output = self.output_path.get().strip()
        if not output or not Path(output).exists():
            messagebox.showwarning("Missing result", "Run the analysis or select an existing result first.")
            return
        self.worse_path.set(output)
        self._load_stage_filter_from_worse(output, self.output_sheet.get().strip() or None)
        if self.raw_df is None:
            self.start_load_raw()
        self.notebook.select(self.chart_tab)

    def start_ppt_generation(self) -> None:
        if self.busy:
            return
        try:
            context = self._build_ppt_context()
        except (ValueError, tk.TclError) as exc:
            messagebox.showwarning("Invalid PPT settings", str(exc))
            return
        self._set_busy(True, "Running PPT generator...")
        threading.Thread(
            target=self._ppt_worker,
            args=(context,),
            daemon=True,
        ).start()

    def _build_ppt_context(self) -> PPTGenerationContext:
        ppt_output_path = self.ppt_output_path.get().strip()
        ppt_template_path = self.ppt_template_path.get().strip()
        input_image_path = self.ppt_input_image_path.get().strip()
        if not ppt_output_path:
            raise ValueError("Choose a PPT output path.")
        if Path(ppt_output_path).suffix.lower() != ".pptx":
            raise ValueError("PPT output path must use the .pptx extension.")
        if ppt_template_path and not Path(ppt_template_path).is_file():
            raise ValueError("Select a valid PPT template file.")
        self._collect_analysis_options()
        Path(ppt_output_path).parent.mkdir(parents=True, exist_ok=True)

        raw_path = self.input_path.get().strip()
        result_path = self.output_path.get().strip()
        return PPTGenerationContext(
            ppt_output_path=ppt_output_path,
            ppt_template_path=ppt_template_path,
            input_image_path=input_image_path,
            raw_data_path=raw_path,
            bsl_path=self.bsl_path.get().strip(),
            worse_result_path=result_path,
            input_sheet=self.input_sheet.get().strip() or None,
            result_sheet=self.output_sheet.get().strip() or DEFAULT_SHEET_NAME,
            defect_columns=parse_defect_columns(self.defect_override.get()),
            bsl_multiplier=float(self.bsl_multiplier.get()),
            min_wafers=int(self.min_wafers.get()),
            outlier_sigma=float(self.outlier_sigma.get()),
            selected_defect=self.defect_type.get().strip() or None,
            selected_process_stage=self.process_stage.get().strip() or None,
            bsl_source=self._selected_bsl_source(),
            data_window=self._selected_data_window(self.analysis_data_window),
            outlier_handling=self._selected_outlier_handling(),
            process_aggregation=self._selected_process_aggregation(),
            special_process_rules=self._parse_special_step_rules_for_ui(),
            chart_group_mode=self.chart_group_mode.get(),
            time_column=self.time_column.get(),
            show_bsl_line=self.show_bsl_line.get(),
            show_threshold_line=self.show_threshold_line.get(),
            show_golden_line=self.show_golden_line.get(),
        )

    def _ppt_worker(self, context: PPTGenerationContext) -> None:
        try:
            def log(message: str) -> None:
                print("[PPT] {}".format(message), flush=True)
                self.result_queue.put(("ppt_log", message))

            output = run_ppt_generation(
                context,
                log_callback=log,
            )
            output_path = Path(output)
            if not output_path.is_file():
                raise ValueError(
                    "PPT generator returned a path that does not exist: {}".format(output_path)
                )
            self.result_queue.put(("ppt_done", output_path))
        except Exception as exc:
            self.result_queue.put(("ppt_error", exc))

    def start_plot(self) -> None:
        if self.busy:
            messagebox.showinfo("Operation in progress", "Please wait for loading, analysis or PPT generation to finish.")
            return
        request_id = self._invalidate_plot_requests()
        if self.raw_df is None:
            messagebox.showwarning("Missing raw data", "Please load raw defect data first.")
            return
        defect = self.defect_type.get().strip()
        stage = self.process_stage.get().strip()
        if not defect or not stage:
            messagebox.showwarning("Missing selection", "Please select defect type and process stage.")
            return
        time_col = self.time_column.get().strip() or "Scan_Time"
        try:
            sigma = float(self.outlier_sigma.get())
            self._get_y_limits()
            special_rules = self._parse_special_step_rules_for_ui()
            process_aggregation = self._selected_process_aggregation()
            chart_data_window = self._selected_data_window(self.chart_data_window)
            outlier_handling = self._selected_outlier_handling()
            chart_group_mode = self.chart_group_mode.get().strip()
            if chart_group_mode not in CHART_GROUP_MODES:
                raise ValueError("Choose either By Chamber or By Equipment ID for chart grouping.")
            reference_options = dict(bsl_path=self.bsl_path.get().strip(), bsl_source=self._selected_bsl_source(),
                 data_window=self._selected_data_window(self.analysis_data_window),
                 bsl_multiplier=float(self.bsl_multiplier.get()), min_wafers=int(self.min_wafers.get()),
                 outlier_sigma=sigma, outlier_handling=outlier_handling,
                 special_process_rules=special_rules, process_aggregation=process_aggregation,
                 chart_group_mode=chart_group_mode)
            if reference_options["min_wafers"] < 1 or reference_options["bsl_multiplier"] < 0 or sigma < 0:
                raise ValueError("Minimum wafers must be positive; multiplier and sigma must be nonnegative.")
        except tk.TclError:
            messagebox.showwarning("Invalid setting", "Outlier sigma must be numeric.")
            return
        except ValueError as exc:
            messagebox.showwarning("Invalid chart settings", str(exc))
            return
        self.status.set("Preparing chart: {} | {} | {} | {}".format(
            defect, stage, chart_group_mode, chart_data_window))
        threading.Thread(
            target=self._plot_worker,
            args=(
                request_id,
                self.raw_df,
                defect,
                stage,
                self.chart_type.get(),
                time_col,
                sigma,
                special_rules,
                process_aggregation,
                chart_data_window,
                chart_group_mode,
                outlier_handling,
                reference_options,
            ),
            daemon=True,
        ).start()

    def _plot_worker(
        self,
        request_id: int,
        raw_data: pd.DataFrame,
        defect: str,
        stage: str,
        chart_type: str,
        time_col: str,
        sigma: float,
        special_rules: SpecialProcessRules,
        process_aggregation: str,
        chart_data_window: str,
        chart_group_mode: str,
        outlier_handling: str,
        reference_options: Optional[dict] = None,
    ) -> None:
        def send(kind, payload):
            self.result_queue.put(("plot_result", (request_id, kind, payload)))

        try:
            # Capture the dataset at submission; loading replaces self.raw_df.
            if time_col not in raw_data.columns:
                raise ValueError("Selected time column does not exist: {}".format(time_col))
            window_df = filter_by_recent_scan_time(raw_data, data_window=chart_data_window)
            df = handle_outliers_for_defect(
                window_df,
                defect,
                outlier_sigma=sigma,
                outlier_handling=outlier_handling,
            )
            filter_label, df = self._filter_chart_process(
                df,
                defect,
                stage,
                special_rules,
                process_aggregation,
            )
            df = self._filter_chart_group_mode(df, chart_group_mode)
            if df.empty:
                raise ValueError(
                    "No rows remain for this defect/process selection in chart mode '{}'.".format(
                        chart_group_mode
                    )
                )
            if chart_type == CHART_TYPE_BOX:
                from chart_context import annotate_chart_data
                if reference_options is not None:
                    annotate_chart_data(self, raw_data, df, defect, reference_options, chart_data_window)
                send("box", (defect, filter_label, df))
                return
            trend = prepare_trend_data(df, defect, time_col)
            if reference_options is not None:
                from chart_context import annotate_chart_data
                annotate_chart_data(self, raw_data, trend, defect, reference_options, chart_data_window)
            if trend.empty:
                raise ValueError("{} cannot be parsed for trend chart.".format(time_col))
            if chart_type == CHART_TYPE_ALL_GROUPS:
                kind = "trend_all_chambers"
            elif chart_type == CHART_TYPE_SEQUENCE:
                kind = "trend_sequence_by_tool"
            else:
                kind = "trend"
            send(kind, (defect, filter_label, time_col, trend))
        except Exception as exc:
            send("error", exc)

    def _invalidate_plot_requests(self) -> int:
        self._plot_request_id = self.__dict__.get("_plot_request_id", 0) + 1
        return self._plot_request_id

    def _apply_plot_result(self, result) -> None:
        request_id, kind, payload = result
        if request_id != self._plot_request_id:
            return
        try:
            if kind == "error":
                raise payload
            handlers = {"box": self._draw_box, "trend": self._draw_trend,
                        "trend_all_chambers": self._draw_trend_all_chambers,
                        "trend_sequence_by_tool": self._draw_trend_sequence_by_tool}
            handlers[kind](*payload)
        except Exception as exc:
            self.status.set("Chart failed. Check settings and plot again.")
            messagebox.showerror("Chart failed", str(exc))

    def _poll_results(self) -> None:
        try:
            while True:
                kind, payload = self.result_queue.get_nowait()
                if kind == "plot_result":
                    self._apply_plot_result(payload)
                elif kind == "error":
                    self._set_busy(False, "Operation failed.")
                    messagebox.showerror("Error", str(payload))
                elif kind == "ppt_error":
                    self._set_busy(False, "PPT generation failed.")
                    messagebox.showerror("PPT generation failed", str(payload))
                elif kind == "ppt_log":
                    self.status.set(str(payload))
                elif kind == "ppt_done":
                    self._set_busy(False, "PPT generated: {}".format(payload))
                    messagebox.showinfo("PPT generation complete", "Output:\n{}".format(payload))
                elif kind == "loaded":
                    self._apply_loaded_data(*payload)
                    self._set_busy(
                        False,
                        "Loaded {} rows, {} defect types, {} process stages.".format(
                            len(payload[0]), len(payload[1]), len(payload[2])
                        ),
                    )
                elif kind == "analysis_done":
                    result, output, df, defects, stages, columns, data_window = payload
                    self.last_result = result
                    self.worse_path.set(str(output))
                    self.chart_data_window.set(DATA_WINDOW_VALUE_LABELS[data_window])
                    self._apply_loaded_data(df, defects, stages, columns)
                    self._show_result_preview(result)
                    self._set_busy(
                        False,
                        "Completed: {} worse-tool row(s) written to {}.".format(len(result), output),
                    )
                    messagebox.showinfo(
                        "Analysis complete",
                        "Generated {} worse-tool row(s).\n\nOutput:\n{}".format(len(result), output),
                    )
        except queue.Empty:
            pass
        self._poll_job = self.after(150, self._poll_results)

    def _apply_loaded_data(
        self,
        df: pd.DataFrame,
        defects: Sequence[str],
        stages: Sequence[str],
        columns: Sequence[str],
    ) -> None:
        self._invalidate_plot_requests()
        self.raw_df = df
        self.all_columns = list(columns)
        self.defect_columns = list(defects)
        self.stage_values = list(stages)
        self.defect_combo["values"] = self.defect_columns
        self.time_combo["values"] = self.all_columns
        if self.defect_columns:
            self.defect_type.set(self.defect_columns[0])
        self._refresh_process_stage_options()
        if "Scan_Time" in self.all_columns:
            self.time_column.set("Scan_Time")

    def _parse_special_step_rules_for_ui(self) -> SpecialProcessRules:
        return parse_special_process_rules(self.special_step_rules.get())

    def _selected_process_aggregation(self) -> str:
        label = self.process_aggregation.get().strip()
        return normalize_process_aggregation(PROCESS_AGGREGATION_LABELS.get(label, label))

    def _selected_data_window(self, variable: tk.StringVar) -> str:
        label = variable.get().strip()
        return DATA_WINDOW_LABELS.get(label, label or DATA_WINDOW_ALL)

    def _selected_outlier_handling(self) -> str:
        label = self.outlier_handling.get().strip()
        return normalize_outlier_handling(OUTLIER_HANDLING_LABELS.get(label, label))

    def _selected_bsl_source(self) -> str:
        label = self.bsl_source.get().strip()
        return normalize_bsl_source(BSL_SOURCE_LABELS.get(label, label))

    def _build_process_stage_values(
        self,
        df: pd.DataFrame,
        process_aggregation: Optional[str] = None,
    ) -> List[str]:
        mode = normalize_process_aggregation(process_aggregation or PROCESS_AGGREGATION_STAGE_STEP)
        if mode == PROCESS_AGGREGATION_STEP:
            return [
                self._format_step_only_option(step)
                for step in sorted(df["Step_ID"].dropna().astype(str).str.strip().unique().tolist())
            ]
        return sorted(df["Process_Stage"].dropna().astype(str).unique().tolist())

    def _get_y_limits(self) -> Tuple[Optional[float], Optional[float]]:
        min_text = self.y_min.get().strip()
        max_text = self.y_max.get().strip()
        y_min = float(min_text) if min_text else None
        y_max = float(max_text) if max_text else None
        if y_min is not None and y_max is not None and y_min >= y_max:
            raise ValueError("Y min must be smaller than Y max.")
        return y_min, y_max

    def _apply_y_limits(self, ax) -> None:
        y_min, y_max = self._get_y_limits()
        if y_min is not None or y_max is not None:
            current_min, current_max = ax.get_ylim()
            ax.set_ylim(
                y_min if y_min is not None else current_min,
                y_max if y_max is not None else current_max,
            )

    def _refresh_process_stage_options(self) -> None:
        if not hasattr(self, "stage_combo"):
            return
        current = self.process_stage.get().strip()
        values = list(self.stage_values)
        try:
            rules = self._parse_special_step_rules_for_ui()
        except ValueError:
            rules = {}
        defect_key = self.defect_type.get().strip().casefold()
        if self._selected_process_aggregation() != PROCESS_AGGREGATION_STEP:
            special_steps = sorted(rules.get(defect_key, {}).keys())
            for value in [self._format_step_only_option(step) for step in special_steps]:
                if value not in values:
                    values.append(value)
        self.stage_combo["values"] = values
        if current in values:
            return
        if values:
            self.process_stage.set(values[0])
        else:
            self.process_stage.set("")

    def _format_step_only_option(self, step_id: str) -> str:
        return "{}{} (ignore Stage_ID)".format(STEP_ONLY_PREFIX, step_id)

    def _parse_step_only_option(self, selected: str) -> Optional[str]:
        if not selected.startswith(STEP_ONLY_PREFIX):
            return None
        value = selected[len(STEP_ONLY_PREFIX):]
        if " " in value:
            value = value.split(" ", 1)[0]
        return value.strip() or None

    def _filter_chart_process(
        self,
        df: pd.DataFrame,
        defect: str,
        selected_process: str,
        special_rules: SpecialProcessRules,
        process_aggregation: str,
    ) -> Tuple[str, pd.DataFrame]:
        adjusted = apply_special_process_rules(
            df,
            defect,
            special_process_rules=special_rules,
        )
        adjusted = apply_process_aggregation(adjusted, process_aggregation)
        step_only = self._parse_step_only_option(selected_process)
        if step_only:
            expected_stage = "{}{}".format(STEP_ONLY_PREFIX, step_only)
            filtered = adjusted.loc[
                adjusted["Process_Stage"].astype(str).str.strip() == expected_stage
            ].copy()
            if filtered.empty and normalize_process_aggregation(process_aggregation) != PROCESS_AGGREGATION_STEP:
                raise ValueError(
                    "Step-only process '{}' is not configured for defect '{}'.".format(step_only, defect)
                )
            label = "Step_ID={} (Stage ignored)".format(step_only)
            return label, filtered

        filtered = adjusted.loc[adjusted["Process_Stage"].astype(str) == selected_process].copy()
        return selected_process, filtered

    def _filter_chart_group_mode(self, df: pd.DataFrame, chart_group_mode: str) -> pd.DataFrame:
        if chart_group_mode == CHART_GROUP_MODE_CHAMBER:
            source_column = "Chamber_ID"
            group_type = "Chamber"
            missing_label = "(Missing Chamber)"
        elif chart_group_mode == CHART_GROUP_MODE_EQUIPMENT:
            source_column = "Equipment_ID"
            group_type = "Equipment ID"
            missing_label = "(Missing Equipment ID)"
        else:
            raise ValueError("Unsupported chart grouping mode: {}".format(chart_group_mode))
        group_values = df[source_column].fillna("").astype(str).str.strip()
        grouped = df.copy()
        grouped["Chart_Group"] = group_values.mask(group_values == "", missing_label)
        grouped["Chart_Group_Type"] = group_type
        return grouped

    def _show_result_preview(self, result: pd.DataFrame) -> None:
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        preview_columns = list(self.result_tree["columns"])
        for _, row in rank_worse_results(result).head(500).iterrows():
            values = []
            for column in preview_columns:
                value = row.get(column, "")
                if isinstance(value, float):
                    value = "{:.3f}".format(value)
                values.append(value)
            self.result_tree.insert("", "end", values=values)

    def _reset_chart_artists(self) -> None:
        self.chart_artist_registry = {}
        self.selected_chart_artist = None
        self.selected_chart_item.set("No chart item selected")

    def _register_chart_artist(
        self,
        artist,
        kind: str,
        key: str,
        label: str,
        color: object,
        linewidth: float,
    ) -> None:
        artist.set_picker(6 if kind == "line" else True)
        self.chart_artist_registry[artist] = {
            "kind": kind,
            "key": key,
            "label": label,
            "color": to_hex(color),
            "linewidth": float(linewidth),
        }

    def _artist_style(self, kind: str, key: str, color: object, linewidth: float) -> Tuple[object, float]:
        override = self.artist_style_overrides.get((kind, str(key)), {})
        return override.get("color", color), float(override.get("linewidth", linewidth))


    def _box_pixels_per_group(self, group_count: int, ax=None) -> float:
        if group_count <= 0:
            return 0.0
        figure_width = float(self.fig.get_figwidth()) * float(self.fig.dpi)
        axes_fraction = float(ax.get_position().width) if ax is not None else 1.0
        return figure_width * axes_fraction / float(group_count)

    @staticmethod
    def _box_rank_colors(group_count: int) -> List[object]:
        if group_count <= 0:
            return []
        return [
            plt.cm.coolwarm(1.0 - index / float(max(1, group_count - 1)))
            for index in range(group_count)
        ]

    def _box_stats_font_size(self, pixels_per_box: float) -> float:
        configured_size = float(self.box_label_font_size.get())
        if configured_size > 0:
            return configured_size
        if pixels_per_box >= 140:
            return 11.5
        if pixels_per_box >= 95:
            return 10.5
        if pixels_per_box >= 65:
            return 9.0
        return 8.0

    def _display_tool_label(self, part: pd.DataFrame, fallback: str) -> str:
        if part.empty:
            return fallback
        label = str(part.iloc[0].get("Chart_Group", "")).strip()
        return label or fallback

    def _chart_group_label(self, part: pd.DataFrame) -> str:
        if part.empty:
            return "Chart group"
        return str(part.iloc[0].get("Chart_Group_Type", "Chart group")).strip() or "Chart group"

    def _colors(self, count: int) -> List[object]:
        if count <= 0:
            return []
        scheme = self.color_scheme.get()
        if scheme == "Custom single":
            return [self.custom_color.get().strip() or "#1565C0"] * count
        if scheme == "Viridis":
            cmap = plt.cm.get_cmap("viridis", count)
            return [cmap(i) for i in range(count)]
        if scheme == "Plasma":
            cmap = plt.cm.get_cmap("plasma", count)
            return [cmap(i) for i in range(count)]
        base = list(plt.cm.tab20.colors) + list(plt.cm.tab20b.colors) + list(plt.cm.tab20c.colors)
        random.Random(73013 + count).shuffle(base)
        if count <= len(base):
            return base[:count]
        extra_count = count - len(base)
        extra = [plt.cm.hsv(i / float(max(1, extra_count))) for i in range(extra_count)]
        return base + extra

    def _jitter_positions(self, center: int, count: int) -> List[float]:
        if count <= 1:
            return [float(center)]
        width = 0.22
        return [center - width / 2.0 + width * i / float(count - 1) for i in range(count)]

    def save_png(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
        )
        if path:
            self.export_current_chart(path)
            self.status.set("Saved {}".format(path))


def main() -> None:
    app = DefectWorseToolApp()
    app.mainloop()


if __name__ == "__main__":
    main()
