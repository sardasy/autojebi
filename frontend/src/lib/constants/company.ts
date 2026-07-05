// 회사 기본값 상수.
// NEXT_PUBLIC_* env는 빌드타임에 번들로 인라인되어 Docker 운영 시 런타임 주입이 안 되는 함정이 있어
// env 없이 순수 상수로 관리한다.
export const DEFAULT_COMPANY_NAME = "미림씨스콘";
