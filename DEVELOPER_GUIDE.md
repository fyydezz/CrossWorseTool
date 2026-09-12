# Defect Worse Tool Cross 开发者文档

## 2026-09-12 绘图模块拆分

`defect_worse_ui.DefectWorseToolApp` 继承 `chart_view.ChartViewMixin`。UI 保留 Tk 控件、文件加载、线程队列、风格变量；`chart_view.py` 负责 Box/Overlay/Sequential 的实际布局、选中高亮、悬停详情和导出；`chart_context.py` 负责参考值与排序。部署时务必连同这两个新增模块一起复制。

- `analysis_references(raw, defect, options)` 使用与核心一致的分析窗口和清洗设置，调用 `summarize_one_defect()` 取得各层 Golden，再按文件/计算均值/近期均值确定 BSL 与 threshold。临时零阈值用于获得全部合格候选，不改变用户计算参数。没有合格 Golden 时仍保留可用 BSL；不读取输出 Excel，也不调用上下 5% 截尾函数。
- `annotate_chart_data(renderer, raw, data, defect, options, chart_window, references=None)` 返回带 `attrs['tool_order']` 和 `attrs['chart_meta']` 的当前绘图 DataFrame。仅添加元数据，不过滤或修改传入图表行；近期排名在单独副本上计算。PPT 可以传入提前算好的 references，避免在一对图之间重复计算。若以后使用会丢失 attrs 的 pandas 操作，应显式重新赋予元数据。
- `tool_order` 固定使用最近 14 天（全文件最新 Scan_Time 为锚点）的 median/mean 降序，其后追加仅历史存在的 Tool。不同图表窗口共用此顺序；红蓝颜色仍表达当前 Box 数据的排名。若未来需要“每次按当前 Box 值排序”，应做显式模式选择，不要悄悄打乱跨图 T 编号。
- `_render_chart(kind, defect, stage, time_col, data)` 为统一绘制入口。`kind` 为 box、overlay、sequence；输入应已经按明确的窗口和清洗规则准备完毕。重复时间行不得合并，Overlay X 为各组 cumcount + 1；Sequence X 为按共同 Tool 顺序串接后的逐行序号。
- `_wrap_pixels()` 使用 Matplotlib 字体实际宽度换行；统计带、主图、侧栏、页脚彼此分区。屏幕超出空间的统计进入可滚动 `Tool Details`。`export_current_chart()` 另建 Agg renderer 扩大画布并附全量列表，不改变当前窗口大小；PPT 再按图片真实比例适配单页。
- `chart_focus` 按 `(defect, layer, chart grouping)` 保存选中 Tool；`chart_orders` 缓存无 attrs 数据的排序。风格仍通过 `artist_style_overrides` 按 box/line 类型及上下文保存。`_update_overlay_ticks()` 将所选 Tool 的真实时间映射到它自己的观测序号，不能解释为所有 Tool 同时发生；悬停使用逐行元数据精确定位。
- `NAMED_COLORS` 保存中文/英文名称到十六进制的映射；`_color_controls()` 在全局与单项编辑窗口复用同一控件。选名称只更新原有颜色变量，原有十六进制覆盖接口不变；变量 trace 随控件销毁清理。`_on_chart_resize()` 250ms 防抖重排布局，`destroy()` 取消重排与轮询定时器。
- `PPTGenerationContext` 新增三个默认 True 的参考线开关，不改变外接三路径方法签名。内置 PPT 使用这些开关和共享绘图模块；模板或自定义外接生成器不自动获得完整 UI 风格变量。

验证命令：`python -m unittest discover -v`。新增 `test_chart_view.py` 覆盖全部 Trend 点距/行数、共同排名/高亮/真实时间、核心参考值一致性、缺失 Golden、参考线开关、黑色 raw 点、密集导出名称/边界以及中文选色映射。改布局时还应渲染稀疏和 30 个以上 Tool 的图，检查标题、刻度、统计和页脚；不要只依赖计算测试。

## Golden Tool 实现

`add_golden_comparison(grouped, min_wafers)` 接收单个 Defect 的清洗后分组统计，在 Worse Tool 阈值筛选前执行。候选数门槛为 `max(5, min_wafers)`；按 Mean、Median 升序，Wafer_Count 降序和 Tool_Group 升序排序，再按 Stage_ID/Step_ID 取首个候选，以 many-to-one merge 回填。`GOLDEN_COLUMNS` 同时用于非空/空结果输出和 UI 预览。比较值不参与 BSL 或优先级计算。

`test_golden_tool.py` 覆盖不足 5 片、重复 wafer、不同 layer、Step-only、特殊合并、零均值、无候选及旧 Excel append。Raw Data 使用独立黑色 scatter，`showfliers=False` 只关闭 boxplot 的重复离群点图层，不过滤任何散点数据。

## 2026-09 报告与排序接口

`ppt_report.generate_report(context, log_callback)` 重新调用核心分析入口，按 Defect/Stage/Step 去重后生成页面。每页从原始数据独立准备 14d Box 与 all-data Sequential Trend，复用 process 聚合和 outlier 清洗函数。`make_renderer()` 使用 Agg Figure 和普通变量适配器复用 UI 绘图，不创建 Tk 控件。`PPTGenerationContext` 新增带默认值的 BSL 来源、时间窗口、特殊规则、聚合、画图分组和时间列字段；原外部三路径接口保留。

`recent_mean` 在应用分析时间窗口之前保存原始数据副本，从该副本单独取最近 14 天计算清洗后均值。`rank_worse_results()` 仅影响预览顺序，权重为 Mean/BSL 百分位 0.7、Wafer_Count 百分位 0.3。BSL=0 且 Mean>0 按最高严重程度排名。

`_draw_box()` 根据每组绘图区像素宽度与字号选择图内统计或右侧统计。新增测试 `test_ppt_report.py` 覆盖 BSL 窗口隔离、排序、稀疏 Box 和实际 PPT 分页生成。模板保留主题/母版及页面尺寸，不复制模板示例页内容。

## Interactive Chart Architecture (latest UI)

Chart layout and styling are intentionally separated:

- `_build_chart_tab()` builds the hierarchical control panel and chart toolbar.
- `open_chart_style_dialog()` owns global defaults for box labels, line styles, palettes, markers, and Y-axis limits. Its Canvas-based body and vertical scrollbar keep every control reachable under Windows display scaling.
- `_reset_chart_artists()` clears selection state before each redraw.
- `_register_chart_artist()` makes a box patch or line pickable and stores edit metadata.
- `_on_chart_pick()` records the clicked artist and updates the toolbar selection.
- `edit_selected_chart_item()` changes only the selected artist and stores the override.
- `_artist_style()` reapplies an override when the same chart context is rendered again.

Override keys include defect, process, chart-group type, and group value. Overrides are session-local and are not written to disk. `_draw_box()` maps descending rank through `coolwarm` from red to blue, preserves raw-data scatter, and conditionally builds Count/Median/Mean labels. Trend methods use `_colors()` for distinct shuffled defaults and register each line for picking.

`box_label_font_size=0` keeps `_box_stats_font_size()` in adaptive mode. Any positive value overrides the adaptive result for the main Box statistics and compact tool mapping.

Data-completeness rules:

- `calculate_recent_trimmed_bsl()` operates on a temporary numeric Series. Its quantile trimming must never be reused as the DataFrame passed to `summarize_one_defect()` or chart preparation.
- `calculate_mean_bsl()` applies the selected outlier handling to the complete defect-wide analysis window and returns one global baseline Mean. It does not group by Tool.
- `prepare_trend_data()` keeps one row per valid chart input row and performs a stable Tool/time/source-order sort. Do not reintroduce the former Tool/time `groupby().mean()` because it collapsed multiple wafers into one point.
- `add_equal_spacing_index()` assigns a 1-based observation index within each Tool without dropping rows.
- `filter_by_recent_scan_time()` rejects invalid Scan Time values rather than silently excluding them from recent-window analysis.
- `_filter_chart_group_mode()` uses explicit missing-ID groups rather than dropping rows.

When adding a new selectable chart type, call `_reset_chart_artists()`, apply `_artist_style()` before drawing, then call `_register_chart_artist()` with a context-specific key. Keep Matplotlib drawing on the Tk main thread through `_poll_results()`.

---

本文档面向后续维护和二次开发。项目兼容 Python 3.8，请不要使用 `match/case`、`list[str]`、`X | None` 等 Python 3.9+ 或 3.10+ 语法。

## 1. 工程结构

```text
DefectWorseToolCross/
├── defect_worse_tool.py   # 核心算法、命令行入口、Excel 输出
├── defect_worse_ui.py     # Tkinter UI、后台线程、Matplotlib 图表
├── ppt_integration.py     # 外部 PPT 生成接口
├── generate_demo_data.py  # Demo 数据生成
├── requirements.txt       # Python 3.8 依赖
├── README.md              # 用户使用说明
└── DEVELOPER_GUIDE.md     # 本文档
```

依赖方向：

```text
defect_worse_ui.py
  -> defect_worse_tool.py
  -> ppt_integration.py

defect_worse_tool.py 不依赖 UI
ppt_integration.py 不依赖 UI
```

请保持核心算法和 UI 解耦。算法函数不要访问 Tkinter 控件；PPT 接口也不要直接操作 UI。

## 2. 核心数据流

```text
CSV/Excel
  -> read_table()
  -> normalize_columns()
  -> validate_required_columns()
  -> add_grouping_columns()
  -> detect_defect_columns()
  -> normalize_bsl_source()
  -> file: read_bsl_table() + build_bsl_lookup()
  -> calculated_mean: calculate_mean_bsl()
  -> 每个 defect 调用 summarize_one_defect()
  -> handle_outliers_for_defect()
  -> apply_special_process_rules()
  -> apply_process_aggregation()
  -> groupby + wafer/BSL/threshold 筛选
  -> write_result_to_excel()
```

## 3. defect_worse_tool.py 方法说明

### 3.1 输入读取和字段处理

- `normalize_column_name(name)`：去除表头前后空格。
- `normalize_columns(df)`：将必须 metadata 字段按大小写不敏感方式映射为内部标准名，例如 `LOT_ID` -> `Lot_ID`；defect 列名保持不变。
- `parse_sheet_name(sheet_name)`：空值返回第 0 个 sheet；纯数字字符串转换为 sheet index。
- `read_table(path, sheet_name=None)`：读取 `.csv`、`.xlsx`、`.xlsm`、`.xls`。
- `validate_required_columns(df)`：检查 `Lot_ID`、`Wafer_NO`、`Scan_Time`、`Stage_ID`、`Step_ID`、`Equipment_ID`、`Chamber_ID`。
- `detect_defect_columns(df, explicit_columns=None)`：自动识别 numeric defect count 列；如果用户手动指定，则大小写不敏感解析列名。

### 3.2 BSL

- `read_bsl_table(path)`：读取 BSL 文件，兼容 `Defect type` / `Defect_Type` / `Defect` 和 `BSL count` / `BSL_count` / `BSL` 等常见列名。
- `build_bsl_lookup(bsl)`：生成两个 lookup：
  - `stage_lookup[(defect, stage, step)] = bsl`
  - `defect_lookup[defect] = bsl`
- `get_bsl_count(...)`：普通 process 使用，优先 stage-specific BSL，找不到时回退全局 defect BSL。
- `get_special_bsl_count(...)`：特殊 Step-only 合并组使用，优先全局 defect BSL；没有全局 BSL 时取参与 stage 的最大 stage-specific BSL。
- `normalize_bsl_source(value)`：规范化 `file` / `calculated_mean` 两种 BSL 来源。
- `calculate_mean_bsl(...)`：在已选择的数据窗口内，按当前 outlier 方式处理该 defect 的全部 Tool 数据后取整体 Mean。该值作为 defect 全局 BSL。

### 3.3 Equipment/Chamber 聚合

`add_grouping_columns(df)` 生成辅助列：

- `Process_Stage = Stage_ID + "_" + Step_ID`
- `Equipment_Group = Equipment_ID`
- `Chamber_Group`：仅 `KE`、`KT` 开头时使用 `Chamber_ID`，其他为空。
- `Group_Level`：`Chamber` 或 `Equipment`。
- `Tool_Group`：`KE`、`KT` 为 `Equipment_ID + "::" + Chamber_ID`；其他为 `Equipment_ID`。
- `Wafer_Key = Lot_ID + "::" + Wafer_NO`
- `Scan_Time_Parsed`

当前 chamber 前缀在文件顶部配置：

```python
CHAMBER_PREFIXES = ("KE", "KT")
```

非 chamber 前缀默认按整机聚合。若未来要严格限制未知前缀，应在 `add_grouping_columns()` 中增加校验。

### 3.4 Outlier 处理

`handle_outliers_for_defect(df, defect_col, outlier_sigma, outlier_handling)` 对每个 defect 单独处理：

```text
upper_limit = mean + outlier_sigma * population_std
```

仅处理高端 outlier，不处理低端点。标准差使用 `ddof=0`。`filter` 删除超过上限的行；`cap` 保留行并把 defect count 截断为上限。旧接口 `filter_outliers_for_defect()` 保留兼容，固定使用 `filter`。

### 3.5 特殊 Process 规则

类型定义：

```python
SpecialProcessRules = Dict[str, Dict[str, Optional[Set[str]]]]
```

解析入口：

```python
parse_special_process_rules(raw)
```

规则示例：

```text
Defect Type1: STG01_STEP10, STG02_STEP10; Defect Type2: STEP30
```

解析结果含义：

- `rules["defect type1"]["STEP10"] = {"STG01", "STG02"}`：只合并指定 stage 的 STEP10。
- `rules["defect type2"]["STEP30"] = None`：合并该 defect 下所有 STEP30。

应用入口：

```python
apply_special_process_rules(df, defect_col, special_process_rules)
```

该函数会把命中的行改写为：

```text
Stage_ID = SPECIAL_STEP_ONLY
Process_Stage = Step-only | Step_ID=<Step_ID>
```

注意：特殊规则在 `handle_outliers_for_defect()` 之后、groupby 之前执行，因此不会影响每个 defect 的 outlier 全局判断，但会影响后续 groupby、wafer count、BSL threshold 和输出。

### 3.6 Process Aggregation

新增全局 process 聚合模式：

```python
PROCESS_AGGREGATION_STAGE_STEP = "stage_step"
PROCESS_AGGREGATION_STEP = "step"
```

入口函数：

```python
normalize_process_aggregation(value)
apply_process_aggregation(df, process_aggregation)
```

行为：

- `stage_step`：默认模式，保留 `Stage_ID + Step_ID` 作为 process 分组。
- `step`：忽略所有 `Stage_ID`，把 `Stage_ID` 改写为 `ALL_STAGES`，`Process_Stage` 改写为 `Step-only | Step_ID=<Step_ID>`，后续 groupby 只会对每个 `Step_ID + tool/chamber` 输出一次。

该逻辑在 `apply_special_process_rules()` 之后执行。因此当全局 `step` 模式开启时，特殊 process rules 不会再额外拆分 stage；所有 stage 都会按 Step_ID 合并。

### 3.7 Worse Tool 判定

`summarize_one_defect()` 是单 defect 的核心计算入口：

1. 按 `outlier_handling` 删除或封顶 outlier。
2. 应用特殊 process 合并。
3. 应用全局 process aggregation。
4. 按 `Stage_ID`、`Step_ID`、`Equipment_Group`、`Chamber_Group`、`Group_Level`、`Tool_Group` 聚合。
5. 计算 `Mean_Count`、`Median_Count`、`Max_Count`、`Wafer_Count`、`Row_Count`。
6. 过滤 `Wafer_Count < min_wafers`。
7. 查 BSL。
8. 保留 `Mean_Count >= BSL * bsl_multiplier` 或 `Median_Count >= BSL * bsl_multiplier` 的组。

`build_worse_tool_result()` 是完整分析入口，循环处理所有 defect 并 concat 结果。`bsl_source="file"` 时读取外部 BSL；`bsl_source="calculated_mean"` 时不要求 `bsl_path`，并为每个 defect 生成一个全局 Mean BSL。输出通过 `BSL Source` 标记实际来源。

### 3.8 输出

- `write_result_to_excel(result, output_path, sheet_name, write_mode)`：
  - `append`：读取目标 sheet 历史内容，concat 后替换目标 sheet。
  - `replace`：只替换目标 sheet，保留 workbook 其他 sheet。
- `append_result_to_excel(...)`：旧接口兼容，内部固定使用 append。

### 3.9 命令行参数

`parse_args()` 定义命令行入口。新增参数时应同步更新：

- `README.md`
- UI 的 `_collect_analysis_options()`
- 如果影响 PPT 上下文，也更新 `ppt_integration.py` 的 dataclass

当前特殊规则命令行参数：

```powershell
--special-process-rules "Defect Type1: STG01_STEP10, STG02_STEP10"
```

当前 process 聚合命令行参数：

```powershell
--process-aggregation stage_step
--process-aggregation step
```

当前 BSL 来源参数：

```powershell
--bsl-source file --bsl demo_bsl.csv
--bsl-source calculated_mean
```

## 4. defect_worse_ui.py 结构

`DefectWorseToolApp` 是 Tkinter 主窗口。

主要区域：

- `_build_run_tab()`：文件选择、算法参数、特殊 process rules、一键运行、结果预览。
- `_build_chart_tab()`：图表参数、左侧滚动控制面板、Matplotlib canvas。
- `_configure_style()`：ttk 样式。

### 4.1 线程模型

Tkinter 主线程不能执行耗时 pandas/PPT 任务，否则 UI 会卡死。当前模式：

```text
Button callback
  -> 启动 daemon worker thread
  -> worker 将结果放入 result_queue
  -> _poll_results() 在主线程消费 queue
  -> 主线程更新控件或弹窗
```

新增耗时任务时，请遵循该模式。不要在 worker thread 中调用 `messagebox`、修改 `StringVar` 或直接操作 widget。

### 4.2 分析流程 UI

- `start_analysis()`：入口，校验 UI 状态并启动后台线程。
- `_collect_analysis_options()`：从 UI 读取并校验参数；特殊 process rules 在这里解析，格式错误会提示用户。
- `process_aggregation`：Run 页下拉框，默认 `Stage_ID + Step_ID`；选择 `Step_ID only` 时传给 `build_worse_tool_result(..., process_aggregation="step")`。
- `bsl_source`：Run 页下拉框。`file` 模式要求 BSL 文件；`calculated_mean` 模式禁用 BSL 文件控件并使用 defect-wide Mean。
- `_analysis_worker()`：调用 `build_worse_tool_result()` 和 `write_result_to_excel()`，然后重新加载 raw data 用于图表。
- `_show_result_preview()`：显示前 500 行结果。

### 4.3 图表流程 UI

- `start_plot()`：校验 defect、process、time column、Y scale、特殊规则。
- `_plot_worker()`：后台准备图表数据。
- `_poll_results()`：收到 queue kind 后调用对应绘图方法。

图表方法：

- `_draw_box()`：由 `ChartViewMixin` 实现，复用近期 Tool 排名；根据每组可用像素宽度选择顶部统计带、独立侧栏或滚动详情表。Raw-data 散点均为黑色。
- `_filter_chart_group_mode()`：创建独立 `Chart_Group`。`By Chamber` 直接使用 `Chamber_ID`，`By Equipment ID` 直接使用 `Equipment_ID`，不改变核心 Worse Tool 的 `Tool_Group`。
- `_filter_chart_process()`：直接复用核心层的 `apply_special_process_rules()` 和 `apply_process_aggregation()`，保证 special process 的 Chart 与 Worse Tool 使用同一批数据。
- `add_equal_spacing_index()`：在每个 Tool 内按 `Selected_Time` 稳定排序后使用 `cumcount()+1`，每一行占一个 X 位置；禁止按唯一时间 factorize，也禁止 groupby mean 合并数据点。
- `build_equal_spacing_time_ticks()` / `sample_tick_labels()`：生成真实时间刻度，并按绘图区宽度抽样，始终保留首尾时间。
- `_render_chart()` / `_render_side()`：在 `chart_view.py` 创建主图与独立侧栏；根据文本像素宽高判断可读性，密集屏幕图转到 Tool Details，导出则扩大物理尺寸并保留完整列表。
- `_draw_trend()` / `_draw_trend_all_chambers()`：共用逐 Tool 的等距观测序号轴。`_update_overlay_ticks()` 显示选中 Tool 的真实时间，默认取最长序列；不能将这些刻度解释为各 Tool 的共同时间。
- `_draw_trend_sequence_by_tool()`：按 Tool 分段连续拼接的 Trend。每个 Tool 内按时间排序，Tool 之间加虚线分隔，相邻点距离恒为 1，名称放在右侧栏，Y 轴共用。
- `annotate_chart_data()`：在 `chart_context.py` 生成共同的近期排序并存入 DataFrame.attrs；仅历史窗口存在的 Tool 按 ID 追加。
- `_colors()`：颜色方案。
- `_jitter_positions()`：Box chart 散点抖动。
- `_get_y_limits()` / `_apply_y_limits()`：用户自定义 Y min/Y max。
- `save_png()`：保存当前图为 PNG。

### 4.4 特殊 Process 在 UI 中的使用

Run 页和 Charts 页共用 `self.special_step_rules`。命名沿用历史变量名，但实际内容是 special process rules。

Charts 下拉框刷新：

```python
_refresh_process_stage_options()
```

如果当前 defect 有特殊规则，会额外加入：

```text
Step-only | Step_ID=<Step_ID> (ignore Stage_ID)
```

绘图筛选：

```python
_filter_chart_process(df, defect, selected_process, special_rules)
```

如果特殊规则是 `STG01_STEP10, STG02_STEP10`，画图只取这两个 stage 的 STEP10；如果规则是 `STEP10`，画图取该 defect 下所有 STEP10。

## 5. ppt_integration.py 接口

UI 中的 `Run PPT Generator` 最终调用：

```python
run_ppt_generation(context, log_callback=None)
```

`PPTGenerationContext` 字段：

- `raw_data_path`
- `bsl_path`
- `worse_result_path`
- `ppt_output_path`
- `input_sheet`
- `result_sheet`
- `defect_columns`
- `bsl_multiplier`
- `min_wafers`
- `outlier_sigma`
- `selected_defect`
- `selected_process_stage`

内网接入模板：

```python
from pathlib import Path


def run_ppt_generation(context, log_callback=None):
    if log_callback:
        log_callback("Generating PPT report...")

    from internal_ppt_script import create_ppt_report

    create_ppt_report(
        raw_data_path=context.raw_data_path,
        result_excel_path=context.worse_result_path,
        result_sheet=context.result_sheet,
        output_pptx=context.ppt_output_path,
        defect_type=context.selected_defect,
        process_stage=context.selected_process_stage,
    )

    return Path(context.ppt_output_path)
```

要求：

- 成功时返回最终 `.pptx` 路径。
- 返回前确保文件已创建。
- 失败时直接抛异常，UI 会捕获并弹窗。
- 不要在该函数里访问 Tkinter 控件。
- 不要调用 `sys.exit()`。

## 6. 常见修改点

### 新增输出字段

1. 修改 `summarize_one_defect()` 的 `.agg()` 或后处理逻辑。
2. 将字段加入 `output_cols`。
3. 如需 UI 预览，修改 `_build_run_tab()` 中的 `columns`。
4. 更新 `README.md` 和本文档。

### 修改 tool/chamber 前缀规则

修改 `defect_worse_tool.py` 顶部：

```python
WHOLE_TOOL_PREFIXES = ("KP", "KD", "KW")
CHAMBER_PREFIXES = ("KE", "KT")
```

当前实际 chamber 判断只依赖 `CHAMBER_PREFIXES`。

### 新增图表类型

1. 在 `_build_chart_tab()` 的 chart type combobox 中增加名称。
2. 在 `_plot_worker()` 中准备数据并投递新的 queue kind。
3. 在 `_poll_results()` 中处理新的 kind。
4. 新增 `_draw_xxx()`，只在主线程绘图。

### 调整特殊 Process 格式

主要修改：

- `parse_special_process_rules()`
- `_split_process_token()`
- `apply_special_process_rules()`
- UI 中 `_refresh_process_stage_options()` 和 `_filter_chart_process()`

## 7. 验证命令

语法检查：

```powershell
python -m py_compile defect_worse_tool.py defect_worse_ui.py ppt_integration.py generate_demo_data.py
```

命令行冒烟测试：

```powershell
python defect_worse_tool.py `
  --input demo_defect_data.csv `
  --bsl demo_bsl.csv `
  --output developer_test.xlsx `
  --write-mode replace
```

特殊 process 冒烟测试：

```powershell
python defect_worse_tool.py `
  --input demo_defect_data.csv `
  --bsl demo_bsl.csv `
  --output developer_special_test.xlsx `
  --special-process-rules "Defect Type1: STG01_STEP10, STG02_STEP10" `
  --write-mode replace
```

UI 测试：

```powershell
python defect_worse_ui.py
```

确认 Run 页能运行，Charts 页能画四种图，Y min/Y max、特殊 Step-only 下拉项和保存 PNG 正常。
