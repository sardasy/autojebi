ENERGY_KEYWORDS = {
    "core": [
        "전기공사", "전력설비", "수배전반", "변전소", "송전선로",
        "배전선로", "전력케이블", "GIS", "차단기", "변압기",
        "ESS", "에너지저장장치", "태양광", "풍력", "신재생에너지",
        "전기설비", "수전설비", "동력설비", "조명설비", "접지공사",
        "전력계통", "SCADA", "EMS", "배전자동화", "스마트그리드",
    ],
    "related": [
        "전기안전", "전기감리", "전력품질", "역률개선", "절연저항",
        "내선공사", "외선공사", "가공전선로", "지중전선로", "분전반",
        "MCC", "UPS", "비상발전기", "축전지", "인버터",
        "EV충전", "전기차충전", "AMI", "스마트미터", "DR",
        "VPP", "마이크로그리드", "직류배전", "HVDC", "전력변환",
    ],
    "certification": [
        "전기공사업", "전력시설물", "전기안전관리", "전기기사",
        "전기공사기사", "신에너지전문기업", "KEPIC",
    ],
}

WEIGHTS: dict[str, float] = {"core": 3.0, "related": 1.5, "certification": 2.0}

ENERGY_ORGS: set[str] = {
    "한국전력공사", "전력거래소", "한전KPS", "한국전력기술", "한국수력원자력",
}

ALL_KEYWORDS: list[str] = (
    ENERGY_KEYWORDS["core"] + ENERGY_KEYWORDS["related"] + ENERGY_KEYWORDS["certification"]
)
