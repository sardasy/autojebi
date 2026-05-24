"""두 번째 공고 (제어기시험장치 재공고) — regex + LLM 추출, 첫 케이스와 비교용."""
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
from src.llm.prompts.summarize import SUMMARIZE_SYSTEM, SUMMARIZE_USER
from src.llm.structured_output import BidSummaryOutput

FILES = [
    r"C:\Users\junpr\Downloads\1. (재)공고문_제어기시험장치.hwp",
    r"C:\Users\junpr\Downloads\2. 물품구매규격서_제어기시험장치.hwp",
    r"C:\Users\junpr\Downloads\3. 규격제안요청서_제어기시험장치.hwp",
]


async def main():
    hwp = HwpParser()
    individual = {}
    texts = []
    for path_str in FILES:
        p = Path(path_str)
        raw = p.read_bytes()
        text = hwp.parse(raw, p.name)
        individual[p.name] = text
        texts.append(f"=== {p.name} ===\n{text}")
        print(f"파일: {p.name:60s}  {p.stat().st_size:>7,}b → {len(text):>6,}자")
    combined = "\n\n".join(texts)
    print(f"\n합본 길이: {len(combined):,}자\n")

    # 합본 미리보기 (앞 600자)
    print("=== 공고문 본체 (앞 800자) ===")
    print(individual[Path(FILES[0]).name][:800].replace("\n", " ↵ "))

    # --- regex
    rex = RegexExtractor()
    regex_out = {
        "base_price":     rex.extract_base_price(combined),
        "estimated_price": rex.extract_estimated_price(combined),
        "nakchal_rate":   rex.extract_nakchal_rate(combined),
        "deadline":       str(rex.extract_deadline(combined)) if rex.extract_deadline(combined) else None,
        "classification": rex.extract_classification(combined),
        "tender_type":    rex.extract_tender_type(combined),
        "evaluation_method": rex.extract_evaluation_method(combined),
        "direct_mfg":     rex.extract_direct_mfg(combined),
        "loa_accepted":   rex.extract_loa_accepted(combined),
    }
    print("\n=== regex 추출 ===")
    print(json.dumps(regex_out, ensure_ascii=False, indent=2, default=str))

    # --- LLM (cap 14000)
    gw = LLMGateway()
    full_prompt = SUMMARIZE_USER.format(bid_content=combined[:14000])
    print("\nLLM 호출 중 (cap 14000)...")
    out = await gw._openai_json_call(
        model="gpt-4o-mini",
        system=SUMMARIZE_SYSTEM,
        prompt=full_prompt,
        max_tokens=2000,
        schema_cls=BidSummaryOutput,
    )
    if not out:
        print("LLM 응답 없음")
        return
    print(f"\n=== LLM summary ===\n{out.summary}\n")
    print("=== LLM specs ===")
    print(json.dumps(out.specs.model_dump(), ensure_ascii=False, indent=2))


asyncio.run(main())
