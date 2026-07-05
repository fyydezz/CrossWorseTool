from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.ticker import MaxNLocator

from defect_worse_tool import (
    DEFAULT_SHEET_NAME,
    SPECIAL_STAGE_ID,
    SpecialProcessRules,
    add_grouping_columns,
    build_worse_tool_result,
    detect_defect_columns,
    filter_outliers_for_defect,
    parse_defect_columns,
    parse_special_process_rules,
    read_table,
    validate_required_columns,
    write_result_to_excel,
)
from ppt_integration import PPTGenerationContext, run_ppt_generation


DATA_FILE_TYPES = [
    ("Data files", "*.csv *.xlsx *.xlsm *.xls"),
    ("All files", "*.*"),
]

STEP_ONLY_PREFIX = "Step-only | Step_ID="


class DefectWorseToolApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Defect Worse Tool Cross")
        self.geometry("1280x820")
        self.minsize(1060, 680)

        self.input_path = tk.StringVar()
        self.input_sheet = tk.StringVar()
        self.bsl_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.output_sheet = tk.StringVar(value=DEFAULT_SHEET_NAME)
        self.defect_override = tk.StringVar()
        self.bsl_multiplier = tk.DoubleVar(value=1.5)
        self.min_wafers = tk.IntVar(value=5)
        self.outlier_sigma = tk.DoubleVar(value=3.0)
        self.write_mode = tk.StringVar(value="append")

        self.worse_path = tk.StringVar()
        self.defect_type = tk.StringVar()
        self.process_stage = tk.StringVar()
        self.time_column = tk.StringVar(value="Scan_Time")
        self.chart_type = tk.StringVar(value="Box chart by tool")
        self.special_step_rules = tk.StringVar()
        self.line_width = tk.DoubleVar(value=1.8)
        self.marker_size = tk.DoubleVar(value=4.0)
        self.color_scheme = tk.StringVar(value="Tableau")
        self.custom_color = tk.StringVar(value="#1565C0")
        self.y_min = tk.StringVar()
        self.y_max = tk.StringVar()
        self.status = tk.StringVar(value="Select raw data and a BSL file to start.")

        self.raw_df: Optional[pd.DataFrame] = None
        self.last_result: Optional[pd.DataFrame] = None
        self.all_columns: List[str] = []
        self.defect_columns: List[str] = []
        self.stage_values: List[str] = []
        self.result_queue: queue.Queue = queue.Queue()
        self.busy = False

        self._configure_style()
        self._build_ui()
        self.special_step_rules.trace_add("write", lambda *_: self._refresh_process_stage_options())
        self.after(150, self._poll_results)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        self.configure(background="#EEF2F6")
        style.configure("TFrame", background="#EEF2F6")
        style.configure("Card.TFrame", background="#FFFFFF")
        style.configure("TLabel", background="#EEF2F6", foreground="#263442")
        style.configure("Card.TLabel", background="#FFFFFF", foreground="#263442")
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 17), foreground="#123047")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 9), foreground="#5F7180")
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 10), padding=(12, 8))
        style.configure("TNotebook", background="#EEF2F6", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 8), font=("Segoe UI Semibold", 10))
        style.configure("Treeview", rowheight=25, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9))

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(18, 12, 18, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Defect Worse Tool Cross", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Run the screening workflow and inspect process-stage charts in one place.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

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
        self._file_row(controls, 1, "BSL file", self.bsl_path, self.browse_bsl)
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

        ttk.Label(
            controls,
            text="Defect columns (comma-separated; leave blank for auto-detection)",
            style="Card.TLabel",
        ).grid(row=5, column=0, columnspan=4, sticky="w", pady=(10, 2))
        ttk.Entry(controls, textvariable=self.defect_override).grid(
            row=6, column=0, columnspan=4, sticky="ew", padx=(0, 12)
        )
        mode_frame = ttk.Frame(controls, style="Card.TFrame")
        mode_frame.grid(row=5, column=4, rowspan=2, sticky="nsew")
        ttk.Label(mode_frame, text="Write mode", style="Card.TLabel").pack(anchor="w")
        ttk.Radiobutton(mode_frame, text="Append", variable=self.write_mode, value="append").pack(
            side="left", pady=(4, 0)
        )
        ttk.Radiobutton(mode_frame, text="Replace sheet", variable=self.write_mode, value="replace").pack(
            side="left", padx=(10, 0), pady=(4, 0)
        )

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

        action_frame = ttk.Frame(controls, style="Card.TFrame")
        action_frame.grid(row=10, column=0, columnspan=5, sticky="ew", pady=(14, 0))
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
            text="Run PPT Generator",
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
            "Defect type",
            "BSL count",
            "Stage_ID",
            "Step_ID",
            "Equipment ID",
            "Chamber ID",
            "Mean_Count",
            "Median_Count",
            "Wafer_Count",
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
    ) -> None:
        ttk.Label(parent, text=label, style="Card.TLabel", width=17).grid(
            row=row, column=0, sticky="w", pady=3
        )
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, columnspan=3, sticky="ew", padx=(0, 8), pady=3
        )
        ttk.Button(parent, text="Browse", command=command).grid(row=row, column=4, sticky="ew", pady=3)

    def _build_chart_tab(self) -> None:
        self.chart_tab.columnconfigure(1, weight=1)
        self.chart_tab.rowconfigure(0, weight=1)

        panel_canvas = tk.Canvas(self.chart_tab, width=330, background="#FFFFFF", highlightthickness=0)
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

        ttk.Label(panel, text="Raw defect data", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(panel, textvariable=self.input_path, width=40).grid(row=1, column=0, sticky="ew", pady=(2, 4))
        ttk.Button(panel, text="Browse / Load Raw Data", command=self.browse_raw).grid(row=2, column=0, sticky="ew")

        ttk.Label(panel, text="Worse-tool result", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(panel, textvariable=self.worse_path, width=40).grid(row=4, column=0, sticky="ew", pady=(2, 4))
        ttk.Button(panel, text="Browse Result", command=self.browse_worse).grid(row=5, column=0, sticky="ew")

        ttk.Label(panel, text="Defect type", style="Card.TLabel").grid(row=6, column=0, sticky="w", pady=(12, 0))
        self.defect_combo = ttk.Combobox(panel, textvariable=self.defect_type, state="readonly", width=38)
        self.defect_combo.grid(row=7, column=0, sticky="ew", pady=(2, 7))
        self.defect_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_process_stage_options())

        ttk.Label(panel, text="Process stage", style="Card.TLabel").grid(row=8, column=0, sticky="w")
        self.stage_combo = ttk.Combobox(panel, textvariable=self.process_stage, state="readonly", width=38)
        self.stage_combo.grid(row=9, column=0, sticky="ew", pady=(2, 7))

        ttk.Label(panel, text="Special step-only rules", style="Card.TLabel").grid(row=10, column=0, sticky="w")
        ttk.Entry(panel, textvariable=self.special_step_rules, width=40).grid(
            row=11, column=0, sticky="ew", pady=(2, 4)
        )
        ttk.Label(
            panel,
            text="Example: Defect Type1: STEP10, STEP20; Defect Type2: STEP30",
            style="Subtitle.TLabel",
            wraplength=280,
        ).grid(row=12, column=0, sticky="w", pady=(0, 7))

        ttk.Label(panel, text="Time column", style="Card.TLabel").grid(row=13, column=0, sticky="w")
        self.time_combo = ttk.Combobox(panel, textvariable=self.time_column, width=38)
        self.time_combo.grid(row=14, column=0, sticky="ew", pady=(2, 7))

        ttk.Label(panel, text="Chart type", style="Card.TLabel").grid(row=15, column=0, sticky="w")
        ttk.Combobox(
            panel,
            textvariable=self.chart_type,
            values=[
                "Box chart by tool",
                "Trend overlay by time",
                "Trend all chambers same axis",
                "Sequential trend by tool",
            ],
            state="readonly",
            width=38,
        ).grid(row=16, column=0, sticky="ew", pady=(2, 8))

        style_frame = ttk.LabelFrame(panel, text="Chart style", padding=7)
        style_frame.grid(row=17, column=0, sticky="ew", pady=(0, 10))
        style_frame.columnconfigure(1, weight=1)
        self._spin_row(style_frame, 0, "Line width", self.line_width, 0.5, 8.0, 0.2)
        self._spin_row(style_frame, 1, "Marker size", self.marker_size, 0.0, 12.0, 0.5)
        ttk.Label(style_frame, text="Color").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Combobox(
            style_frame,
            textvariable=self.color_scheme,
            values=["Tableau", "Viridis", "Plasma", "Custom single"],
            state="readonly",
            width=18,
        ).grid(row=2, column=1, sticky="ew", padx=(6, 0), pady=(4, 0))
        ttk.Label(style_frame, text="Custom").grid(row=3, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(style_frame, textvariable=self.custom_color).grid(
            row=3, column=1, sticky="ew", padx=(6, 0), pady=(4, 0)
        )
        ttk.Label(style_frame, text="Y min").grid(row=4, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(style_frame, textvariable=self.y_min, width=10).grid(
            row=4, column=1, sticky="ew", padx=(6, 0), pady=(4, 0)
        )
        ttk.Label(style_frame, text="Y max").grid(row=5, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(style_frame, textvariable=self.y_max, width=10).grid(
            row=5, column=1, sticky="ew", padx=(6, 0), pady=(4, 0)
        )

        ttk.Button(panel, text="Plot", style="Accent.TButton", command=self.start_plot).grid(
            row=18, column=0, sticky="ew", pady=(0, 5)
        )
        ttk.Button(panel, text="Save PNG", command=self.save_png).grid(row=19, column=0, sticky="ew")

        chart_frame = ttk.Frame(self.chart_tab, style="Card.TFrame", padding=8)
        chart_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        chart_frame.columnconfigure(0, weight=1)
        chart_frame.rowconfigure(0, weight=1)
        self.fig, self.ax = plt.subplots(figsize=(8.8, 5.8), dpi=110)
        self.ax.set_title("Load raw data to begin")
        self.ax.grid(True, color="#D7DEE8", linewidth=0.7, alpha=0.8)
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

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

    def browse_worse(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Excel files", "*.xlsx *.xlsm *.xls"), ("All files", "*.*")]
        )
        if path:
            self.worse_path.set(path)
            self._load_stage_filter_from_worse(path, self.output_sheet.get().strip() or None)

    def _set_busy(self, busy: bool, message: str) -> None:
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
        self._set_busy(True, "Loading raw data...")
        threading.Thread(target=self._load_raw_worker, args=(path, sheet), daemon=True).start()

    def _load_raw_worker(self, path: str, sheet: Optional[str]) -> None:
        try:
            df = read_table(path, sheet_name=sheet)
            validate_required_columns(df)
            df = add_grouping_columns(df)
            defects = detect_defect_columns(df)
            stages = sorted(df["Process_Stage"].dropna().astype(str).unique().tolist())
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
        output_path = self.output_path.get().strip()
        if not input_path or not Path(input_path).is_file():
            raise ValueError("Select a valid raw defect data file.")
        if not bsl_path or not Path(bsl_path).is_file():
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
        output_sheet = self.output_sheet.get().strip()
        if not output_sheet:
            raise ValueError("Output sheet cannot be blank.")
        return {
            "input_path": input_path,
            "bsl_path": bsl_path,
            "output_path": output_path,
            "input_sheet": self.input_sheet.get().strip() or None,
            "output_sheet": output_sheet,
            "defect_columns": parse_defect_columns(self.defect_override.get()),
            "bsl_multiplier": multiplier,
            "min_wafers": min_wafers,
            "outlier_sigma": sigma,
            "special_process_rules": special_process_rules,
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
                special_process_rules=options["special_process_rules"],
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
            stages = sorted(raw["Process_Stage"].dropna().astype(str).unique().tolist())
            self.result_queue.put(
                ("analysis_done", (result, output, raw, defects, stages, list(raw.columns)))
            )
        except Exception as exc:
            self.result_queue.put(("error", exc))

    def _load_stage_filter_from_worse(self, path: str, sheet_name: Optional[str] = None) -> None:
        try:
            worse = pd.read_excel(path, sheet_name=sheet_name or 0)
            if "Stage_ID" in worse.columns and "Step_ID" in worse.columns:
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
        result_path = self.output_path.get().strip()
        if not result_path or not Path(result_path).is_file():
            messagebox.showwarning(
                "Missing result",
                "Run the worse-tool analysis or select an existing output Excel first.",
            )
            return
        ppt_path = filedialog.asksaveasfilename(
            defaultextension=".pptx",
            filetypes=[("PowerPoint presentation", "*.pptx")],
            initialfile=Path(result_path).stem + "_report.pptx",
        )
        if not ppt_path:
            return
        try:
            context = self._build_ppt_context(ppt_path)
        except (ValueError, tk.TclError) as exc:
            messagebox.showwarning("Invalid PPT settings", str(exc))
            return
        self._set_busy(True, "Running PPT generator...")
        threading.Thread(
            target=self._ppt_worker,
            args=(context,),
            daemon=True,
        ).start()

    def _build_ppt_context(self, ppt_output_path: str) -> PPTGenerationContext:
        raw_path = self.input_path.get().strip()
        result_path = self.output_path.get().strip()
        if not raw_path or not Path(raw_path).is_file():
            raise ValueError("A valid raw data file is required for PPT generation.")
        if not result_path or not Path(result_path).is_file():
            raise ValueError("A valid worse-tool result file is required for PPT generation.")
        return PPTGenerationContext(
            raw_data_path=raw_path,
            bsl_path=self.bsl_path.get().strip(),
            worse_result_path=result_path,
            ppt_output_path=ppt_output_path,
            input_sheet=self.input_sheet.get().strip() or None,
            result_sheet=self.output_sheet.get().strip() or DEFAULT_SHEET_NAME,
            defect_columns=parse_defect_columns(self.defect_override.get()),
            bsl_multiplier=float(self.bsl_multiplier.get()),
            min_wafers=int(self.min_wafers.get()),
            outlier_sigma=float(self.outlier_sigma.get()),
            selected_defect=self.defect_type.get().strip() or None,
            selected_process_stage=self.process_stage.get().strip() or None,
        )

    def _ppt_worker(self, context: PPTGenerationContext) -> None:
        try:
            output = run_ppt_generation(
                context,
                log_callback=lambda message: self.result_queue.put(("ppt_log", message)),
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
        except tk.TclError:
            messagebox.showwarning("Invalid setting", "Outlier sigma must be numeric.")
            return
        except ValueError as exc:
            messagebox.showwarning("Invalid chart settings", str(exc))
            return
        self.status.set("Preparing chart...")
        threading.Thread(
            target=self._plot_worker,
            args=(defect, stage, self.chart_type.get(), time_col, sigma, special_rules),
            daemon=True,
        ).start()

    def _plot_worker(
        self,
        defect: str,
        stage: str,
        chart_type: str,
        time_col: str,
        sigma: float,
            special_rules: SpecialProcessRules,
    ) -> None:
        try:
            assert self.raw_df is not None
            if time_col not in self.raw_df.columns:
                raise ValueError("Selected time column does not exist: {}".format(time_col))
            df = filter_outliers_for_defect(self.raw_df, defect, outlier_sigma=sigma)
            filter_label, df = self._filter_chart_process(df, defect, stage, special_rules)
            if df.empty:
                raise ValueError("No rows remain for this defect/process selection after outlier filtering.")
            if chart_type == "Box chart by tool":
                self.result_queue.put(("box", (defect, filter_label, df)))
                return
            df["Selected_Time"] = pd.to_datetime(df[time_col], errors="coerce")
            trend = (
                df.dropna(subset=["Selected_Time"])
                .groupby(
                    ["Selected_Time", "Tool_Group", "Equipment_Group", "Chamber_Group", "Group_Level"],
                    dropna=False,
                )[defect]
                .mean()
                .reset_index()
                .sort_values(["Equipment_Group", "Chamber_Group", "Selected_Time"])
            )
            if trend.empty:
                raise ValueError("{} cannot be parsed for trend chart.".format(time_col))
            if chart_type == "Trend all chambers same axis":
                kind = "trend_all_chambers"
            elif chart_type == "Sequential trend by tool":
                kind = "trend_sequence_by_tool"
            else:
                kind = "trend"
            self.result_queue.put((kind, (defect, filter_label, time_col, trend)))
        except Exception as exc:
            self.result_queue.put(("error", exc))

    def _poll_results(self) -> None:
        try:
            while True:
                kind, payload = self.result_queue.get_nowait()
                if kind == "error":
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
                    result, output, df, defects, stages, columns = payload
                    self.last_result = result
                    self.worse_path.set(str(output))
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
                elif kind == "box":
                    self._draw_box(*payload)
                elif kind == "trend":
                    self._draw_trend(*payload)
                elif kind == "trend_all_chambers":
                    self._draw_trend_all_chambers(*payload)
                elif kind == "trend_sequence_by_tool":
                    self._draw_trend_sequence_by_tool(*payload)
        except queue.Empty:
            pass
        self.after(150, self._poll_results)

    def _apply_loaded_data(
        self,
        df: pd.DataFrame,
        defects: Sequence[str],
        stages: Sequence[str],
        columns: Sequence[str],
    ) -> None:
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
        special_steps = sorted(rules.get(defect_key, {}).keys())
        values.extend([self._format_step_only_option(step) for step in special_steps])
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
    ) -> Tuple[str, pd.DataFrame]:
        step_only = self._parse_step_only_option(selected_process)
        if step_only:
            defect_rules = special_rules.get(defect.strip().casefold(), {})
            if step_only not in defect_rules:
                raise ValueError(
                    "Step-only process '{}' is not configured for defect '{}'.".format(step_only, defect)
                )
            mask = df["Step_ID"].astype(str).str.strip() == step_only
            stage_set = defect_rules.get(step_only)
            if stage_set is not None:
                mask = mask & df["Stage_ID"].astype(str).str.strip().isin(stage_set)
            filtered = df.loc[mask].copy()
            label = "Step_ID={} (Stage ignored)".format(step_only)
            return label, filtered

        filtered = df.loc[df["Process_Stage"].astype(str) == selected_process].copy()
        return selected_process, filtered

    def _show_result_preview(self, result: pd.DataFrame) -> None:
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        preview_columns = list(self.result_tree["columns"])
        for _, row in result.head(500).iterrows():
            values = []
            for column in preview_columns:
                value = row.get(column, "")
                if isinstance(value, float):
                    value = "{:.3f}".format(value)
                values.append(value)
            self.result_tree.insert("", "end", values=values)

    def _draw_box(self, defect: str, stage: str, df: pd.DataFrame) -> None:
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        grouped_parts = []
        for tool, part in df.groupby("Tool_Group"):
            values = pd.to_numeric(part[defect], errors="coerce").dropna()
            if len(values) > 0:
                grouped_parts.append(
                    (str(tool), values.values, len(values), float(values.median()), float(values.mean()))
                )
        grouped_parts.sort(key=lambda item: item[3], reverse=True)
        if not grouped_parts:
            messagebox.showerror("Plot failed", "No numeric values to plot.")
            return
        full_labels = [item[0] for item in grouped_parts]
        compact_labels = len(grouped_parts) > 12
        labels = ["T{}".format(index) for index in range(1, len(grouped_parts) + 1)] if compact_labels else full_labels
        groups = [item[1] for item in grouped_parts]
        counts = [item[2] for item in grouped_parts]
        medians = [item[3] for item in grouped_parts]
        means = [item[4] for item in grouped_parts]
        palette = self._colors(len(groups))
        box = ax.boxplot(
            groups,
            labels=labels,
            showmeans=True,
            patch_artist=True,
            widths=0.58,
            medianprops={"color": "#111111", "linewidth": 1.8},
            meanprops={
                "marker": "D",
                "markerfacecolor": "#FFFFFF",
                "markeredgecolor": "#111111",
                "markersize": 5,
            },
            whiskerprops={"color": "#4B5563", "linewidth": 1.1},
            capprops={"color": "#4B5563", "linewidth": 1.1},
            flierprops={
                "marker": "o",
                "markerfacecolor": "#B91C1C",
                "markeredgecolor": "#B91C1C",
                "markersize": 3,
                "alpha": 0.45,
            },
        )
        for patch, color in zip(box["boxes"], palette):
            patch.set_facecolor(color)
            patch.set_alpha(0.56)
            patch.set_edgecolor("#1F2937")
        for index, values in enumerate(groups, start=1):
            ax.scatter(
                self._jitter_positions(index, len(values)),
                values,
                s=14,
                color=palette[index - 1],
                edgecolors="#FFFFFF",
                linewidths=0.35,
                alpha=0.68,
                zorder=3,
            )
            top = max(values)
            ax.text(
                index,
                top * 1.03 if top != 0 else 0.05,
                "n={}\nmed={:.2f}\navg={:.2f}".format(
                    counts[index - 1],
                    medians[index - 1],
                    means[index - 1],
                ),
                ha="center",
                va="bottom",
                fontsize=7 if compact_labels else 8,
                color="#374151",
            )
            ax.scatter(
                [index],
                [means[index - 1]],
                marker="D",
                s=28,
                color="#FFFFFF",
                edgecolors="#111111",
                linewidths=0.9,
                zorder=4,
            )
            ax.scatter(
                [index],
                [medians[index - 1]],
                marker="_",
                s=180,
                color="#111111",
                linewidths=1.5,
                zorder=4,
            )
        ax.set_title("{} | {} | Box by tool/chamber".format(defect, stage))
        ax.set_xlabel("Tool group")
        ax.set_ylabel("Defect count")
        ax.tick_params(axis="x", rotation=0 if compact_labels else 45)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=8))
        ax.grid(True, axis="y", color="#D7DEE8", linewidth=0.7, alpha=0.8)
        ax.set_axisbelow(True)
        ax.margins(y=0.14)
        if compact_labels:
            mapping_lines = [
                "{} = {} | med {:.2f} | avg {:.2f}".format(label, tool, median, mean)
                for label, tool, median, mean in zip(labels, full_labels, medians, means)
            ]
            ax.text(
                1.01,
                1.0,
                "\n".join(mapping_lines[:40]),
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=7,
                color="#263442",
                bbox={"boxstyle": "round,pad=0.35", "facecolor": "#FFFFFF", "edgecolor": "#D1D5DB", "alpha": 0.92},
            )
            if len(mapping_lines) > 40:
                ax.text(
                    1.01,
                    0.02,
                    "... {} more tools".format(len(mapping_lines) - 40),
                    transform=ax.transAxes,
                    ha="left",
                    va="bottom",
                    fontsize=7,
                    color="#B45309",
                )
        self._apply_y_limits(ax)
        self.fig.tight_layout()
        self.canvas.draw()
        self.status.set("Box chart rendered. Groups: {}".format(len(groups)))

    def _draw_trend(self, defect: str, stage: str, time_col: str, trend: pd.DataFrame) -> None:
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        groups = self._ordered_trend_groups(trend)
        colors = self._colors(len(groups))
        for color, tool in zip(colors, groups):
            part = trend.loc[trend["Tool_Group"] == tool].sort_values("Selected_Time")
            ax.plot(
                part["Selected_Time"],
                part[defect],
                marker="o" if self.marker_size.get() > 0 else None,
                markersize=self.marker_size.get(),
                linewidth=self.line_width.get(),
                color=color,
                label=str(tool),
            )
        ax.set_title("{} | {} | Trend overlay by {}".format(defect, stage, time_col))
        ax.set_xlabel(time_col)
        ax.set_ylabel("Mean defect count")
        ax.grid(True, color="#D7DEE8", linewidth=0.7, alpha=0.8)
        ax.legend(loc="best", fontsize=8, frameon=True, framealpha=0.88)
        self._apply_y_limits(ax)
        self.fig.autofmt_xdate()
        self.fig.tight_layout()
        self.canvas.draw()
        self.status.set("Trend chart rendered.")

    def _draw_trend_all_chambers(
        self,
        defect: str,
        stage: str,
        time_col: str,
        trend: pd.DataFrame,
    ) -> None:
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        groups = self._ordered_trend_groups(trend)
        colors = self._colors(len(groups))
        for color, tool in zip(colors, groups):
            part = trend.loc[trend["Tool_Group"] == tool].sort_values("Selected_Time")
            ax.plot(
                part["Selected_Time"],
                part[defect],
                marker="o" if self.marker_size.get() > 0 else None,
                markersize=self.marker_size.get(),
                linewidth=self.line_width.get(),
                color=color,
                label=str(tool),
            )
        ax.set_title("{} | {} | All chambers trend by {}".format(defect, stage, time_col))
        ax.set_xlabel(time_col)
        ax.set_ylabel("Mean defect count")
        ax.yaxis.set_major_locator(MaxNLocator(nbins=8))
        ax.grid(True, color="#D7DEE8", linewidth=0.7, alpha=0.8)
        ax.set_axisbelow(True)
        ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8, frameon=True, framealpha=0.9)
        self._apply_y_limits(ax)
        self.fig.autofmt_xdate()
        self.fig.tight_layout()
        self.canvas.draw()
        self.status.set("All-chamber trend rendered on one axis. Groups: {}".format(len(groups)))

    def _draw_trend_sequence_by_tool(
        self,
        defect: str,
        stage: str,
        time_col: str,
        trend: pd.DataFrame,
    ) -> None:
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        groups = self._ordered_trend_groups(trend)
        colors = self._colors(len(groups))
        x_positions: List[int] = []
        x_labels: List[str] = []
        boundaries: List[float] = []
        tool_labels: List[Tuple[float, str, object]] = []
        current_x = 0

        for index, (color, tool) in enumerate(zip(colors, groups)):
            part = trend.loc[trend["Tool_Group"] == tool].sort_values("Selected_Time").reset_index(drop=True)
            if part.empty:
                continue
            xs = list(range(current_x, current_x + len(part)))
            ax.plot(
                xs,
                part[defect],
                marker="o" if self.marker_size.get() > 0 else None,
                markersize=self.marker_size.get(),
                linewidth=self.line_width.get(),
                color=color,
                label=str(tool),
            )
            x_positions.extend(xs)
            x_labels.extend(part["Selected_Time"].dt.strftime("%m-%d %H:%M").tolist())
            tool_labels.append((sum(xs) / float(len(xs)), str(tool), color))
            current_x += len(part) + 1
            if index < len(groups) - 1:
                boundaries.append(current_x - 0.5)

        if not x_positions:
            messagebox.showerror("Plot failed", "No valid trend points to plot.")
            return

        for boundary in boundaries:
            ax.axvline(boundary, linestyle="--", linewidth=1.0, color="#6B7280", alpha=0.45)

        configured_y_min, configured_y_max = self._get_y_limits()
        self._apply_y_limits(ax)
        y_min, y_max = ax.get_ylim()
        y_span = y_max - y_min if y_max > y_min else 1.0
        if configured_y_max is None:
            ax.set_ylim(y_min, y_max + y_span * 0.16)
            y_min, y_max = ax.get_ylim()
            y_span = y_max - y_min if y_max > y_min else 1.0
        for x_mid, label, color in tool_labels:
            ax.text(
                x_mid,
                y_max + y_span * 0.04,
                label,
                ha="center",
                va="bottom",
                fontsize=8,
                fontweight="bold",
                color=color,
                rotation=0,
            )

        max_ticks = 70
        tick_step = max(1, int(len(x_positions) / max_ticks) + (1 if len(x_positions) % max_ticks else 0))
        shown_positions = x_positions[::tick_step]
        shown_labels = x_labels[::tick_step]
        ax.set_xticks(shown_positions)
        ax.set_xticklabels(shown_labels, rotation=55, ha="right", fontsize=8)
        ax.set_title("{} | {} | Sequential trend by tool".format(defect, stage))
        ax.set_xlabel("{} sorted within each tool, tools appended left to right".format(time_col))
        ax.set_ylabel("Mean defect count")
        ax.yaxis.set_major_locator(MaxNLocator(nbins=8))
        ax.grid(True, axis="y", color="#D7DEE8", linewidth=0.7, alpha=0.8)
        ax.set_axisbelow(True)
        ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8, frameon=True, framealpha=0.9)
        self.fig.tight_layout()
        self.canvas.draw()
        self.status.set("Sequential trend rendered on one axis. Groups: {}".format(len(groups)))

    def _ordered_trend_groups(self, trend: pd.DataFrame) -> List[str]:
        order = (
            trend[["Tool_Group", "Equipment_Group", "Chamber_Group", "Group_Level"]]
            .drop_duplicates()
            .sort_values(["Equipment_Group", "Chamber_Group", "Tool_Group"])
        )
        return order["Tool_Group"].astype(str).tolist()

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
        base = list(plt.cm.tab20.colors)
        return [base[i % len(base)] for i in range(count)]

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
            self.fig.savefig(path, dpi=180, bbox_inches="tight")
            self.status.set("Saved {}".format(path))


def main() -> None:
    app = DefectWorseToolApp()
    app.mainloop()


if __name__ == "__main__":
    main()
