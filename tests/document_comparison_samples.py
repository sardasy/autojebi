"""Synthetic immutable-policy fixtures (no real company information)."""
import io
import zipfile

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
CONTROL = '<hp:ctrl><hp:fieldBegin><hp:parameters><hp:integerParam>9</hp:integerParam><hp:stringParam>Clickhere:set:42:Direction:wstring:0: HelpState:wstring:0:</hp:stringParam></hp:parameters></hp:fieldBegin></hp:ctrl>'


def archive(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        for name, content in entries:
            z.writestr(zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0)), content)
    return stream.getvalue()


def cell(text, row=0, col=0, inner=""):
    return f'<hp:tc><hp:subList><hp:p><hp:run><hp:t>{text}</hp:t>{inner}</hp:run></hp:p></hp:subList><hp:cellAddr rowAddr="{row}" colAddr="{col}"/><hp:cellSpan rowSpan="1" colSpan="1"/></hp:tc>'


def table(text="220 V", ident="table-1", inner=""):
    return f'<hp:tbl id="{ident}" rowCnt="1" colCnt="1"><hp:tr>{cell(text,inner=inner)}</hp:tr></hp:tbl>'


def section(body):
    return f'<hp:sec xmlns:hp="{HP}">{body}</hp:sec>'


def sample():
    return archive([("Contents/section0.xml", section(
        f'<hp:p><hp:run>{CONTROL}<hp:t>😀 Clickhere 9 본문</hp:t></hp:run></hp:p>'
        f'<hp:p><hp:run>{table()}</hp:run></hp:p>'))])


def reference(text="😀 Clickhere 9 본문\n220 V", value="220 V"):
    start = text.index(value)
    return {"text": text, "tables": [{"reference_table_id": "table-1", "locator": "blocks/1",
            "rows": 1, "cols": 1, "parent_cell": None, "cells": [{"locator": "blocks/1/cells/0/0",
            "row": 0, "col": 0, "row_span": 1, "col_span": 1, "text": value,
            "start": start, "end": start+len(value)}]}]}
