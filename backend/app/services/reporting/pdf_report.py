"""PDF rendering via WeasyPrint (HTML+CSS -> PDF). Imported lazily inside the
function, not at module level: WeasyPrint pulls in Pango/Cairo bindings that
are unnecessary for any code path that doesn't actually render a PDF (mirrors
the same lazy-import pattern used for sentence-transformers)."""

from app.services.reporting.data import ReportData
from app.services.reporting.html_report import build_html_report


def build_pdf_report(data: ReportData, *, mode: str = "condensed") -> bytes:
    from weasyprint import HTML

    html_content = build_html_report(data, mode=mode)
    return HTML(string=html_content).write_pdf()
