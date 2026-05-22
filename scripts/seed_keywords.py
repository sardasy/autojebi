"""키워드 사전 확인 및 출력 유틸리티"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.filter.energy_keywords import ENERGY_KEYWORDS  # noqa: E402

if __name__ == "__main__":
    total = sum(len(v) for v in ENERGY_KEYWORDS.values())
    print(f"총 키워드: {total}개\n")
    for cat, kws in ENERGY_KEYWORDS.items():
        print(f"[{cat}] ({len(kws)}개)")
        for kw in kws:
            print(f"  - {kw}")
