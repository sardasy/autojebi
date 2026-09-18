import { type ExtractedArchiveMember, type ExtractedPage } from "@/lib/workspace";

const archiveIssues: Record<string, string> = {
  archive_depth_limit: "중첩 ZIP 깊이 초과 · 개별 파일로 등록하세요",
  hwp_worker_required: "HWP 실행기 연결 필요", hwp_worker_auth_missing: "HWP 실행기 인증 설정 필요",
  hwp_worker_unavailable: "HWP 실행기 연결 확인 필요", hwp_member_limit: "HWP 처리 개수 초과 · 나누어 등록하세요",
  member_format_mismatch: "확장자와 실제 파일 형식 불일치", unsupported_member_format: "미지원 형식 · 변환본 필요",
  hwp_member_storage_unsafe: "HWP 임시 저장 경로 확인 필요", hwp_member_source_changed: "HWP 원본 변경 · 다시 등록하세요",
};

const ocrIssues: Record<string, string> = {
  ocr_engine_missing: "OCR 프로그램 설치 필요", ocr_engine_unavailable: "OCR 프로그램 실행 확인 필요",
  ocr_configuration_invalid: "OCR 설정 확인 필요", ocr_failed: "OCR 실패 · 원본 또는 변환본 확인 필요",
  ocr_timeout: "OCR 시간 초과 · 페이지를 나누어 등록하세요", ocr_page_limit: "OCR 페이지 한도 초과 · 나누어 등록하세요",
  ocr_disabled: "OCR 기능 설정 필요", ocr_output_limit: "OCR 결과 크기 초과 · 나누어 등록하세요",
  ocr_language_missing: "OCR 언어 파일 설치 필요",
};

export function ExtractionPages({pages}: {pages: ExtractedPage[]}) {
  return <>{pages.map(page => <div key={page.page_no}>
    <p>{page.page_no}쪽 · {page.status === "unread" ? "본문 미확보 · OCR 설정 또는 변환본 확인" : page.review_required ? "OCR 본문 · 원문 대조 필요" : "텍스트 확보"}{page.confidence != null ? ` · OCR 신뢰도 ${page.confidence}%` : ""}</p>
    {page.code && ocrIssues[page.code] && <p className="text-amber-800">{ocrIssues[page.code]}{page.missing_languages?.length ? `: ${page.missing_languages.map(language => ({kor: "한국어", eng: "영어", chi_tra: "번체 중국어"} as Record<string, string>)[language] || language).join(", ")}` : ""}</p>}
  </div>)}</>;
}

export function ArchiveMembers({members}: {members: ExtractedArchiveMember[]}) {
  return <ul className="space-y-1 pl-3 border-l mt-2">{members.map(member => <li key={member.name} className="break-all">
    <p>{member.name} · {member.complete ? "본문 확보" : member.status === "unsupported" ? "미지원 형식 · 변환본 필요" : "본문 확인 필요"}</p>
    {member.error_code && <p className="text-amber-800">{archiveIssues[member.error_code] || "추출 오류 · 원본 파일 확인 필요"}</p>}
    {member.extraction?.pages && <ExtractionPages pages={member.extraction.pages}/>}
    {!!member.extraction?.members?.length && <ArchiveMembers members={member.extraction.members}/>}
  </li>)}</ul>;
}
