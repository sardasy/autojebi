ROUTING: dict[str, str] = {
    "HIL": "Sangjun",
    "SW": "Sangjun",
    "IGBT": "이용문",
    "SCR": "이용문",
    "수동소자": "이용문",
    "ABB장비": "이용문",
    "혼합": "Sangjun / 이용문",
    "비관련": "미배정",
}


def assignee_for_category(category: str) -> str:
    return ROUTING.get(category, "미배정")

