# Defect Worse Tool Cross 使用说明

## 2026-09-19 两项修复

- `Recent Trimmed BSL` 对照列固定使用完整输入中最新 Scan_Time 往前 14 天的数据（含边界），不足两周时使用可用的全部数据；仅在该数值计算中排除 5% 分位数以下和 95% 分位数以上的数据。选择 All data、Latest 2 weeks 或 Latest 1 week 不再改变这一对照窗口。它不使用 3σ 清洗后的数据，也不会影响 Worse Tool 的片数、均值、中位数或图表数据。Append 的历史行不会自动回算。
- 连续点击 `Plot Chart` 时只接受最后一次请求的结果；旧请求的报错也会忽略。加载新文件、启动分析或 PPT 时会使此前画图请求失效。画图状态显示本次 Defect、layer、分组和时间窗口；加载/分析/PPT 运行中暂不接受新的画图请求。已开始的旧计算可能继续在后台完成，但不会更新画面。

由于该对照列必须定位最近 14 天，Scan_Time 无法解析时即使分析选择 All data，也会提示修正时间，而不是悄悄省略这些行。近期窗口仍相对于文件最新时间，不是电脑当天日期。

## 2026-09-12 图表与选色更新

- **所有 Trend 均按数据点等距**，不再提供时间等距模式。每个 Tool 按所选时间列稳定排序；同一时间的不同 wafer 仍是独立点。Overlay 中每个 Tool 都从 1 开始；Sequential 则按 Tool 连续拼接，跨 Tool 的相邻点距离也为 1。
- Overlay 同一横坐标上的不同 Tool **不代表同一时刻**。X 轴默认显示点数最多 Tool 的真实时间，并注明 `dates for T编号`。点击另一根线或在 `Tool Details` 中选中 Tool，时间刻度切换到该 Tool；悬停任何点可查看完整 Tool、实际时间、count、Lot 和 Wafer。
- Box 与 Trend 共用 Tool 顺序：按最近 14 天的中位数降序、均值降序；仅历史窗口出现的 Tool 按 ID 追加。T 编号在同一 Defect/layer/分组方式中保持一致。Box 的红蓝颜色仍按当前绘图数据的高低排名，因此选择其他 Box 窗口时，颜色排名和横向顺序可能不同。
- 点击 Box、曲线或 `Tool Details` 表格行可高亮同一 Tool，切换图型仍保留高亮；`Clear highlight` 恢复全部显示。高亮和自定义风格仅保存在当前 UI 会话内。
- `Tool Details` 提供可上下、左右滚动的完整 Tool 表，包括 Rows、Unique wafers、Median、Mean。图表空间足够时直接标注统计值，否则放到侧栏；侧栏也放不下时改为详情窗口，不压缩到无法辨认。`Save PNG` 自动扩大输出尺寸并附完整 Tool 列表，不减少数据点。
- 主标题、数据窗口/清洗方式/行数/独立 wafer 数与参考值说明分区显示。`Chart Style` 中可独立开关 BSL、Worse threshold、Golden Mean 参考线；内置 PPT 同步这些开关。参考线使用当前 **Run 分析参数**，不读取 append Excel 历史记录，也不随 Box/Trend 显示窗口改变；Golden 使用核心分析的 Equipment/Chamber 聚合方式与最低片数门槛。缺少有效基准会标记 unavailable，而不是当作 0。
- 两个选色入口都新增“红色、黄色、蓝色、绿色、橙色、紫色、粉色、青色、黑色、灰色”名称及色块预览。修改单个 Tool：选中图形 → `Edit Selected` → 选择颜色、宽度 → `Apply`。全局统一线色：`Chart Style` → `Line palette = Custom single` → 选择颜色 → `Apply & Redraw`。保留自定义色值和选色器；默认 `Distinct` 仍给各条线分配不同颜色。

提示：近期窗口均相对于输入文件最大的 Scan_Time，而不是电脑当天日期；Rows 是数据行数，Unique wafers 按 Lot + Wafer 去重，两者不一定相等。上下各 5% 裁剪仅用于 Recent Trimmed BSL，不参与上述图表数据或参考线计算。

## Golden Tool 对照列

每个 Defect、每个当前 layer 的 Golden Tool 定义为：与本次分析相同时间窗口、相同清洗和聚合口径下，Mean_Count 最低的合格 Tool。有效片数按 `Lot_ID + Wafer_NO` 去重统计，至少 5 片；若 Minimum wafers 设置高于 5，则使用更高门槛。均值并列时依次按中位数更低、wafer 数更多、Tool ID 升序选定。

输出及结果预览新增 `Golden Equipment ID`、`Golden Chamber ID`、`Golden Mean_Count`、`Golden Wafer_Count`、`Mean minus Golden`、`Mean / Golden` 六列。整机分组的 Golden Chamber 留空。Golden Mean 为 0 时倍数留空，避免除零；没有合格候选时对照列留空。Golden 是本次数据中的相对参考，不保证低于 BSL，也可能与当前 Worse Tool 是同一 Tool。

Golden 在筛选 Worse Tool 之前从全部合格组中选择，沿用 Step-only 和特殊 layer 合并规则，不改变原有 Worse Tool 判定。Append 时历史行不回算，新列仅填入本次新增行。Box 的 Raw Data 全部改为黑色实心点，关闭额外的离群点标记以避免重复绘制；UI 和自动 PPT 共用这一绘图逻辑。

## 2026-09 更新

- BSL source 新增 `Latest 2 weeks mean`，无需 BSL 文件。固定取输入数据最新 Scan Time 往前 14 天的数据，按当前 3σ 删除/封顶方式处理后计算每个 Defect 的整体均值；该窗口独立于分析窗口，上下 5% 截尾不参与计算。
- `Generate Worse Tool PPT` 按当前 Run 参数重新计算命中结果，每个 Defect × layer 一页，标题为 `Defect type cross to layer name`。左侧 Box 使用最近 14 天，右侧 Sequential Trend 使用 All data。图中包含该 layer 全部 Tool 以便比较，清洗方式与 Run 一致。
- layer 默认 Stage + Step；Step-only 和特殊规则沿用分析时的合并口径。Charts 页的分组和时间列选择作用于 PPT。
- PPT output 必填。模板可留空，默认 16:9；提供模板则保留母版/主题和尺寸并替换示例页。Chart export folder 为生成图片的输出目录，留空自动创建在 PPT 旁边。日志输出至终端及 UI 状态栏。
- 部署时重新执行 `pip install -r requirements.txt`，新增依赖 `python-pptx>=0.6.21,<1.0.0`。
- Box 空间充足时在图内上方显示 N/Median/Mean，密集时使用右侧汇总；判断依据为每个 Box 可用像素宽度及字号。
- Result preview 按 Priority Score 降序：70% 为 Mean/BSL 的百分位排名，30% 为 unique wafer 数的百分位排名。仅用于本次优先级，不改变阈值，也不表示统计显著性。
- 默认 PPT 按钮已有内置实现。旧外部三路径方法仍保留给内网自定义，但不再要求用户自行实现才能生成 PPT。

## Chart Interaction (latest UI)

The Charts tab now separates workflow controls from visual styling:

1. Use the left panel to load data and select defect, process, grouping, chart type, time window, and outlier handling.
2. Select `Chart Style...` to open the resizable, vertically scrollable style dialog. Box labels (`Count`, `Median`, and `Mean`) can be shown or hidden independently.
3. Box and Trend share the latest-14-day median/mean ranking. Box colors indicate current-window rank from red (high) to blue (low); raw-data points remain black and visible.
4. Trend charts assign distinct shuffled colors to different lines by default. Global line width, marker size, palette, and Y-axis scale are configured in the style dialog.
5. Click a box or trend line, then select `Edit Selected` above the chart to change only that item's color and width.
6. Per-item styles remain active when the same chart context is redrawn during the current UI session.

The scrollable left panel is divided into `Data Source`, `View`, and `Data Preparation`. `Save PNG` is above the chart.

`Box chart > Label size` controls the Count/Median/Mean annotation font. Keep it at `0` for density-based automatic sizing, or enter a positive point size for a fixed font.

### Data completeness and trend spacing

- The upper/lower 5% trim is used only by `Recent Trimmed BSL`. It returns one BSL value and does not remove rows from worse-tool statistics or chart data.
- Trend preparation no longer averages rows that share the same Tool and Scan Time. Every valid input row becomes one plotted point after the explicitly selected time-window and outlier settings are applied.
- Both overlay Trend modes sort each Tool by the selected time column, then plot its observations at `1, 2, 3, ...`. Every adjacent point is exactly one X-axis unit apart; real-time gaps never affect horizontal spacing. Axis times belong to the selected reference Tool, not a shared calendar.
- A recent-window or Trend operation stops with an explicit error if Scan Time is invalid; rows are not silently discarded.
- Empty Chamber or Equipment IDs remain visible as `(Missing Chamber)` or `(Missing Equipment ID)`.
- CSV/Excel loading preserves identifiers such as `NA` and `N/A` instead of converting them to missing values.

---

本工具用于把某一扫描站点得到的 wafer defect count 数据，Cross 到不同 Process Stage 和 Equipment/Chamber，筛选 worse tool，并通过 UI 查看 Box chart 和 Trend chart。

## 1. 文件说明

- `defect_worse_tool.py`：核心分析脚本，也可命令行运行。
- `defect_worse_ui.py`：Tkinter 图形界面，可一键跑 worse-tool 分析并画图。
- `ppt_integration.py`：预留的 PPT 一键生成接口，方便内网接入自定义 PPT 脚本。
- `generate_demo_data.py`：生成 demo 数据。
- `requirements.txt`：Python 3.8 依赖。
- `README.md`：本文档，面向使用者。
- `DEVELOPER_GUIDE.md`：工程结构和二次开发说明。

## 2. 环境安装

建议使用 Python 3.8。

```powershell
cd "D:\python demo\DefectWorseToolCross"
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## 3. 输入数据格式

原始 defect 数据支持 `.csv`、`.xlsx`、`.xlsm`、`.xls`，必须包含以下字段。字段大小写不敏感，因此实际表头是全大写也可以。

```text
Lot_ID
Wafer_NO
Scan_Time
Stage_ID
Step_ID
Equipment_ID
Chamber_ID
```

除以上 metadata 字段外，其他可转换为数字的列会被自动识别为 defect count 列。也可以在 UI 或命令行手动指定 defect 列，例如：

```text
Defect Type1,Defect Type2
```

BSL 文件支持 `.csv` 或 Excel，至少需要：

```text
Defect type
BSL count
```

如果 BSL 文件同时包含 `Stage_ID` 和 `Step_ID`，程序会优先使用 stage-specific BSL；找不到时回退到 defect 全局 BSL。

`BSL source` 提供两种基准：

- `Input BSL file`：使用用户导入的 BSL 文件，保持原有 stage-specific/global BSL 逻辑。
- `Calculated defect mean (after outlier handling)`：BSL 文件可留空。程序在当前 `Analysis data window` 内，先按所选 3σ outlier 方式处理该 Defect 的全部 Tool 数据，再取整体 Mean 作为该 Defect 的全局 BSL。

计算 Mean BSL 与 `Recent Trimmed BSL` 是两个独立值。前者可参与 worse-tool 阈值判定；后者仍只用于输出观察，并只在自身计算时过滤上下各 5%。

## 4. 核心计算规则

1. `KP`、`KD`、`KW` 开头的 `Equipment_ID` 按整机聚合。
2. `KE`、`KT` 开头的 `Equipment_ID` 按 `Equipment_ID + Chamber_ID` 聚合。
3. 默认 process stage 使用 `Stage_ID + "_" + Step_ID`。
4. 如果 `Process aggregation` 选择 `Step_ID only`，则忽略 `Stage_ID`，直接按 `Step_ID + tool/chamber` 聚合；输出中每个 Step_ID 的 worse tool 只列一次，`Stage_ID` 显示为 `ALL_STAGES`。
5. `Analysis data window` 可选择全部数据、近两周或近一周。窗口按输入数据中最大的 `Scan_Time` 往前回推，不按电脑当天日期计算。
6. 每个 defect 单独过滤高端 outlier，默认过滤 `mean + 3 * std` 以上的点。
7. 每个 process/tool 组内 unique wafer 数小于 `Minimum wafers` 时过滤掉，默认 5。
8. 根据 `BSL source` 使用输入文件 BSL 或计算 Mean BSL；组内平均值或中位数大于等于 `BSL count * BSL multiplier` 时输出，默认倍数 1.5。
9. 输出 `Recent Trimmed BSL`，独立使用完整输入中最近 14 天该 defect 的数据，按上下 5% 分位数截尾后取均值；不足两周使用全部可用数据，与分析窗口无关。

## 5. 特殊 Process 规则

部分 process 存在不同 `Stage_ID` 但相同 `Step_ID`，需要忽略 Stage 直接按 Step 比较。工具支持在 UI 和命令行输入特殊规则。

规则格式：

```text
Defect Type1: STG01_STEP10, STG02_STEP10; Defect Type2: STEP30
```

含义：

- `STG01_STEP10, STG02_STEP10`：只把该 defect 下这两个 stage 的 `STEP10` 合并计算，其他同 Step 的 stage 仍按普通 stage 单独计算。
- `STEP30`：该 defect 下所有 `Step_ID=STEP30` 的数据都忽略 Stage 合并计算。
- 特殊合并后的输出中，`Stage_ID` 会显示为 `SPECIAL_STEP_ONLY`，`Step_ID` 保持原值。
- 特殊合并组的 BSL 优先使用 defect 全局 BSL；如果只有 stage-specific BSL，则取参与合并 stage 的最大 BSL，避免阈值偏松。

## 6. UI 使用

启动：

```powershell
python defect_worse_ui.py
```

### Run Worse Tool 页

1. 选择 raw defect data。
2. 选择 `BSL source`。使用 `Input BSL file` 时选择 BSL 文件；使用计算 Mean 时 BSL 文件可留空。
3. 指定输出 Excel 路径。
4. 按需设置 input/output sheet、BSL multiplier、Minimum wafers、Outlier sigma 和 Outlier handling。
5. `Process aggregation` 默认 `Stage_ID + Step_ID`；如需跨 stage 按相同 recipe/tool 对比，选择 `Step_ID only`。
6. `Analysis data window` 默认 `Latest 2 weeks`，也可选 `Latest 1 week` 或 `All data`。
7. `Defect columns` 可留空自动识别，也可逗号指定。
8. `Special process rules` 可留空；需要特殊 Step-only 逻辑时按第 5 节格式填写。
9. 选择写入模式：
   - `Append`：读取目标 sheet 历史结果并追加。
   - `Replace sheet`：只替换目标 sheet，保留 workbook 其他 sheet。
10. 点击 `Run Worse Tool`。

`Outlier handling` 支持两种口径：

- `Remove values above mean + N*sigma`：删除超过上限的行，保持原有逻辑。
- `Cap values at mean + N*sigma`：保留行和 wafer，只把超过上限的 defect count 替换为该上限。

### Charts 页

先加载 raw data，再选择 defect type、process stage、time column、chart data window、chart grouping 和 chart type。`Chart data window` 默认 `Latest 2 weeks`，也支持 `All data`、`Latest 1 week`，同样按数据中最大的 `Scan_Time` 往前回推。运行 Worse Tool 后，Chart data window 会自动同步为本次分析使用的窗口。

`Chart grouping` 必须二选一：`By Chamber` 直接按输入的 `Chamber_ID` 分组，`By Equipment ID` 直接按输入的 `Equipment_ID` 分组。只要对应字段非空，每个 process stage 都可以用两种方式画图。该选择是 Chart 的独立观察口径，不会修改 Worse Tool 中按设备前缀决定 Equipment/Chamber 的计算规则。

图表类型：

- `Box chart by selected group`：与 Trend 共用近期排名。少量 Tool 直接标注 Rows/Median/Mean；密集时使用右侧统计或可滚动详情表，保留全部黑色 raw data 点。
- `Trend overlay equal point spacing`：每个 Tool 独立按所选时间排序、逐点等距排列，重复时间不合并。X 轴显示当前参考 Tool 的真实时间。
- `Trend all tools equal point spacing`：同样使用逐 Tool 的点序号坐标，不按真实时间对齐；完整 Tool 名称可在右侧或 Tool Details 查看。
- `Sequential trend by selected group`：第一个 group 按时间排序画完后紧接第二个 group，再接第三个 group；相邻数据点距离固定为 1，X 轴显示真实时间，Tool 名称移至右侧栏，所有 group 共用同一个 Y 轴。

Chart style 支持：

- 调整线宽。
- 调整 marker 大小。
- 选择颜色方案或自定义颜色。
- 手动设置 `Y min` 和 `Y max`，留空则自动缩放。

Charts 左侧控制区带滚动条，参数较多时可向下滚动。

## 7. 命令行使用

```powershell
python defect_worse_tool.py `
  --input demo_defect_data.csv `
  --bsl demo_bsl.csv `
  --output worse_tool_result.xlsx `
  --output-sheet worse_tool `
  --bsl-multiplier 1.5 `
  --min-wafers 5 `
  --outlier-sigma 3.0 `
  --outlier-handling cap `
  --process-aggregation step `
  --data-window 14d `
  --special-process-rules "Defect Type1: STG01_STEP10, STG02_STEP10" `
  --write-mode replace
```

不使用 BSL 文件、改用计算 Mean BSL：

```powershell
python defect_worse_tool.py `
  --input demo_defect_data.csv `
  --bsl-source calculated_mean `
  --output worse_tool_result.xlsx `
  --data-window 14d `
  --outlier-handling cap `
  --write-mode replace
```

`--process-aggregation stage_step` 是默认模式，按 `Stage_ID + Step_ID` 计算；`--process-aggregation step` 会忽略 Stage，只按 Step_ID 计算和输出。

`--data-window all` 使用全部数据；`--data-window 14d` 使用最新 Scan_Time 往前 14 天；`--data-window 7d` 使用最新 Scan_Time 往前 7 天。

`--outlier-handling filter` 删除超过 sigma 上限的值；`--outlier-handling cap` 将超过上限的值替换为该上限。

手动指定 defect 列：

```powershell
--defect-cols "Defect Type1,Defect Type2"
```

## 8. 输出字段

```text
Defect type
BSL count
BSL Source
Stage_ID
Step_ID
Equipment ID
Chamber ID
Group_Level
Mean_Count
Median_Count
Max_Count
Wafer_Count
Row_Count
BSL Multiplier
Outlier Handling
Recent Trimmed BSL
Data Window
Trigger
```

`Chamber ID` 仅在 `KE`、`KT` 按 chamber 聚合时输出；整机聚合时为空。

## 9. PPT 接口

`Generate Worse Tool PPT` 默认调用内置生成器。UI 路径为：

- `PPT output path`
- `PPT template`
- `Chart export folder`（目录，不是单张图片）

点击按钮后在后台线程调用 `ppt_integration.run_ppt_generation(context, log_callback)`。如需接入内网自定义方法，在该函数中转调保留的三路径接口：

```python
run_external_ppt_method(ppt_output_path, ppt_template_path, input_image_path, log_callback)
```

`run_external_ppt_method()` 本身仍为占位方法；替换它并在 `run_ppt_generation()` 中转调即可接入。运行过程中可调用 `log_callback("message")` 打印日志，日志显示在 UI 状态栏并输出到控制台。内置 PPT 的密集图会等比例缩放以适应单页，查看细节请打开同时导出的完整 PNG。
