"""Reference values and stable ordering shared by UI and PPT chart pairs."""
from defect_worse_tool import (
    filter_by_recent_scan_time, handle_outliers_for_defect, calculate_mean_bsl,
    read_bsl_table, build_bsl_lookup, summarize_one_defect,
    apply_special_process_rules, apply_process_aggregation,
    get_bsl_count, get_special_bsl_count,
)


def analysis_references(raw, defect, options):
    window = options.get("data_window", "all")
    data = filter_by_recent_scan_time(raw, window)
    sigma = options.get("outlier_sigma", 3.0)
    handling = options.get("outlier_handling", "filter")
    source = options.get("bsl_source", "file")
    stage_lookup, defect_lookup = {}, {}
    if source == "file":
        if options.get("bsl_path"):
            stage_lookup, defect_lookup = build_bsl_lookup(read_bsl_table(options["bsl_path"]))
    else:
        baseline = filter_by_recent_scan_time(raw, "14d") if source == "recent_mean" else data
        mean = calculate_mean_bsl(baseline, defect, sigma, handling)
        if mean is not None:
            defect_lookup = {defect.casefold(): mean}
    # Zero multiplier exposes all eligible layers without reusing append history.
    summary = summarize_one_defect(data, defect, {}, {defect.casefold(): 0.0},
        bsl_multiplier=0, min_wafers=options.get("min_wafers", 5), outlier_sigma=sigma,
        outlier_handling=handling, special_process_rules=options.get("special_process_rules"),
        process_aggregation=options.get("process_aggregation", "stage_step"))
    golden = {(str(row.Stage_ID), str(row.Step_ID)): row["Golden Mean_Count"]
              for _, row in summary.iterrows()} if not summary.empty else {}
    layers = handle_outliers_for_defect(data, defect, sigma, handling)
    layers = apply_special_process_rules(layers, defect, options.get("special_process_rules"))
    layers = apply_process_aggregation(layers, options.get("process_aggregation", "stage_step"))
    refs = {}
    for _, row in layers[["Stage_ID", "Step_ID"]].drop_duplicates().iterrows():
        stage, step = str(row.Stage_ID), str(row.Step_ID)
        if stage in {"ALL_STAGES", "SPECIAL_STEP_ONLY"}:
            rules = options.get("special_process_rules") or {}
            stages = rules.get(defect.casefold(), {}).get(step)
            bsl = get_special_bsl_count(defect, step, stages, stage_lookup, defect_lookup)
        else:
            bsl = get_bsl_count(defect, stage, step, stage_lookup, defect_lookup)
        refs[(stage, step)] = dict(
            BSL=bsl,
            Threshold=bsl * options.get("bsl_multiplier", 1.5) if bsl is not None else None,
            Golden=golden.get((stage, step)),
        )
    return refs


def annotate_chart_data(renderer, raw, data, defect, options, chart_window, references=None):
    sigma = options.get("outlier_sigma", 3.0)
    handling = options.get("outlier_handling", "filter")
    stage, step = str(data.Stage_ID.iloc[0]), str(data.Step_ID.iloc[0])
    # All chart types use the latest-14-day rank; historical-only Tools follow by ID.
    recent = filter_by_recent_scan_time(raw, "14d")
    recent = handle_outliers_for_defect(recent, defect, sigma, handling)
    recent = apply_special_process_rules(recent, defect, options.get("special_process_rules"))
    recent = apply_process_aggregation(recent, options.get("process_aggregation", "stage_step"))
    recent = recent.loc[(recent.Stage_ID.astype(str) == stage) & (recent.Step_ID.astype(str) == step)]
    recent = renderer._filter_chart_group_mode(recent, options.get("chart_group_mode", "By Chamber"))
    order = recent.groupby("Chart_Group")[defect].agg(["median", "mean"]).sort_values(
        ["median", "mean"], ascending=False, kind="mergesort").index.tolist()
    # Include all-time identifiers in the same comparison context, even when the Box has no rows for them.
    all_layers = apply_special_process_rules(raw, defect, options.get("special_process_rules"))
    all_layers = apply_process_aggregation(all_layers, options.get("process_aggregation", "stage_step"))
    all_layers = all_layers.loc[(all_layers.Stage_ID.astype(str) == stage) & (all_layers.Step_ID.astype(str) == step)]
    all_layers = renderer._filter_chart_group_mode(all_layers, options.get("chart_group_mode", "By Chamber"))
    order += sorted(set(all_layers.Chart_Group) - set(order))
    data.attrs["tool_order"] = order
    refs = analysis_references(raw, defect, options) if references is None else references
    meta = dict(refs.get((stage, step), {}))
    meta.update(window={"14d": "Latest 14 days", "7d": "Latest 7 days", "all": "All data"}[chart_window],
                cleaning="{} at mean + {} sigma".format(handling, sigma),
                reference_note="References: analysis {}, {}; Golden uses analysis grouping (wafer min {})".format(
                    options.get("data_window", "all"), options.get("bsl_source", "file"), max(5, options.get("min_wafers", 5))))
    data.attrs["chart_meta"] = meta
    return data
