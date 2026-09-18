"""Compatibility facade (R3, ADR 0001).

Job execution moved to ``api.workspace.executors`` (one module per job kind) and file checks to
``api.workspace.storage``. New code must import from those modules; this facade only keeps old
import paths working. Patch targets in tests must name the module where the code now lives.
"""

from api.workspace.executors import execute
from api.workspace.executors.analyze import analyze
from api.workspace.executors.excel import run_excel
from api.workspace.executors.extract import extract, extract_archive_hwp
from api.workspace.executors.fetch import fetch_sources
from api.workspace.executors.hwp import hwp_preview, run_hwp
from api.workspace.executors.package import run_package
from api.workspace.llm_usage import reserve_call
from api.workspace.storage import artifact, source_path, storage_root

__all__ = [
    "analyze",
    "artifact",
    "execute",
    "extract",
    "extract_archive_hwp",
    "fetch_sources",
    "hwp_preview",
    "reserve_call",
    "run_excel",
    "run_hwp",
    "run_package",
    "source_path",
    "storage_root",
]
