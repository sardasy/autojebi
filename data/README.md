# data/

G2B(나라장터) 수집기 디버깅·테스트용 픽스처.

| 파일 | 용도 |
|---|---|
| `sample_raw.json` | G2B PPSSrch API 단건 응답 예시 (한국전력 강원본부 변압기시험기 공고). `tests/test_collector_pipeline.py`에서 픽스처로 사용. |
| `g2b_api_spec.txt` (선택) | data.go.kr 입찰공고정보서비스 v1.2 명세서. 필요 시 `abb-bid-pipeline/data/g2b_api_spec.txt`에서 가져옴 (~395KB). |

ABB SKU 카탈로그(`abb_catalog_sample.json`)는 M3에서 Qdrant 도입할 때 추가.
