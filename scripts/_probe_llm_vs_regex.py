"""실제 공고 합본 → LLM 추출 + regex 추출 → 필드별 비교."""
import sys, os, asyncio, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import logging
logging.basicConfig(level=logging.WARNING)

from pathlib import Path
from src.collector.attachments import HwpParser, PdfParser
from src.llm.extraction_validators import RegexExtractor
from src.llm.gateway import LLMGateway


FILES = [
    (r"C:\Users\junpr\Downloads\1. 공고문.hwp", "hwp"),
    (r"C:\Users\junpr\Downloads\제안서.hwp", "hwp"),
    (r"C:\Users\junpr\Downloads\2. 용도설명서 및 상세규격서.pdf", "pdf"),
]


async def main():
    hwp = HwpParser()
    pdf = PdfParser()
    texts = []
    for path_str, kind in FILES:
        p = Path(path_str)
        raw = p.read_bytes()
        text = hwp.parse(raw, p.name) if kind == "hwp" else pdf.parse(raw)
        texts.append(f"=== {p.name} ===\n{text}")
    combined = "\n\n".join(texts)
    print(f"합본 길이: {len(combined):,}자\n")

    # --- regex 추출
    rex = RegexExtractor()
    regex_out = {
        "기초금액":       rex.extract_base_price(combined),
        "추정가격":       rex.extract_estimated_price(combined),
        "낙찰하한율":     rex.extract_nakchal_rate(combined),
        "입찰마감":       str(rex.extract_deadline(combined)) if rex.extract_deadline(combined) else None,
        "조달청물품분류번호": rex.extract_classification(combined),
        "입찰방식":       rex.extract_tender_type(combined),
        "낙찰자선정방식": rex.extract_evaluation_method(combined),
        "직접생산증명요구": rex.extract_direct_mfg(combined),
        "위임장허용":     rex.extract_loa_accepted(combined),
    }

    # --- LLM 추출 (attachment_text 경로로 전달)
    gw = LLMGateway()
    print("LLM 호출 중...")
    out = await gw.summarize_bid(
        bid_content="한국에너지공과대학교 반도체 변압기(SST) 번들 시험장치 구매 입찰 공고",
        attachment_text=combined[:8000],  # 첨부 cap 6000자에 맞춰 8000 transmit
    )
    if not out:
        print("LLM 응답 없음")
        return
    llm_specs = out.specs.model_dump()

    # --- 비교 출력
    print(f"\n=== LLM summary ===\n{out.summary}\n")
    print("=== 필드별 비교 (LLM vs regex) ===")
    fields = list(set(regex_out.keys()) | set(llm_specs.keys()))
    interesting = [
        "공고명", "발주기관", "기초금액", "추정가격", "낙찰하한율",
        "입찰방식", "낙찰자선정방식", "조달청물품분류번호",
        "납기", "입찰마감", "공사_용역_유형",
        "직접생산증명요구", "위임장허용",
        "주요_기술요건", "필수_자격_면허", "적격심사_배점",
    ]
    for f in interesting:
        l = llm_specs.get(f)
        r = regex_out.get(f, "(regex 없음)")
        match = "  " if (l == r) else ("≠ " if r != "(regex 없음)" else "  ")
        print(f"  {match}{f:24s}  LLM={l!r:60s} regex={r!r}")


asyncio.run(main())
