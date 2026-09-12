"""Shared interactive/headless charts. Ordinal positions never encode elapsed time."""
import math
import textwrap
import tkinter as tk
from tkinter import ttk

import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.font_manager import FontProperties


class ChartViewMixin:
    def _draw_box(self, defect, stage, data):
        self._render_chart("box", defect, stage, "Scan_Time", data)

    def _draw_trend(self, defect, stage, time_col, data):
        self._render_chart("overlay", defect, stage, time_col, data)

    def _draw_trend_all_chambers(self, defect, stage, time_col, data):
        self._render_chart("overlay", defect, stage, time_col, data)

    def _draw_trend_sequence_by_tool(self, defect, stage, time_col, data):
        self._render_chart("sequence", defect, stage, time_col, data)

    def _render_chart(self, kind, defect, stage, time_col, data):
        from defect_worse_ui import add_equal_spacing_index, prepare_trend_data
        self._chart_request = (kind, defect, stage, time_col, data)
        self._reset_chart_artists()
        self._hover_points = []
        self._hover_label = None
        self.fig.clear()
        self.fig.patch.set_facecolor("#FFFFFF")
        self._chart_context_key = (defect, stage, self._chart_group_label(data))
        if "chart_focus" not in self.__dict__:
            self.chart_focus = {}
        if "chart_orders" not in self.__dict__:
            self.chart_orders = {}
        self._chart_stats = data.groupby("Chart_Group", sort=False)[defect].agg(["size", "mean", "median"])
        self._chart_stats["wafers"] = (data.groupby("Chart_Group")["Wafer_Key"].nunique()
                                       if "Wafer_Key" in data else float("nan"))
        order = data.attrs.get("tool_order")
        if order is None:
            order = self.chart_orders.get(self._chart_context_key)
        if order is None:
            order = self._chart_stats.sort_values(["median", "mean"], ascending=False,
                                                 kind="mergesort").index.tolist()
        groups = [g for g in order if g in self._chart_stats.index]
        groups += sorted(set(self._chart_stats.index) - set(groups))
        self.chart_orders[self._chart_context_key] = list(order)
        self._chart_groups = groups
        self._chart_codes = {g: "T{}".format(order.index(g) + 1) if g in order else "T{}".format(len(order) + i + 1)
                             for i, g in enumerate(groups)}
        export = self.__dict__.get("_export_chart", False)
        dense = len(groups) > 12
        # Screen density is handled by a scrollable detail table. Exports grow physically.
        sidebar = .31 if export or (not dense and len(groups) > 4) else .19
        height = self.fig.get_figheight()
        title_width = max(28, int(self.fig.get_figwidth() * 8))
        title = textwrap.fill("{} cross to {}".format(defect, stage), title_width)
        title_bottom = .98 - len(title.splitlines()) * 18 / 72 / height
        meta = data.attrs.get("chart_meta", {})
        wafers = data["Wafer_Key"].nunique() if "Wafer_Key" in data else "unknown"
        subtitle = "{} | {} | {} rows / {} unique wafers | {}".format(
            {"box": "Box", "overlay": "Overlay: equal point spacing", "sequence": "Sequential: equal point spacing"}[kind],
            meta.get("window", "Current data"), len(data), wafers, meta.get("cleaning", "As supplied"))
        subtitle = textwrap.fill(subtitle, title_width + 20)
        subtitle_top = title_bottom - .14 / height
        plot_top = subtitle_top - (len(subtitle.splitlines()) * 12 / 72 + .25) / height
        grid = self.fig.add_gridspec(1, 2, width_ratios=[1 - sidebar, sidebar],
                                    left=.09, right=.98, top=max(.55, plot_top),
                                    bottom=min(.43, (1.9 if kind != "box" else 1.25) / height),
                                    wspace=.10)
        ax = self.fig.add_subplot(grid[0, 0])
        side = self.fig.add_subplot(grid[0, 1])
        side.set_axis_off()
        self.ax = ax
        self._chart_side = side
        self.fig.suptitle(title, x=.09, y=.98, ha="left", fontsize=12, fontweight="bold")
        self.fig.text(.09, subtitle_top, subtitle, fontsize=9, va="top", color="#52606D")
        colors = dict(zip(order, self._colors(len(order)))) if kind != "box" else {}
        for g in groups:
            colors.setdefault(g, "#52606D")
        if kind == "box":
            values = [data.loc[data.Chart_Group == g, defect].to_numpy() for g in groups]
            box = ax.boxplot(values, patch_artist=True, showfliers=False,
                             showmeans=self.show_box_mean.get(), widths=.6,
                             medianprops={"color": "#C23B22", "linewidth": 2},
                             meanprops={"marker": "D", "markerfacecolor": "#F2B134", "markeredgecolor": "#263238"})
            ranked = self._chart_stats.sort_values(["median", "mean"], ascending=False).index.tolist()
            ranks = dict(zip(ranked, self._box_rank_colors(len(ranked))))
            for index, (g, patch, vals) in enumerate(zip(groups, box["boxes"], values), 1):
                key = "{}|{}|{}|{}".format(defect, stage, self._chart_group_label(data), g)
                color, width = self._artist_style("box", key, ranks[g], self.box_line_width.get())
                patch.set(facecolor=color, edgecolor=color, linewidth=width, alpha=.72)
                self._register_chart_artist(patch, "box", key, g, color, width)
                scatter = ax.scatter(self._jitter_positions(index, len(vals)), vals, color="black",
                                     s=12 if dense else 18, linewidths=0, zorder=3)
                self._hover_points.append((scatter, data.loc[data.Chart_Group == g].reset_index(drop=True), "scatter"))
            stats_labels = [self._stat_text(g) for g in groups]
            per_box = ax.get_position().width * self.fig.get_figwidth() * self.fig.dpi / max(1, len(groups))
            size = self._box_stats_font_size(per_box)
            measure = self.fig.canvas.get_renderer()
            required = max((measure.get_text_width_height_descent(line, FontProperties(size=size), False)[0]
                            for label in stats_labels for line in label.splitlines()), default=0) + 6
            if not float(self.box_label_font_size.get()) and required > per_box:
                size = max(8, size * per_box / required * .95)
                required = max((measure.get_text_width_height_descent(line, FontProperties(size=size), False)[0]
                                for label in stats_labels for line in label.splitlines()), default=0) + 6
            inline = not dense and per_box >= required and self._get_y_limits() == (None, None)
            if inline:
                # Shrink the plot vertically and reserve a dedicated annotation strip above it.
                pos = ax.get_position()
                band = min(.18, (size * 3.8 / 72) / self.fig.get_figheight())
                ax.set_position([pos.x0, pos.y0, pos.width, pos.height - band])
                for index, label in enumerate(stats_labels, 1):
                    ax.text(index, 1.025, label, transform=ax.get_xaxis_transform(), fontsize=size,
                            ha="center", va="bottom", clip_on=False)
            labels = [g if per_box >= max(100, len(str(g)) * 8) else self._chart_codes[g] for g in groups]
            ax.set_xticks(range(1, len(groups) + 1))
            ax.set_xticklabels(labels, rotation=90 if len(groups) > 18 else 30, ha="right", fontsize=8)
            if len(groups) > 30 and not export:
                for i, tick in enumerate(ax.get_xticklabels()):
                    tick.set_visible(i % max(1, math.ceil(len(groups) / 22)) == 0 or i == len(groups)-1)
            ax.set_xlabel(self._chart_group_label(data) + " | shared Tool order")
            self._render_side(side, groups, ranks, show_stats=not inline, box=True)
        else:
            trend = add_equal_spacing_index(prepare_trend_data(data, defect, time_col))
            self._overlay_data = trend
            current = 1
            for g in groups:
                part = trend.loc[trend.Chart_Group == g].copy().reset_index(drop=True)
                xs = part.Observation_Index if kind == "overlay" else list(range(current, current + len(part)))
                key = "{}|{}|{}|{}".format(defect, stage, self._chart_group_label(data), g)
                color, width = self._artist_style("line", key, colors[g], self.line_width.get())
                line, = ax.plot(xs, part[defect], marker="o" if self.marker_size.get() else None,
                                markersize=self.marker_size.get(), color=color, linewidth=width, label=g)
                self._register_chart_artist(line, "line", key, g, color, width)
                self._hover_points.append((line, part, "line"))
                part["_Plot_X"] = list(xs)
                if kind == "sequence":
                    if current > 1:
                        ax.axvline(current - .5, color="#9CA3AF", linestyle="--", linewidth=.7)
                    current += len(part)
            if kind == "overlay":
                ax.set_xlim(.5, int(trend.Observation_Index.max()) + .5)
                self._update_overlay_ticks()
            else:
                self._sequence_ticks(time_col)
                ax.set_xlim(.5, current - .5)
            self._render_side(side, groups, colors, box=False)
        ax.set_ylabel("Defect count")
        ax.grid(True, axis="y", color="#D7DEE8", linewidth=.6)
        ax.set_axisbelow(True)
        ax.margins(y=.08)
        self._reference_lines(data, ax)
        self._apply_y_limits(ax)
        self._apply_focus()
        self._refresh_details()
        self.canvas.draw()
        self.status.set("{}: {} Tools / {} points. Tool Details shows full names; hover a point for its time.".format(kind, len(groups), len(data)))

    def _stat_text(self, group):
        row = self._chart_stats.loc[group]
        labels = []
        if self.show_box_count.get():
            labels.append("Rows={}".format(int(row["size"])))
        if self.show_box_median.get():
            labels.append("Median={:.2f}".format(row["median"]))
        if self.show_box_mean.get():
            labels.append("Mean={:.2f}".format(row["mean"]))
        return "\n".join(labels)

    def _render_side(self, ax, groups, colors, show_stats=False, box=False):
        export = self.__dict__.get("_export_chart", False)
        font_size = (float(self.box_label_font_size.get()) or 9) if box else 9
        width = ax.get_position().width * self.fig.get_figwidth() * self.fig.dpi
        height = ax.get_position().height * self.fig.get_figheight() * self.fig.dpi
        line_height = font_size * self.fig.dpi / 72 * 1.25
        labels = []
        for g in groups:
            label = "{}  {}".format(self._chart_codes[g], g)
            if show_stats:
                label += "\n" + self._stat_text(g)
            labels.append(self._wrap_pixels(label, width - (55 if not box else 8), font_size))
        key_height = 72 * self.fig.dpi / 72 if box else 0
        required = sum((len(label.splitlines()) + .6) * line_height for label in labels)
        if box:
            handles = [Line2D([], [], color="#C23B22", label="Median")]
            if self.show_box_mean.get():
                handles.append(Line2D([], [], marker="D", color="none", markerfacecolor="#F2B134", label="Mean"))
            handles.append(Line2D([], [], marker="o", color="none", markerfacecolor="black", label="Raw data"))
            ax.legend(handles=handles,
                      loc="upper left", frameon=False, fontsize=9, borderaxespad=0)
            if not show_stats:
                return
        if not export and (len(groups) > 12 or required + key_height > height):
            message = "{} Tools\n\nOpen Tool Details\nfor full names,\ncounts and statistics.\n\nPNG export expands\nthe chart and includes\nthe complete list.".format(len(groups))
            ax.text(0, 1 - key_height / height, self._wrap_pixels(message, width - 8, 9),
                    transform=ax.transAxes, va="top", fontsize=9)
            return
        if not show_stats and not box:
            handles = [Line2D([], [], color=colors[g], label=label) for g, label in zip(groups, labels)]
            ax.legend(handles=handles, loc="upper left", frameon=False, fontsize=9,
                      borderaxespad=0, title="Tool order")
            return
        position = 1 - key_height / height
        for label in labels:
            ax.text(0, position, label, transform=ax.transAxes,
                    va="top", fontsize=font_size, color="#263442")
            position -= (len(label.splitlines()) + .6) * line_height / height

    def _wrap_pixels(self, text, width, size):
        renderer = self.fig.canvas.get_renderer()
        font = FontProperties(size=size)
        output = []
        for original in text.split("\n"):
            line = ""
            for char in original:
                if line and renderer.get_text_width_height_descent(line + char, font, False)[0] > width:
                    space = line.rfind(" ")
                    if space >= len(line) // 2:
                        output.append(line[:space])
                        line = line[space + 1:]
                    else:
                        output.append(line)
                        line = ""
                line += char
            output.append(line)
        return "\n".join(output)

    def _tick_budget(self):
        width = self.ax.get_position().width * self.fig.get_figwidth() * self.fig.dpi
        return max(2, min(10, int(width / (self.fig.dpi * .9))))

    def _update_overlay_ticks(self):
        from defect_worse_ui import build_equal_spacing_time_ticks
        trend = self._overlay_data
        focus = self.chart_focus.get(self._chart_context_key)
        if focus not in self._chart_groups:
            focus = trend.groupby("Chart_Group", sort=False).size().idxmax()
        ticks, labels = build_equal_spacing_time_ticks(trend, self._tick_budget(), focus)
        self.ax.set_xticks(ticks)
        self.ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
        self.ax.set_xlabel("{} | dates for {}\nEach Tool uses point order; select a Tool to change dates".format(
            self._chart_request[3], self._chart_codes[focus]), fontsize=9)

    def _sequence_ticks(self, time_col):
        from defect_worse_ui import sample_tick_labels
        positions, labels = [], []
        for artist, part, _ in self._hover_points:
            group = part.Chart_Group.iloc[0]
            for x, time in zip(artist.get_xdata(), part.Selected_Time):
                positions.append(int(x))
                labels.append("{}\n{}".format(self._chart_codes[group], pd.Timestamp(time).strftime("%Y-%m-%d\n%H:%M")))
        ticks, text = sample_tick_labels(positions, labels, self._tick_budget())
        self.ax.set_xticks(ticks)
        self.ax.set_xticklabels(text, rotation=35, ha="right", fontsize=8)
        self.ax.set_xlabel(time_col + " | chronological within each Tool\nTool segments, equal point spacing", fontsize=9)

    def _reference_lines(self, data, ax):
        meta = data.attrs.get("chart_meta", {})
        flags = (("show_bsl_line", "BSL", "#334155", "--"),
                 ("show_threshold_line", "Threshold", "#B91C1C", "-."),
                 ("show_golden_line", "Golden", "#047857", ":"))
        entries = []
        for flag, name, color, style in flags:
            variable = self.__dict__.get(flag)
            if variable is not None and not variable.get():
                continue
            value = meta.get(name)
            if value is None or not math.isfinite(float(value)):
                entries.append(name + " unavailable")
                continue
            ax.axhline(float(value), color=color, linestyle=style, linewidth=1.1, label="_" + name)
            entries.append("{}={:.3g}".format(name, value))
        note = " | ".join(entries)
        if meta.get("reference_note"):
            note += " | " + meta["reference_note"]
        self.fig.text(.09, .015, self._wrap_pixels(note, self.fig.bbox.width * .87, 8),
                      fontsize=8, color="#475569", va="bottom")

    def focus_tool(self, group):
        if "_chart_request" not in self.__dict__:
            return
        if group is None:
            self.chart_focus.pop(self._chart_context_key, None)
            self.selected_chart_artist = None
            self.selected_chart_item.set("")
        else:
            self.chart_focus[self._chart_context_key] = group
        self._apply_focus()
        if self._chart_request[0] == "overlay":
            self._update_overlay_ticks()
        self.canvas.draw_idle()

    def _apply_focus(self):
        focus = self.chart_focus.get(self._chart_context_key)
        for artist, info in self.chart_artist_registry.items():
            active = info["label"] == focus
            artist.set_alpha((1.0 if active else .25) if focus else (.72 if info["kind"] == "box" else 1.0))
            artist.set_linewidth(info["linewidth"] + (1.5 if active else 0))
            if active:
                self.selected_chart_artist = artist
                self.selected_chart_item.set("Selected: " + info["label"])

    def _on_chart_hover(self, event):
        if "_chart_request" not in self.__dict__ or event.inaxes != self.ax:
            if self.__dict__.get("_hover_label") is not None:
                self._hover_label.set_visible(False)
                self.canvas.draw_idle()
            return
        for artist, part, kind in self._hover_points:
            contains, info = artist.contains(event)
            if not contains or not len(info.get("ind", [])):
                continue
            index = int(info["ind"][0])
            row = part.iloc[index]
            time_col = self._chart_request[3]
            time = row.get("Selected_Time", row.get(time_col, "unknown"))
            text = "{}\n{}: {}\n{} = {}\nLot {} / Wafer {}".format(row.Chart_Group, time_col, time,
                self._chart_request[1], row[self._chart_request[1]], row.get("Lot_ID", "?"), row.get("Wafer_NO", "?"))
            if self._hover_label is None:
                self._hover_label = self.ax.annotate("", (0, 0), xytext=(8, 8), textcoords="offset points",
                    bbox=dict(boxstyle="round", fc="white", ec="#94A3B8"), fontsize=9, zorder=20)
            self._hover_label.xy = (event.xdata, event.ydata)
            right_half = event.x > self.ax.bbox.x0 + self.ax.bbox.width / 2
            top_half = event.y > self.ax.bbox.y0 + self.ax.bbox.height / 2
            self._hover_label.set_ha("right" if right_half else "left")
            self._hover_label.set_va("top" if top_half else "bottom")
            self._hover_label.set_position((-8 if right_half else 8, -8 if top_half else 8))
            self._hover_label.set_text(text)
            self._hover_label.set_visible(True)
            self.canvas.draw_idle()
            return
        if self._hover_label is not None:
            self._hover_label.set_visible(False)
            self.canvas.draw_idle()

    def open_tool_details(self):
        if "_chart_request" not in self.__dict__:
            return
        win = self.__dict__.get("_details_window")
        if win is not None and win.winfo_exists():
            win.lift()
            return
        win = tk.Toplevel(self)
        self._details_window = win
        win.title("Tool Details | select to highlight across chart types")
        win.geometry("850x450")
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)
        columns = ("Code", "Tool (full name)", "Rows", "Unique wafers", "Median", "Mean")
        tree = ttk.Treeview(win, columns=columns, show="headings", selectmode="browse")
        self._details_tree = tree
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=340 if col == "Tool (full name)" else 100, stretch=False)
        tree.grid(row=0, column=0, sticky="nsew")
        ttk.Scrollbar(win, orient="vertical", command=tree.yview).grid(row=0, column=1, sticky="ns")
        vertical = win.grid_slaves(row=0, column=1)[0]
        horizontal = ttk.Scrollbar(win, orient="horizontal", command=tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.bind("<<TreeviewSelect>>", lambda event: self.focus_tool(self._chart_groups[int(tree.selection()[0])])
                  if tree.selection() else None)
        ttk.Button(win, text="Clear highlight", command=lambda: self.focus_tool(None)).grid(row=2, column=0, pady=8)
        self._refresh_details()

    def _refresh_details(self):
        tree = self.__dict__.get("_details_tree")
        if tree is None or not tree.winfo_exists():
            return
        tree.delete(*tree.get_children())
        for i, g in enumerate(self._chart_groups):
            row = self._chart_stats.loc[g]
            tree.insert("", "end", iid=str(i), values=(self._chart_codes[g], g, int(row["size"]),
                int(row.wafers) if pd.notna(row.wafers) else "unknown", "{:.3f}".format(row["median"]), "{:.3f}".format(row["mean"])))

    def export_current_chart(self, path):
        from ppt_report import make_renderer
        if "_chart_request" not in self.__dict__:
            self.fig.savefig(path, dpi=180, bbox_inches="tight")
            return
        renderer = make_renderer()
        for name in ("show_box_count", "show_box_mean", "show_box_median", "box_label_font_size",
                     "line_width", "box_line_width", "marker_size", "color_scheme", "custom_color", "y_min", "y_max",
                     "show_bsl_line", "show_threshold_line", "show_golden_line"):
            if name in self.__dict__:
                renderer.__dict__[name].set(self.__dict__[name].get())
        renderer.artist_style_overrides = self.artist_style_overrides.copy()
        renderer.chart_focus = self.chart_focus.copy()
        renderer.chart_orders = self.chart_orders.copy()
        count = len(self._chart_groups)
        name_lines = max((math.ceil(len(str(g)) / 32) for g in self._chart_groups), default=1)
        size_factor = max(1, (float(self.box_label_font_size.get()) or 9) / 9)
        renderer.fig.set_size_inches(max(12, min(30, count * .28 + 5)),
                                    max(8, count * (.80 + .18 * (name_lines - 1)) * size_factor + 2))
        renderer._export_chart = True
        renderer._render_chart(*self._chart_request)
        renderer.fig.savefig(path, dpi=160, bbox_inches="tight")
