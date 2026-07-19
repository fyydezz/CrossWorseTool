from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_PDF = PROJECT_DIR / "output" / "pdf" / "CrossWorseTool_UI_User_Guide.pdf"
FONT_PATHS = [
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
    Path(r"C:\Windows\Fonts\simsun.ttc"),
]


def register_font() -> str:
    for font_path in FONT_PATHS:
        if font_path.exists():
            pdfmetrics.registerFont(TTFont("CNFont", str(font_path)))
            return "CNFont"
    return "Helvetica"


def p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text.replace("\n", "<br/>"), style)


def bullets(items, style: ParagraphStyle) -> ListFlowable:
    return ListFlowable(
        [ListItem(p(item, style), leftIndent=8) for item in items],
        bulletType="bullet",
        leftIndent=16,
        bulletFontName=style.fontName,
        bulletFontSize=style.fontSize,
    )


def numbered(items, style: ParagraphStyle) -> ListFlowable:
    return ListFlowable(
        [ListItem(p(item, style), leftIndent=10) for item in items],
        bulletType="1",
        leftIndent=18,
        bulletFontName=style.fontName,
        bulletFontSize=style.fontSize,
    )


def make_table(rows, font_name: str, widths=None) -> Table:
    cell_style = ParagraphStyle(
        "TableCellCN",
        fontName=font_name,
        fontSize=8.3,
        leading=12,
        textColor=colors.HexColor("#1F2D3A"),
        wordWrap="CJK",
    )
    header_style = ParagraphStyle(
        "TableHeaderCN",
        parent=cell_style,
        textColor=colors.HexColor("#123047"),
    )
    wrapped_rows = []
    for row_index, row in enumerate(rows):
        style = header_style if row_index == 0 else cell_style
        wrapped_rows.append([p(str(cell), style) for cell in row])
    table = Table(wrapped_rows, colWidths=widths, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F0F6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#123047")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B7C3CF")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def add_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("CNFont", 8)
    canvas.setFillColor(colors.HexColor("#657485"))
    canvas.drawString(1.6 * cm, 1.05 * cm, "CrossWorseTool UI 使用指南")
    canvas.drawRightString(19.4 * cm, 1.05 * cm, "Page {}".format(doc.page))
    canvas.restoreState()


def build_pdf() -> None:
    font_name = register_font()
    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "TitleCN",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=22,
        leading=30,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#123047"),
        spaceAfter=18,
    )
    h1 = ParagraphStyle(
        "Heading1CN",
        parent=styles["Heading1"],
        fontName=font_name,
        fontSize=15,
        leading=21,
        textColor=colors.HexColor("#0F3A5A"),
        spaceBefore=12,
        spaceAfter=8,
    )
    h2 = ParagraphStyle(
        "Heading2CN",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=12,
        leading=17,
        textColor=colors.HexColor("#245B78"),
        spaceBefore=8,
        spaceAfter=5,
    )
    body = ParagraphStyle(
        "BodyCN",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9.5,
        leading=15,
        alignment=TA_LEFT,
        spaceAfter=6,
    )
    small = ParagraphStyle(
        "SmallCN",
        parent=body,
        fontSize=8.5,
        leading=13,
        textColor=colors.HexColor("#4F5F6F"),
    )

    story = []
    story.append(p("CrossWorseTool UI 使用指南", title))
    story.append(p("面向使用者的操作说明 - 适用于 Defect Worse Tool Cross 图形界面", body))
    story.append(Spacer(1, 0.25 * cm))
    story.append(
        make_table(
            [
                ["适用对象", "需要用 UI 跑 worse-tool 分析、查看 box/trend chart、调用外部 PPT 方法的用户"],
                ["推荐环境", "Python 3.8；先执行 python -m pip install -r requirements.txt"],
                ["启动方式", "在项目目录运行：python defect_worse_ui.py"],
                ["核心输入", "Raw defect data、BSL file、Output Excel；PPT 功能另需 PPT output/template/image folder 三个路径"],
            ],
            font_name,
            widths=[3.4 * cm, 12.6 * cm],
        )
    )

    story.append(p("1. 启动 UI", h1))
    story.append(
        numbered(
            [
                "打开 PowerShell，进入项目目录，例如：cd \"D:\\python demo\\DefectWorseToolCross\"。",
                "如果使用虚拟环境，先激活环境并安装依赖：python -m pip install -r requirements.txt。",
                "运行：python defect_worse_ui.py。",
                "窗口打开后，默认包含两个页签：Run Worse Tool 和 Charts。",
            ],
            body,
        )
    )

    story.append(p("2. Run Worse Tool 页：一键计算 worse tool", h1))
    story.append(p("推荐先在 Run Worse Tool 页完成数据文件、参数和输出路径设置，再点击 Run Worse Tool。", body))
    story.append(
        make_table(
            [
                ["控件", "怎么填", "说明"],
                ["Raw defect data", "选择 .csv/.xlsx/.xlsm/.xls", "原始 defect count 数据。必要字段大小写不敏感，LOT_ID 等全大写也支持。"],
                ["BSL file", "选择 BSL csv/excel", "至少包含 Defect type 和 BSL count。"],
                ["Output Excel", "选择输出 .xlsx", "分析结果写入该 Excel。Append 会追加，Replace sheet 会替换目标 sheet。"],
                ["Input sheet", "可空或填 sheet 名/序号", "CSV 可留空；Excel 默认读取第 0 个 sheet。"],
                ["Output sheet", "默认 worse_tool", "结果写入的 sheet 名。"],
                ["BSL multiplier", "默认 1.5", "Mean 或 Median 达到 BSL * multiplier 时判定为 worse。"],
                ["Minimum wafers", "默认 5", "每个 process/tool 分组少于该 wafer 数会被过滤。"],
                ["Outlier sigma", "默认 3.0", "每个 defect 的高点上限为 mean + sigma * std。"],
                ["Outlier handling", "Remove 或 Cap", "Remove 删除超过上限的行；Cap 保留行并把高点替换为上限。"],
            ],
            font_name,
            widths=[3.2 * cm, 4.2 * cm, 8.6 * cm],
        )
    )

    story.append(p("3. Process 和时间窗口参数", h1))
    story.append(
        make_table(
            [
                ["参数", "选项", "使用建议"],
                ["Process aggregation", "Stage_ID + Step_ID", "默认模式；每个 Stage + Step 单独比较。"],
                ["Process aggregation", "Step_ID only", "当多个 stage 的 tool 和 recipe 完全相同时使用；输出中同一 Step_ID 的 worse tool 只列一次，Stage_ID 显示为 ALL_STAGES。"],
                ["Analysis data window", "All data", "使用全部 Scan_Time 数据。"],
                ["Analysis data window", "Latest 2 weeks", "默认建议；按数据中最大 Scan_Time 往前 14 天筛选。"],
                ["Analysis data window", "Latest 1 week", "只看最新 7 天表现。"],
            ],
            font_name,
            widths=[4.2 * cm, 4.0 * cm, 7.8 * cm],
        )
    )
    story.append(
        p(
            "注意：Latest 2 weeks / Latest 1 week 是按输入数据里的最大 Scan_Time 回推，不是按电脑当天日期回推。因此历史数据也可以稳定复现。",
            small,
        )
    )

    story.append(p("4. Special process rules", h1))
    story.append(p("如果只有部分特殊 process 需要忽略 Stage_ID，可填写 Special process rules。", body))
    story.append(
        make_table(
            [
                ["写法", "含义"],
                ["Defect Type1: STG01_STEP10, STG02_STEP10", "仅把 Defect Type1 下这两个 Stage 的 STEP10 合并比较。"],
                ["Defect Type2: STEP30", "把 Defect Type2 下所有 Stage 的 STEP30 都合并比较。"],
                ["留空", "不启用特殊合并逻辑。"],
            ],
            font_name,
            widths=[7.0 * cm, 9.0 * cm],
        )
    )

    story.append(p("5. 结果输出怎么读", h1))
    story.append(
        make_table(
            [
                ["字段", "说明"],
                ["Defect type", "当前 defect count 列名。"],
                ["BSL count", "从 BSL 文件中读取到的 BSL。"],
                ["Stage_ID / Step_ID", "当前 process。Step_ID only 模式下 Stage_ID 为 ALL_STAGES。"],
                ["Equipment ID / Chamber ID", "KP/KD/KW 按整机；KE/KT 按 chamber。"],
                ["Mean_Count / Median_Count", "当前分组的均值和中位数。"],
                ["Wafer_Count", "当前分组 unique wafer 数。"],
                ["Outlier Handling", "本次异常值使用 filter 删除还是 cap 封顶。"],
                ["Recent Trimmed BSL", "当前分析窗口内该 defect 的全部数据，去掉上下各 5% 后取均值，用于观察近期 BSL 水平。"],
                ["Data Window", "本次使用 all、14d 或 7d 哪个数据窗口。"],
                ["Trigger", "触发原因，mean 或 median。"],
            ],
            font_name,
            widths=[4.5 * cm, 11.5 * cm],
        )
    )

    story.append(PageBreak())
    story.append(p("6. Charts 页：查看图表", h1))
    story.append(
        numbered(
            [
                "先在 Run 页加载 raw data，或在 Charts 页点击 Browse / Load Raw Data。",
                "选择 Defect type。",
                "选择 Process stage。如果启用了 Step_ID only 或特殊规则，会看到 Step-only | Step_ID=... 选项。",
                "选择 Time column，通常使用 Scan_Time。",
                "选择 Chart data window：All data、Latest 2 weeks 或 Latest 1 week。",
                "选择 Outlier handling，并选择 By Chamber 或 By Equipment ID。每个 process 只要对应字段非空，都可以使用两种分组方式。",
                "选择 Chart type 后点击 Plot。",
            ],
            body,
        )
    )
    story.append(
        make_table(
            [
                ["图表类型", "用途"],
                ["Box chart by selected group", "按中位数从高到低排列；保留 raw data，并根据 Box 密集程度自适应显示 N、Median、Mean。"],
                ["Trend overlay by time", "所有 tool/chamber 按真实 Scan_Time 叠加到同一坐标系。"],
                ["Trend all groups same axis", "所有选定的 Chamber 或 Equipment ID 放在同一坐标系对比。"],
                ["Sequential trend by selected group", "第一个 group 按时间画完后接第二个 group，所有 group 共用同一 Y 轴。"],
            ],
            font_name,
            widths=[4.8 * cm, 11.2 * cm],
        )
    )
    story.append(
        p(
            "Chart grouping 是独立观察口径：By Chamber 直接按 Chamber_ID 分组，By Equipment ID 直接按 Equipment_ID 分组；不会改变 Worse Tool 的设备前缀聚合规则。",
            small,
        )
    )

    story.append(p("7. 图表样式和保存", h1))
    story.append(
        bullets(
            [
                "Line width：调整 trend chart 线宽。",
                "Marker size：调整点大小；设为 0 可以隐藏 marker。",
                "Color：选择 Tableau、Viridis、Plasma 或 Custom single。",
                "Y min / Y max：手动固定 Y 轴范围；留空则自动缩放。",
                "Save PNG：把当前图保存为 PNG。",
                "左侧控制区可滚动；如果看不到底部按钮，请滚动左侧面板。",
            ],
            body,
        )
    )

    story.append(p("8. PPT Generator 按钮", h1))
    story.append(p("PPT 按钮是预留给外部 PPT 方法的接口。使用前需要填写三个路径。", body))
    story.append(
        make_table(
            [
                ["控件", "说明"],
                ["PPT output path", "最终生成的 .pptx 路径。"],
                ["PPT template", "你的 PPT 模板文件，支持 .pptx/.pptm/.potx。"],
                ["Input image folder", "包含待处理图片的文件夹路径。"],
                ["Run PPT Generator", "点击后在后台线程调用 ppt_integration.py 中的 run_external_ppt_method(output, template, image_folder, log_callback)。"],
            ],
            font_name,
            widths=[4.5 * cm, 11.5 * cm],
        )
    )
    story.append(
        p(
            "日志：外部方法运行时可以调用 log_callback(\"message\")。日志会显示在 UI 底部状态栏，并打印到控制台。",
            body,
        )
    )

    story.append(p("9. 常见问题", h1))
    story.append(
        make_table(
            [
                ["问题", "处理方式"],
                ["提示缺少字段", "确认输入文件包含 Lot_ID、Wafer_NO、Scan_Time、Stage_ID、Step_ID、Equipment_ID、Chamber_ID。全大写表头也支持。"],
                ["没有 worse-tool 输出", "检查 BSL 是否过高、Minimum wafers 是否过大、数据窗口是否太窄。"],
                ["近两周结果为空", "确认 Scan_Time 能被解析；窗口按最大 Scan_Time 往前回推。"],
                ["图表 process 下拉为空", "先加载 raw data，或确认 defect 数据字段可被识别。"],
                ["PPT 按钮报未配置", "这是正常占位行为；需要在 ppt_integration.py 中替换 run_external_ppt_method()。"],
            ],
            font_name,
            widths=[4.5 * cm, 11.5 * cm],
        )
    )

    doc = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.6 * cm,
        title="CrossWorseTool UI 使用指南",
        author="CrossWorseTool",
    )
    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    print(OUTPUT_PDF)


if __name__ == "__main__":
    build_pdf()
