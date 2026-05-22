from pydantic import BaseModel


class BidSpecs(BaseModel):
    공고명: str = ""
    발주기관: str = ""
    추정가격: str = ""
    납기: str = ""
    입찰마감: str = ""
    공사_용역_유형: str = ""
    주요_기술요건: list[str] = []
    필수_자격_면허: list[str] = []
    현장_위치: str = ""


class BidSummaryOutput(BaseModel):
    summary: str
    specs: BidSpecs
    relevance_note: str = ""
