"""실제 공고 첨부 3건 (공고문/제안서/사양서 PDF) — 합본 추출 + regex 검증."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

import logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from pathlib import Path
from src.collector.attachments import HwpParser, PdfParser
from src.llm.extraction_validators import RegexExtractor


FILES = [
    (r"C:\Users\junpr\Downloads\1. 공고문.hwp", "hwp"),
    (r"C:\Users\junpr\Downloads\제안서.hwp", "hwp"),
    (r"C:\Users\junpr\Downloads\2. 용도설명서 및 상세규격서.pdf", "pdf"),
]

hwp = HwpParser()
pdf = PdfParser()

individual_texts: dict[str, str] = {}
for path_str, kind in FILES:
    p = Path(path_str)
    raw = p.read_bytes()
    if kind == "hwp":
        text = hwp.parse(raw, p.name)
    else:
        text = pdf.parse(raw)
    individual_texts[p.name] = text
    print(f"\n{'='*80}\n파일: {p.name}\n포맷: {kind}  크기: {p.stat().st_size:,}b  추출: {len(text):,}자")
    if text:
        preview = text[:600].replace("\n", " ↵ ")
        print(f"미리보기 (앞 600자):\n  {preview}")

print(f"\n{'='*80}\n[합본 regex 추출]")
combined = "\n\n--- 첨부 ---\n\n".join(individual_texts.values())
print(f"합본 길이: {len(combined):,}자\n")

rex = RegexExtractor()
results = {
    "base_price":         rex.extract_base_price(combined),
    "estimated_price":    rex.extract_estimated_price(combined),
    "nakchal_rate":       rex.extract_nakchal_rate(combined),
    "deadline":           rex.extract_deadline(combined),
    "classification":     rex.extract_classification(combined),
    "tender_type":        rex.extract_tender_type(combined),
    "evaluation_method":  rex.extract_evaluation_method(combined),
    "direct_mfg":         rex.extract_direct_mfg(combined),
    "loa_accepted":       rex.extract_loa_accepted(combined),
}
print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
