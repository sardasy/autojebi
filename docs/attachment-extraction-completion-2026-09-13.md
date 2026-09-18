# 첨부 ZIP 처리 확대 및 한국어 OCR 실검증 — 2026-09-13

ZIP 안의 HWPX·HWP와 중첩 ZIP을 실제 추출 경로에 연결했다. 한국어 OCR은 설치 및 모델 문제를 확인하고 공식 모델로 재검증했지만, 고정 검증 문서의 단위 오인식이 남아 운영 정확도 통과로 처리하지 않았다.

## 구현 결과

- HWPX는 기존 `defusedxml` 파서와 표 구조 추출을 재사용한다. ZIP 바깥 원본과 같은 본문·표 구조 계약을 유지한다.
- HWP는 기존 인증된 단일 COM Worker의 `analyze_document`만 호출한다. 원래 멤버 이름으로 파일을 풀지 않고, `data/workspace/uploads/archive-members/<sha256>.hwp`에 원본 바이트를 보존한다. 호출 전후 해시를 확인하며 변조·심볼릭 링크·크기 초과 파일을 거부한다. Worker 타임아웃 뒤에도 원본을 임의 삭제하지 않는다.
- 중첩 ZIP은 루트 아래 2단계까지 처리한다. 압축해제 전체 50 MB, ZIP 및 Office 컨테이너 합산 500개 엔트리, 최종 본문 200,000자 한도와 압축팽창률·경로·암호화·중복명 방어를 유지한다. PDF OCR은 추출 작업당 10페이지, ZIP 내부 HWP는 작업당 10개 한도를 공유한다.
- 내부 멤버의 파일명·크기·SHA-256·상태·미완료 이유를 유지한다. 중첩 내역은 `extraction.members[*].extraction.members`에 있으며 표 인용 경로는 외부 ZIP 해시부터 내부 파일명까지 전체 컨테이너 경로를 포함한다.
- DWG 같은 미지원 자료나 깊이·Worker 호출 한도를 넘는 멤버가 하나라도 있으면 전체 원문의 `complete=false`가 유지된다. 안전성 한도 위반은 추출을 중단한다. 추출된 본문은 사람 승인이나 표 배치 확인을 뜻하지 않는다.
- Tesseract가 종료 코드 0을 반환해도 요청 언어나 모델 의존성을 로드하지 못했다면 `ocr_language_missing`과 `missing_languages`를 반환한다. 검토용 부분 본문은 보존하며 내부 경로·원문 stderr는 API로 노출하지 않는다.

## 실제 파일 확인

검증 폴더: `data/workspace/e2e-20260913/attachment-continuation/`.

`mixed-attachment-fixture.zip`에는 기존 TEST ONLY HWP와 중첩 ZIP 내부의 TEST ONLY HWPX가 있다. 실제 Worker 분석 1회로 두 경로 모두 `extracted`, 전체 `complete=true`, 본문 199자를 확인했다. HWP 멤버의 저장 바이트 해시가 원본과 일치한다. 세부 결과는 `mixed-attachment-result.json`에 보관한다. UI/DB 반영 검증과 구분되는 실제 추출 실행 기록이다.

HWP SHA-256: `ec6802e67d716a7e38749eb07a75d61ff1ff9ca04ab25923131470f88648970f`.

## 한국어 OCR 결과 및 제한

1. 기존 Tesseract는 `C:/Program Files/Tesseract-OCR/tesseract.exe`에 있으나 PATH 및 `TESSERACT_CMD`가 설정되지 않았다. 설치 루트의 `kor.traineddata`는 기본 tessdata 폴더 밖에 있고 `chi_tra` 의존성을 요구했다. 시스템 설치는 수정하지 않았다.
2. 설치된 모델을 workspace에 복사해 이미지형 PDF를 읽으면 수량·납기 문구가 누락됐는데도 평균 confidence가 91.36으로 표시됐다. `korean-ocr-result.json`은 이 실패와 `ocr_language_missing` 진단을 보존한다.
3. [Tesseract 공식 모델 안내](https://tesseract-ocr.github.io/tessdoc/Data-Files.html)와 [공식 tessdata_fast 저장소](https://github.com/tesseract-ocr/tessdata_fast)를 확인하고 commit `87416418657359cb625c412a48b6e1d6d41c29bd`의 `kor`·`eng` 모델만 `data/ocr/tessdata-fast/`로 내려받았다. 다운로드 출처와 해시는 같은 폴더의 `provenance.json`에 있다. TSV 설정은 설치된 `configs/tsv`를 복사했다.
4. 동일한 고정 PDF를 제품의 기본 페이지 분할로 다시 읽어도 일부 줄 누락이 남았다. `korean-ocr-fast-result.json`에 결과를 보관한다. 모델 로드 문제는 해결됐지만 정확도 검증은 실패했다.
5. 같은 PNG를 진단 목적으로 단일 본문 블록(`--psm 6`)으로 읽으면 `납품 수량은 3대`, `계약 후 30일`은 일치했지만 `400 V`가 `400 \\`로 오인식됐다. `korean-ocr-fast-psm6-result.json`에 기록했다. 다단 문서의 구조를 훼손할 수 있으므로 제품 기본 페이지 분할은 변경하지 않았으며 숫자·단위를 자동 교정하지 않았다.

검증용 모델을 사용하려면 실행 프로세스에 다음 경로가 필요하다. 이 문서는 환경변수나 운영 실행기를 변경하지 않는다.

```text
TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe
TESSDATA_PREFIX=C:/Users/junpr/autojebi/data/ocr/tessdata-fast
WORKSPACE_OCR_LANGUAGES=kor+eng
```

OCR 결과는 항상 `review_required=true`, `complete=false`다. 위 고정 검증 입력에는 실제 회사 개인정보가 없으며 TEST ONLY로 표시했다. 모델 confidence는 원문 일치나 제출 승인 근거로 쓰지 않는다.

## 자동 검증

`pytest tests/test_workspace_attachment_text.py tests/test_workspace_pdf_text.py -q`: 47건 통과.

신규 회귀는 HWPX·HWP·중첩 ZIP 본문/표 인용 경로, 원본 해시, SHA 이름의 Worker 허용 경로, 저장 원본 변조, 공유 압축·엔트리·OCR·HWP 한도, 중첩 zip-slip, 형식 불일치, 미지원 자료의 미완료 상태와 언어 누락 진단을 확인한다. 수정한 추출·OCR·실행·테스트 파일의 Ruff 검사도 통과했다.
