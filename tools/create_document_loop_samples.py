"""Generate explicitly synthetic Korean PDFs for the document-loop rehearsal."""

import subprocess
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/pdf/document-loop-samples"
PREVIEW = ROOT / "tmp/pdfs/document-loop-samples"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    PREVIEW.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("Korean", "C:/Windows/Fonts/malgun.ttf"))
    title = ParagraphStyle("title", fontName="Korean", fontSize=21, leading=32, spaceAfter=18)
    heading = ParagraphStyle("heading", fontName="Korean", fontSize=13, leading=22, spaceBefore=16, spaceAfter=8)
    body = ParagraphStyle("body", fontName="Korean", fontSize=11, leading=21, alignment=TA_LEFT, wordWrap="CJK", spaceAfter=9)
    warning = ParagraphStyle("warning", parent=body, textColor=colors.HexColor("#A4262C"), borderColor=colors.HexColor("#A4262C"), borderWidth=1, borderPadding=9, spaceAfter=24)
    docs = [
        ("01-sample-notice.pdf", "예시 공고 및 요구사항", [
            ("1. 공고 개요", ["문서 식별자: SAMPLE-NOTICE-01", "사업명: 교육용 실시간 시뮬레이터 도입 (가상)", "이 문서는 나라장터 공고가 아닌 기능 검증용 예시입니다."]),
            ("2. 필수 요구사항", ["교육용 시뮬레이터 장비 3대를 공급해야 합니다.", "계약일로부터 30일 이내에 납품해야 합니다.", "검수 완료일로부터 24개월의 보증을 제공해야 합니다."]),
            ("3. 검토 서류", ["각 요구사항에 대응하는 제안 내용과 근거를 확인합니다.", "이전 사업의 수량과 조건을 이번 공고의 충족 근거로 인정하지 않습니다.", "검토가 끝나지 않은 문서는 제출 준비 완료로 표시하지 않습니다."]),
        ]),
        ("02-previous-proposal.pdf", "회사 이전 작성자료 예시", [
            ("1. 자료 성격", ["문서 식별자: SAMPLE-REFERENCE-01", "가상 회사의 과거 제안서 문장입니다. 실제 수행 실적이 아닙니다.", "이번 공고와의 문장 비교에만 사용하며 증빙으로 승인하지 않습니다."]),
            ("2. 이전 제안 내용", ["이전 사업에서는 교육용 시뮬레이터 장비 2대를 제안했습니다.", "이전 사업의 납품 기한은 계약일로부터 60일입니다.", "이전 사업의 보증기간은 검수 완료일로부터 12개월입니다."]),
            ("3. 재사용 시 확인", ["수량, 납기, 보증기간을 새 요구사항과 각각 대조해야 합니다.", "이 문장의 실제성이나 현재 공급 능력은 확인되지 않았습니다."]),
        ]),
        ("03-sample-product-evidence.pdf", "제품 공급조건 확인자료 예시", [
            ("1. 자료 성격", ["문서 식별자: SAMPLE-EVIDENCE-01", "가상의 제품 근거이며 실제 제조사 확인서나 공급확약서가 아닙니다.", "테스트 공고에서만 검토 상태 변경을 연습합니다."]),
            ("2. 검증용 공급조건", ["교육용 시뮬레이터 장비 3대 공급을 가정합니다.", "계약일로부터 30일 이내 납품을 가정합니다.", "검수 완료일로부터 24개월 보증을 가정합니다."]),
            ("3. 사용 제한", ["실제 입찰, 견적, 납품 또는 회사의 실적 증명에 사용할 수 없습니다.", "실제 제출 전에는 회사와 제조사의 유효한 원본 증빙으로 교체해야 합니다."]),
        ]),
    ]
    for filename, name, sections in docs:
        story = [Paragraph("TEST ONLY / 가상 예시 / 실제 입찰 사용 금지", warning), Paragraph(name, title)]
        for section, paragraphs in sections:
            story.append(Paragraph(section, heading))
            story.extend(Paragraph(text, body) for text in paragraphs)
        story.append(Spacer(1, 10 * mm))
        story.append(Paragraph("autoJEBI 서류 작성 루프 E2E 검증 · 2026-09-07", body))
        target = OUTPUT / filename
        SimpleDocTemplate(str(target), pagesize=(210 * mm, 297 * mm), leftMargin=22 * mm, rightMargin=22 * mm, topMargin=20 * mm, bottomMargin=18 * mm).build(story)
        pdf = PdfReader(target)
        assert len(pdf.pages) == 1, filename
        text = pdf.pages[0].extract_text()
        assert "TEST ONLY" in text and "시뮬레이터" in text, filename
        subprocess.run([
            str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe"),
            "-png", "-singlefile", "-scale-to", "1100", str(target), str(PREVIEW / target.stem),
        ], check=True)
        print(target)


if __name__ == "__main__":
    main()
