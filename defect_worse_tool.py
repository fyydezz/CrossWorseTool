from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = [
    "Lot_ID",
    "Wafer_NO",
    "Scan_Time",
    "Stage_ID",
    "Step_ID",
    "Equipment_ID",
    "Chamber_ID",
]

REQUIRED_COLUMN_LOOKUP = {column.upper(): column for column in REQUIRED_COLUMNS}
REQUIRED_COLUMN_LOOKUP.update(
    {
        "STAGE": "Stage_ID",
        "CHAMBER": "Chamber_ID",
    }
)
WHOLE_TOOL_PREFIXES = ("KP", "KD", "KW")
CHAMBER_PREFIXES = ("KE", "KT")
DEFAULT_SHEET_NAME = "worse_tool"
SPECIAL_STAGE_ID = "SPECIAL_STEP_ONLY"
STEP_ONLY_STAGE_ID = "ALL_STAGES"
SpecialProcessRules = Dict[str, Dict[str, Optional[Set[str]]]]
PROCESS_AGGREGATION_STAGE_STEP = "stage_step"
PROCESS_AGGREGATION_STEP = "step"
PROCESS_AGGREGATION_CHOICES = (PROCESS_AGGREGATION_STAGE_STEP, PROCESS_AGGREGATION_STEP)
DATA_WINDOW_ALL = "all"
DATA_WINDOW_14D = "14d"
DATA_WINDOW_7D = "7d"
DATA_WINDOW_CHOICES = (DATA_WINDOW_ALL, DATA_WINDOW_14D, DATA_WINDOW_7D)
DATA_WINDOW_DAYS = {
    DATA_WINDOW_14D: 14,
    DATA_WINDOW_7D: 7,
}


def normalize_column_name(name: object) -> str:
    return str(name).strip()


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    normalized = []
    for column in df.columns:
        name = normalize_column_name(column)
        normalized.append(REQUIRED_COLUMN_LOOKUP.get(name.upper(), name))
    if len(normalized) != len(set(normalized)):
        duplicates = sorted({name for name in normalized if normalized.count(name) > 1})
        raise ValueError(
            "Duplicate column(s) after header normalization: {}".format(", ".join(duplicates))
        )
    df.columns = normalized
    return df


def parse_sheet_name(sheet_name: Optional[str]) -> object:
    if sheet_name is None or str(sheet_name).strip() == "":
        return 0
    value = str(sheet_name).strip()
    if value.isdigit():
        return int(value)
    return value


def read_table(path: str, sheet_name: Optional[str] = None) -> pd.DataFrame:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return normalize_columns(pd.read_csv(file_path))
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return normalize_columns(pd.read_excel(file_path, sheet_name=parse_sheet_name(sheet_name)))
    raise ValueError("Unsupported input file type: {}. Use .csv, .xlsx, .xlsm, or .xls.".format(suffix))


def validate_required_columns(df: pd.DataFrame) -> None:
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError("Missing required column(s): {}".format(", ".join(missing)))


def detect_defect_columns(df: pd.DataFrame, explicit_columns: Optional[Sequence[str]] = None) -> List[str]:
    if explicit_columns:
        column_lookup = {str(column).strip().casefold(): column for column in df.columns}
        resolved = [
            column_lookup.get(str(column).strip().casefold())
            for column in explicit_columns
        ]
        missing = [
            column
            for column, actual in zip(explicit_columns, resolved)
            if actual is None
        ]
        if missing:
            raise ValueError("Missing requested defect column(s): {}".format(", ".join(missing)))
        return [str(column) for column in resolved]

    metadata = set(REQUIRED_COLUMNS)
    defect_cols = []
    for col in df.columns:
        if col in metadata:
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        if numeric.notna().any():
            defect_cols.append(col)
    if not defect_cols:
        raise ValueError("No numeric defect count columns were found.")
    return defect_cols


def _find_first_column(columns: Iterable[str], candidates: Sequence[str]) -> Optional[str]:
    exact = {col.lower().replace(" ", "_"): col for col in columns}
    for candidate in candidates:
        key = candidate.lower().replace(" ", "_")
        if key in exact:
            return exact[key]
    return None


def read_bsl_table(path: str) -> pd.DataFrame:
    bsl = read_table(path)
    defect_col = _find_first_column(
        bsl.columns,
        ["Defect type", "Defect_Type", "Defect", "DefectType", "defect_type"],
    )
    value_col = _find_first_column(
        bsl.columns,
        ["BSL count", "BSL_count", "BSL", "bsl_count", "Baseline", "Baseline count"],
    )
    if defect_col is None or value_col is None:
        raise ValueError("BSL file needs columns like 'Defect type' and 'BSL count'.")

    rename_map = {defect_col: "Defect type", value_col: "BSL count"}
    if "Stage_ID" in bsl.columns:
        rename_map["Stage_ID"] = "Stage_ID"
    if "Step_ID" in bsl.columns:
        rename_map["Step_ID"] = "Step_ID"

    keep_cols = list(dict.fromkeys(rename_map.values()))
    bsl = bsl.rename(columns=rename_map)
    bsl = bsl[[col for col in keep_cols if col in bsl.columns]].copy()
    bsl["Defect type"] = bsl["Defect type"].astype(str).str.strip()
    bsl["BSL count"] = pd.to_numeric(bsl["BSL count"], errors="coerce")
    bsl = bsl.dropna(subset=["Defect type", "BSL count"])
    if bsl.empty:
        raise ValueError("BSL file has no valid BSL rows.")
    return bsl


def build_bsl_lookup(bsl: pd.DataFrame) -> Tuple[Dict[Tuple[str, str, str], float], Dict[str, float]]:
    stage_lookup: Dict[Tuple[str, str, str], float] = {}
    defect_lookup: Dict[str, float] = {}
    has_process_columns = "Stage_ID" in bsl.columns and "Step_ID" in bsl.columns

    for _, row in bsl.iterrows():
        defect = str(row["Defect type"]).strip().casefold()
        bsl_value = float(row["BSL count"])
        if has_process_columns:
            stage = "" if pd.isna(row.get("Stage_ID")) else str(row.get("Stage_ID")).strip()
            step = "" if pd.isna(row.get("Step_ID")) else str(row.get("Step_ID")).strip()
            if stage and step:
                key = (defect, stage, step)
                if key in stage_lookup and not np.isclose(stage_lookup[key], bsl_value):
                    raise ValueError(
                        "Conflicting BSL values for defect/stage/step: {} / {} / {}.".format(
                            row["Defect type"], stage, step
                        )
                    )
                stage_lookup[key] = bsl_value
                continue
        if defect in defect_lookup and not np.isclose(defect_lookup[defect], bsl_value):
            raise ValueError(
                "Conflicting global BSL values for defect: {}.".format(row["Defect type"])
            )
        defect_lookup[defect] = bsl_value
    return stage_lookup, defect_lookup


def get_bsl_count(
    defect: str,
    stage_id: str,
    step_id: str,
    stage_lookup: Dict[Tuple[str, str, str], float],
    defect_lookup: Dict[str, float],
) -> Optional[float]:
    defect_key = str(defect).strip().casefold()
    key = (defect_key, str(stage_id), str(step_id))
    if key in stage_lookup:
        return stage_lookup[key]
    return defect_lookup.get(defect_key)


def get_special_bsl_count(
    defect: str,
    step_id: str,
    step_stage_rules: Optional[Set[str]],
    stage_lookup: Dict[Tuple[str, str, str], float],
    defect_lookup: Dict[str, float],
) -> Optional[float]:
    defect_key = str(defect).strip().casefold()
    if defect_key in defect_lookup:
        return defect_lookup[defect_key]
    if step_stage_rules is None:
        values = [
            float(value)
            for (lookup_defect, _stage_id, lookup_step), value in stage_lookup.items()
            if lookup_defect == defect_key and str(lookup_step) == str(step_id)
        ]
        if values:
            return max(values)
        return None
    if not step_stage_rules:
        return None
    values = []
    for stage_id in step_stage_rules:
        key = (defect_key, str(stage_id), str(step_id))
        if key in stage_lookup:
            values.append(float(stage_lookup[key]))
    if values:
        return max(values)
    return None


def normalize_process_aggregation(value: str) -> str:
    normalized = str(value or PROCESS_AGGREGATION_STAGE_STEP).strip().lower().replace("-", "_")
    aliases = {
        "stage+step": PROCESS_AGGREGATION_STAGE_STEP,
        "stage_step": PROCESS_AGGREGATION_STAGE_STEP,
        "stage_and_step": PROCESS_AGGREGATION_STAGE_STEP,
        "step": PROCESS_AGGREGATION_STEP,
        "step_only": PROCESS_AGGREGATION_STEP,
        "step_id": PROCESS_AGGREGATION_STEP,
    }
    if normalized not in aliases:
        raise ValueError(
            "process_aggregation must be one of: {}".format(", ".join(PROCESS_AGGREGATION_CHOICES))
        )
    return aliases[normalized]


def apply_process_aggregation(df: pd.DataFrame, process_aggregation: str) -> pd.DataFrame:
    mode = normalize_process_aggregation(process_aggregation)
    if mode == PROCESS_AGGREGATION_STAGE_STEP:
        return df
    adjusted = df.copy()
    adjusted["Stage_ID"] = STEP_ONLY_STAGE_ID
    adjusted["Process_Stage"] = "Step-only | Step_ID=" + adjusted["Step_ID"].astype(str).str.strip()
    return adjusted


def apply_special_process_rules(
    df: pd.DataFrame,
    defect_col: str,
    special_process_rules: Optional[SpecialProcessRules] = None,
) -> pd.DataFrame:
    if not special_process_rules:
        return df
    defect_rules = special_process_rules.get(str(defect_col).strip().casefold())
    if not defect_rules:
        return df

    adjusted = df.copy()
    stage_values = adjusted["Stage_ID"].astype(str).str.strip()
    step_values = adjusted["Step_ID"].astype(str).str.strip()
    special_mask = pd.Series(False, index=adjusted.index)

    for step_id, stage_set in defect_rules.items():
        mask = step_values == str(step_id)
        if stage_set is not None:
            mask = mask & stage_values.isin(set(str(stage).strip() for stage in stage_set))
        special_mask = special_mask | mask

    if not special_mask.any():
        return adjusted

    adjusted.loc[special_mask, "Stage_ID"] = SPECIAL_STAGE_ID
    adjusted.loc[special_mask, "Process_Stage"] = (
        "Step-only | Step_ID=" + adjusted.loc[special_mask, "Step_ID"].astype(str).str.strip()
    )
    return adjusted


def add_grouping_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    equipment = df["Equipment_ID"].fillna("").astype(str).str.strip()
    chamber = df["Chamber_ID"].fillna("").astype(str).str.strip()
    prefixes = equipment.str[:2].str.upper()

    df["Process_Stage"] = df["Stage_ID"].astype(str).str.strip() + "_" + df["Step_ID"].astype(str).str.strip()
    df["Equipment_Group"] = equipment
    df["Chamber_Group"] = np.where(prefixes.isin(CHAMBER_PREFIXES), chamber, "")
    df["Group_Level"] = np.where(prefixes.isin(CHAMBER_PREFIXES), "Chamber", "Equipment")
    df["Tool_Group"] = np.where(
        prefixes.isin(CHAMBER_PREFIXES),
        equipment + "::" + chamber,
        equipment,
    )
    df["Wafer_Key"] = df["Lot_ID"].astype(str).str.strip() + "::" + df["Wafer_NO"].astype(str).str.strip()
    df["Scan_Time_Parsed"] = pd.to_datetime(df["Scan_Time"], errors="coerce")
    return df


def normalize_data_window(value: str) -> str:
    normalized = str(value or DATA_WINDOW_ALL).strip().lower().replace("_", "").replace("-", "")
    aliases = {
        "all": DATA_WINDOW_ALL,
        "full": DATA_WINDOW_ALL,
        "latest14d": DATA_WINDOW_14D,
        "14d": DATA_WINDOW_14D,
        "2w": DATA_WINDOW_14D,
        "twoweeks": DATA_WINDOW_14D,
        "latest7d": DATA_WINDOW_7D,
        "7d": DATA_WINDOW_7D,
        "1w": DATA_WINDOW_7D,
        "oneweek": DATA_WINDOW_7D,
    }
    if normalized not in aliases:
        raise ValueError("data_window must be one of: {}".format(", ".join(DATA_WINDOW_CHOICES)))
    return aliases[normalized]


def filter_by_recent_scan_time(df: pd.DataFrame, data_window: str = DATA_WINDOW_ALL) -> pd.DataFrame:
    window = normalize_data_window(data_window)
    if window == DATA_WINDOW_ALL:
        return df.copy()
    parsed = pd.to_datetime(df["Scan_Time_Parsed"] if "Scan_Time_Parsed" in df.columns else df["Scan_Time"], errors="coerce")
    valid = df.loc[parsed.notna()].copy()
    if valid.empty:
        raise ValueError("Scan_Time cannot be parsed for recent data filtering.")
    valid["_Window_Scan_Time"] = parsed.loc[valid.index]
    latest = valid["_Window_Scan_Time"].max()
    cutoff = latest - pd.Timedelta(days=DATA_WINDOW_DAYS[window])
    filtered = valid.loc[valid["_Window_Scan_Time"] >= cutoff].drop(columns=["_Window_Scan_Time"]).copy()
    if filtered.empty:
        raise ValueError("No rows remain after applying data window '{}'.".format(window))
    return filtered


def calculate_recent_trimmed_bsl(df: pd.DataFrame, defect_col: str) -> Optional[float]:
    values = pd.to_numeric(df[defect_col], errors="coerce").dropna().astype(float)
    if values.empty:
        return None
    lower = values.quantile(0.05)
    upper = values.quantile(0.95)
    trimmed = values.loc[(values >= lower) & (values <= upper)]
    if trimmed.empty:
        trimmed = values
    return float(trimmed.mean())


def filter_outliers_for_defect(
    df: pd.DataFrame,
    defect_col: str,
    outlier_sigma: float = 3.0,
) -> pd.DataFrame:
    values = pd.to_numeric(df[defect_col], errors="coerce")
    valid = df.loc[values.notna()].copy()
    valid[defect_col] = values.loc[values.notna()].astype(float)
    if valid.empty:
        return valid

    mean = valid[defect_col].mean()
    std = valid[defect_col].std(ddof=0)
    if pd.isna(std) or std == 0:
        return valid
    return valid.loc[valid[defect_col] <= mean + float(outlier_sigma) * std].copy()


def summarize_one_defect(
    df: pd.DataFrame,
    defect_col: str,
    bsl_stage_lookup: Dict[Tuple[str, str, str], float],
    bsl_defect_lookup: Dict[str, float],
    bsl_multiplier: float = 1.5,
    min_wafers: int = 5,
    outlier_sigma: float = 3.0,
    special_process_rules: Optional[SpecialProcessRules] = None,
    process_aggregation: str = PROCESS_AGGREGATION_STAGE_STEP,
    recent_trimmed_bsl: Optional[float] = None,
    data_window: str = DATA_WINDOW_ALL,
) -> pd.DataFrame:
    filtered = filter_outliers_for_defect(df, defect_col, outlier_sigma=outlier_sigma)
    if filtered.empty:
        return pd.DataFrame()
    filtered = apply_special_process_rules(
        filtered,
        defect_col,
        special_process_rules=special_process_rules,
    )
    filtered = apply_process_aggregation(filtered, process_aggregation)

    group_cols = ["Stage_ID", "Step_ID", "Equipment_Group", "Chamber_Group", "Group_Level", "Tool_Group"]
    grouped = (
        filtered.groupby(group_cols, dropna=False)
        .agg(
            Mean_Count=(defect_col, "mean"),
            Median_Count=(defect_col, "median"),
            Max_Count=(defect_col, "max"),
            Wafer_Count=("Wafer_Key", "nunique"),
            Row_Count=(defect_col, "size"),
        )
        .reset_index()
    )
    grouped = grouped.loc[grouped["Wafer_Count"] >= int(min_wafers)].copy()
    if grouped.empty:
        return grouped

    grouped["Defect type"] = defect_col
    defect_rules = {}
    if special_process_rules:
        defect_rules = special_process_rules.get(str(defect_col).strip().casefold(), {})
    grouped["BSL count"] = grouped.apply(
        lambda row: get_special_bsl_count(
            defect_col,
            row["Step_ID"],
            defect_rules.get(str(row["Step_ID"]).strip()),
            bsl_stage_lookup,
            bsl_defect_lookup,
        )
        if str(row["Stage_ID"]).strip() in {SPECIAL_STAGE_ID, STEP_ONLY_STAGE_ID}
        else get_bsl_count(
            defect_col,
            row["Stage_ID"],
            row["Step_ID"],
            bsl_stage_lookup,
            bsl_defect_lookup,
        ),
        axis=1,
    )
    grouped = grouped.dropna(subset=["BSL count"])
    if grouped.empty:
        return grouped

    threshold = grouped["BSL count"].astype(float) * float(bsl_multiplier)
    grouped = grouped.loc[
        (grouped["Mean_Count"] >= threshold) | (grouped["Median_Count"] >= threshold)
    ].copy()
    if grouped.empty:
        return grouped

    grouped["Equipment ID"] = grouped["Equipment_Group"]
    grouped["Chamber ID"] = np.where(grouped["Group_Level"] == "Chamber", grouped["Chamber_Group"], "")
    grouped["BSL Multiplier"] = float(bsl_multiplier)
    grouped["Recent Trimmed BSL"] = recent_trimmed_bsl
    grouped["Data Window"] = normalize_data_window(data_window)
    grouped["Trigger"] = np.where(
        grouped["Median_Count"] >= grouped["BSL count"] * float(bsl_multiplier),
        "median",
        "mean",
    )
    output_cols = [
        "Defect type",
        "BSL count",
        "Stage_ID",
        "Step_ID",
        "Equipment ID",
        "Chamber ID",
        "Group_Level",
        "Mean_Count",
        "Median_Count",
        "Max_Count",
        "Wafer_Count",
        "Row_Count",
        "BSL Multiplier",
        "Recent Trimmed BSL",
        "Data Window",
        "Trigger",
    ]
    return grouped[output_cols].sort_values(
        ["Defect type", "Stage_ID", "Step_ID", "Mean_Count", "Median_Count"],
        ascending=[True, True, True, False, False],
    )


def build_worse_tool_result(
    input_path: str,
    bsl_path: str,
    defect_columns: Optional[Sequence[str]] = None,
    input_sheet: Optional[str] = None,
    bsl_multiplier: float = 1.5,
    min_wafers: int = 5,
    outlier_sigma: float = 3.0,
    special_process_rules: Optional[SpecialProcessRules] = None,
    process_aggregation: str = PROCESS_AGGREGATION_STAGE_STEP,
    data_window: str = DATA_WINDOW_ALL,
) -> pd.DataFrame:
    df = read_table(input_path, sheet_name=input_sheet)
    validate_required_columns(df)
    df = add_grouping_columns(df)
    df = filter_by_recent_scan_time(df, data_window=data_window)
    defects = detect_defect_columns(df, defect_columns)
    bsl = read_bsl_table(bsl_path)
    stage_lookup, defect_lookup = build_bsl_lookup(bsl)

    pieces = []
    for defect in defects:
        recent_trimmed_bsl = calculate_recent_trimmed_bsl(df, defect)
        piece = summarize_one_defect(
            df,
            defect,
            stage_lookup,
            defect_lookup,
            bsl_multiplier=bsl_multiplier,
            min_wafers=min_wafers,
            outlier_sigma=outlier_sigma,
            special_process_rules=special_process_rules,
            process_aggregation=process_aggregation,
            recent_trimmed_bsl=recent_trimmed_bsl,
            data_window=data_window,
        )
        if not piece.empty:
            pieces.append(piece)
    if not pieces:
        return pd.DataFrame(
            columns=[
                "Defect type",
                "BSL count",
                "Stage_ID",
                "Step_ID",
                "Equipment ID",
                "Chamber ID",
                "Group_Level",
                "Mean_Count",
                "Median_Count",
                "Max_Count",
                "Wafer_Count",
                "Row_Count",
                "BSL Multiplier",
                "Recent Trimmed BSL",
                "Data Window",
                "Trigger",
            ]
        )
    return pd.concat(pieces, ignore_index=True)


def write_result_to_excel(
    result: pd.DataFrame,
    output_path: str,
    sheet_name: str = DEFAULT_SHEET_NAME,
    write_mode: str = "append",
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    mode = str(write_mode).strip().lower()
    if mode not in {"append", "replace"}:
        raise ValueError("write_mode must be 'append' or 'replace'.")

    if output.exists():
        if mode == "append":
            try:
                existing = pd.read_excel(output, sheet_name=sheet_name)
                combined = pd.concat([existing, result], ignore_index=True)
            except ValueError:
                combined = result.copy()
        else:
            combined = result.copy()
        with pd.ExcelWriter(output, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            combined.to_excel(writer, sheet_name=sheet_name, index=False)
    else:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            result.to_excel(writer, sheet_name=sheet_name, index=False)
    return output


def append_result_to_excel(result: pd.DataFrame, output_path: str, sheet_name: str = DEFAULT_SHEET_NAME) -> Path:
    return write_result_to_excel(result, output_path, sheet_name=sheet_name, write_mode="append")


def parse_defect_columns(raw: Optional[str]) -> Optional[List[str]]:
    if raw is None or raw.strip() == "":
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


def _split_process_token(token: str) -> Tuple[Optional[str], str]:
    value = str(token).strip()
    if not value:
        raise ValueError("Special process rule contains an empty stage/step token.")
    if "_" not in value:
        return None, value
    stage_id, step_id = value.rsplit("_", 1)
    stage_id = stage_id.strip()
    step_id = step_id.strip()
    if not stage_id or not step_id:
        raise ValueError("Invalid special process token '{}'. Use STAGE_STEP or STEP.".format(value))
    return stage_id, step_id


def parse_special_process_rules(raw: Optional[str]) -> SpecialProcessRules:
    """
    Parse rules like:
    Defect Type1: STG01_STEP10, STG02_STEP10; Defect Type2: STEP30

    STAGE_STEP tokens merge only the listed stages for that Step_ID.
    STEP tokens merge all rows with that Step_ID for the defect.
    """
    rules: SpecialProcessRules = {}
    if raw is None or str(raw).strip() == "":
        return rules

    normalized = str(raw).replace("\r", "\n").replace(";", "\n")
    for line in normalized.splitlines():
        item = line.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(
                "Special process rules must use 'Defect type: STAGE_STEP, STEP'. "
                "Example: Defect Type1: STG01_STEP10, STG02_STEP10"
            )
        defect, process_text = item.split(":", 1)
        defect_key = defect.strip().casefold()
        if not defect_key:
            raise ValueError("Special process rule has an empty defect type.")
        tokens = [token.strip() for token in process_text.replace("|", ",").split(",") if token.strip()]
        if not tokens:
            raise ValueError("Special process rule for '{}' has no process token.".format(defect.strip()))

        defect_rules = rules.setdefault(defect_key, {})
        for token in tokens:
            stage_id, step_id = _split_process_token(token)
            if step_id in defect_rules and defect_rules[step_id] is None:
                continue
            if stage_id is None:
                defect_rules[step_id] = None
            else:
                defect_rules.setdefault(step_id, set())
                if defect_rules[step_id] is not None:
                    defect_rules[step_id].add(stage_id)
    return rules


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Defect worse tool cross result.")
    parser.add_argument("--input", required=True, help="Input defect table: .csv, .xlsx, .xlsm, or .xls")
    parser.add_argument("--bsl", required=True, help="BSL csv/xlsx with Defect type and BSL count columns")
    parser.add_argument("--output", required=True, help="Output Excel path.")
    parser.add_argument("--input-sheet", default=None, help="Excel sheet name or index for input file.")
    parser.add_argument("--output-sheet", default=DEFAULT_SHEET_NAME, help="Output sheet name.")
    parser.add_argument("--defect-cols", default=None, help="Comma-separated defect count columns. Auto-detected when omitted.")
    parser.add_argument(
        "--special-process-rules",
        default=None,
        help=(
            "Chart/analysis process merge rules, e.g. "
            "'Defect Type1: STG01_STEP10, STG02_STEP10; Defect Type2: STEP30'."
        ),
    )
    parser.add_argument(
        "--process-aggregation",
        choices=PROCESS_AGGREGATION_CHOICES,
        default=PROCESS_AGGREGATION_STAGE_STEP,
        help="Process grouping mode. stage_step keeps Stage_ID+Step_ID; step groups all stages by Step_ID only.",
    )
    parser.add_argument(
        "--data-window",
        choices=DATA_WINDOW_CHOICES,
        default=DATA_WINDOW_ALL,
        help="Rows used for worse-tool calculation by latest Scan_Time. all, 14d, or 7d.",
    )
    parser.add_argument("--bsl-multiplier", type=float, default=1.5, help="Flag threshold multiplier. Default: 1.5")
    parser.add_argument("--min-wafers", type=int, default=5, help="Minimum unique wafers per process-stage/tool group.")
    parser.add_argument("--outlier-sigma", type=float, default=3.0, help="Upper outlier cutoff in sigma. Default: 3.0")
    parser.add_argument(
        "--write-mode",
        choices=["append", "replace"],
        default="append",
        help="Append to or replace the target sheet. Default: append",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_worse_tool_result(
        input_path=args.input,
        bsl_path=args.bsl,
        defect_columns=parse_defect_columns(args.defect_cols),
        input_sheet=args.input_sheet,
        bsl_multiplier=args.bsl_multiplier,
        min_wafers=args.min_wafers,
        outlier_sigma=args.outlier_sigma,
        special_process_rules=parse_special_process_rules(args.special_process_rules),
        process_aggregation=args.process_aggregation,
        data_window=args.data_window,
    )
    write_result_to_excel(
        result,
        args.output,
        sheet_name=args.output_sheet,
        write_mode=args.write_mode,
    )
    print("Generated {} worse-tool row(s).".format(len(result)))
    print("Wrote result to {} using {} mode.".format(args.output, args.write_mode))


if __name__ == "__main__":
    main()
