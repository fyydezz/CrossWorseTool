from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence


LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class PPTGenerationContext:
    """Stable data contract between the UI and an external PPT generator."""

    raw_data_path: str
    bsl_path: str
    worse_result_path: str
    ppt_output_path: str
    input_sheet: Optional[str]
    result_sheet: str
    defect_columns: Optional[Sequence[str]]
    bsl_multiplier: float
    min_wafers: int
    outlier_sigma: float
    selected_defect: Optional[str]
    selected_process_stage: Optional[str]


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

    raise NotImplementedError(
        "PPT integration is not configured. Open ppt_integration.py and "
        "replace run_ppt_generation() with the internal PPT generation method."
    )

