from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence


LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class PPTGenerationContext:
    """Stable data contract between the UI and an external PPT generator."""

    ppt_output_path: str
    ppt_template_path: str
    input_image_path: str
    raw_data_path: str
    bsl_path: str
    worse_result_path: str
    input_sheet: Optional[str]
    result_sheet: str
    defect_columns: Optional[Sequence[str]]
    bsl_multiplier: float
    min_wafers: int
    outlier_sigma: float
    selected_defect: Optional[str]
    selected_process_stage: Optional[str]


def run_external_ppt_method(
    ppt_output_path: str,
    ppt_template_path: str,
    input_image_path: str,
    log_callback: Optional[LogCallback] = None,
) -> Path:
    """
    Replace this placeholder with the external PPT method.

    This is the smallest intended integration point. The UI passes exactly
    these three paths from the PPT controls:
    - ppt_output_path
    - ppt_template_path
    - input_image_path (directory containing the source images)
    """
    if log_callback is not None:
        log_callback("External PPT method received output/template/image-folder paths.")
    raise NotImplementedError(
        "External PPT method is not configured. Replace run_external_ppt_method() "
        "in ppt_integration.py with your PPT generation implementation."
    )


def run_ppt_generation(
    context: PPTGenerationContext,
    log_callback: Optional[LogCallback] = None,
) -> Path:
    """
    Replace this function body with the internal-network PPT implementation.

    The UI calls this function on a worker thread. The implementation should
    create the requested PPT file and return its final path. Do not access
    Tkinter widgets from this function.
    """
    if log_callback is not None:
        log_callback("PPT integration was called.")
        log_callback("Output PPT: {}".format(context.ppt_output_path))
        log_callback("Template PPT: {}".format(context.ppt_template_path))
        log_callback("Input image folder: {}".format(context.input_image_path))

    return run_external_ppt_method(
        ppt_output_path=context.ppt_output_path,
        ppt_template_path=context.ppt_template_path,
        input_image_path=context.input_image_path,
        log_callback=log_callback,
    )
