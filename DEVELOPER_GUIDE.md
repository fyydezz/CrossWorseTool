# Defect Worse Tool Cross 开发者文档

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
  -> read_bsl_table()
  -> build_bsl_lookup()
  -> 每个 defect 调用 summarize_one_defect()
  -> filter_outliers_for_defect()
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

### 3.4 Outlier 过滤

`filter_outliers_for_defect(df, defect_col, outlier_sigma)` 对每个 defect 单独过滤：

```text
upper_limit = mean + outlier_sigma * population_std
```

仅过滤高端 outlier，不过滤低端点。标准差使用 `ddof=0`。

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

注意：特殊规则在 `filter_outliers_for_defect()` 之后、groupby 之前执行，因此不会影响每个 defect 的 outlier 全局判断，但会影响后续 groupby、wafer count、BSL threshold 和输出。

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

1. 过滤 outlier。
2. 应用特殊 process 合并。
3. 应用全局 process aggregation。
4. 按 `Stage_ID`、`Step_ID`、`Equipment_Group`、`Chamber_Group`、`Group_Level`、`Tool_Group` 聚合。
5. 计算 `Mean_Count`、`Median_Count`、`Max_Count`、`Wafer_Count`、`Row_Count`。
6. 过滤 `Wafer_Count < min_wafers`。
7. 查 BSL。
8. 保留 `Mean_Count >= BSL * bsl_multiplier` 或 `Median_Count >= BSL * bsl_multiplier` 的组。

`build_worse_tool_result()` 是完整分析入口，循环处理所有 defect 并 concat 结果。

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
- `_analysis_worker()`：调用 `build_worse_tool_result()` 和 `write_result_to_excel()`，然后重新加载 raw data 用于图表。
- `_show_result_preview()`：显示前 500 行结果。

### 4.3 图表流程 UI

- `start_plot()`：校验 defect、process、time column、Y scale、特殊规则。
- `_plot_worker()`：后台准备图表数据。
- `_poll_results()`：收到 queue kind 后调用对应绘图方法。

图表方法：

- `_draw_box()`：Box chart。tool 数量多于 12 时自动用 `T1/T2/...` 短标签，并在右侧显示映射；图上显示 `n`、`med`、`avg`。
- `_filter_chart_group_mode()`：根据 UI 选择只保留 `Group_Level=Chamber` 或 `Group_Level=Equipment`，防止两类分组混在同一张图。
- `_filter_chart_process()`：直接复用核心层的 `apply_special_process_rules()` 和 `apply_process_aggregation()`，保证 special process 的 Chart 与 Worse Tool 使用同一批数据。
- `_draw_trend()`：普通真实时间 trend overlay。
- `_draw_trend_all_chambers()`：所有 chamber 同坐标系 trend。
- `_draw_trend_sequence_by_tool()`：按 tool 分段拼接的 trend。每个 tool 内按时间排序，tool 之间加虚线分隔，Y 轴共用。
- `_ordered_trend_groups()`：tool/chamber 排序。
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
