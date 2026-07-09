# Defect Worse Tool Cross 使用说明

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

## 4. 核心计算规则

1. `KP`、`KD`、`KW` 开头的 `Equipment_ID` 按整机聚合。
2. `KE`、`KT` 开头的 `Equipment_ID` 按 `Equipment_ID + Chamber_ID` 聚合。
3. 默认 process stage 使用 `Stage_ID + "_" + Step_ID`。
4. 如果 `Process aggregation` 选择 `Step_ID only`，则忽略 `Stage_ID`，直接按 `Step_ID + tool/chamber` 聚合；输出中每个 Step_ID 的 worse tool 只列一次，`Stage_ID` 显示为 `ALL_STAGES`。
5. `Analysis data window` 可选择全部数据、近两周或近一周。窗口按输入数据中最大的 `Scan_Time` 往前回推，不按电脑当天日期计算。
6. 每个 defect 单独过滤高端 outlier，默认过滤 `mean + 3 * std` 以上的点。
7. 每个 process/tool 组内 unique wafer 数小于 `Minimum wafers` 时过滤掉，默认 5。
8. 组内平均值或中位数大于等于 `BSL count * BSL multiplier` 时输出，默认倍数 1.5。
9. 输出新增 `Recent Trimmed BSL`，基于当前分析窗口内该 defect 的全部数据，去掉上下各 5% 后取均值，用于观察近期 BSL 水平。

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
2. 选择 BSL 文件。
3. 指定输出 Excel 路径。
4. 按需设置 input/output sheet、BSL multiplier、Minimum wafers、Outlier sigma。
5. `Process aggregation` 默认 `Stage_ID + Step_ID`；如需跨 stage 按相同 recipe/tool 对比，选择 `Step_ID only`。
6. `Analysis data window` 默认 `Latest 2 weeks`，也可选 `Latest 1 week` 或 `All data`。
7. `Defect columns` 可留空自动识别，也可逗号指定。
8. `Special process rules` 可留空；需要特殊 Step-only 逻辑时按第 5 节格式填写。
9. 选择写入模式：
   - `Append`：读取目标 sheet 历史结果并追加。
   - `Replace sheet`：只替换目标 sheet，保留 workbook 其他 sheet。
10. 点击 `Run Worse Tool`。

### Charts 页

先加载 raw data，再选择 defect type、process stage、time column、chart data window 和 chart type。`Chart data window` 支持 `All data`、`Latest 2 weeks`、`Latest 1 week`，同样按数据中最大的 `Scan_Time` 往前回推。

图表类型：

- `Box chart by tool`：按 tool/chamber 展示 box plot。tool 数很多时自动使用 `T1/T2/...` 编号，并在右侧显示编号映射；图上显示 `n`、`med`、`avg`。
- `Trend overlay by time`：所有 tool/chamber 按真实时间叠加到同一坐标系。
- `Trend all chambers same axis`：所有 chamber 放在同一个坐标系对比。
- `Sequential trend by tool`：第一个 tool 按时间排序画完后接第二个 tool，再接第三个 tool；所有 tool 共用同一个 Y 轴，方便比较。

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
  --process-aggregation step `
  --data-window 14d `
  --special-process-rules "Defect Type1: STG01_STEP10, STG02_STEP10" `
  --write-mode replace
```

`--process-aggregation stage_step` 是默认模式，按 `Stage_ID + Step_ID` 计算；`--process-aggregation step` 会忽略 Stage，只按 Step_ID 计算和输出。

`--data-window all` 使用全部数据；`--data-window 14d` 使用最新 Scan_Time 往前 14 天；`--data-window 7d` 使用最新 Scan_Time 往前 7 天。

手动指定 defect 列：

```powershell
--defect-cols "Defect Type1,Defect Type2"
```

## 8. 输出字段

```text
Defect type
BSL count
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
Recent Trimmed BSL
Data Window
Trigger
```

`Chamber ID` 仅在 `KE`、`KT` 按 chamber 聚合时输出；整机聚合时为空。

## 9. PPT 接口

`Run PPT Generator` 是预留接口。UI 中需要填写：

- `PPT output path`
- `PPT template`
- `Input image`

点击按钮后会在后台线程调用 `ppt_integration.py`，并把以上三个路径传给：

```python
run_external_ppt_method(ppt_output_path, ppt_template_path, input_image_path, log_callback)
```

默认实现会提示尚未配置。复制到内网后，只需要替换 `ppt_integration.py` 中的 `run_external_ppt_method()`，接入自己的 PPT 生成方法即可。运行过程中可调用 `log_callback("message")` 打印日志，日志会显示在 UI 状态栏并输出到控制台。
