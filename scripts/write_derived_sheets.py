#!/usr/bin/env python3
import json
import os
import subprocess
import urllib.parse
from pathlib import Path

from write_quarter_profit import BASE, DEFAULT_WIKI_TOKEN, load_env_file, request, tenant_token, spreadsheet_token

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "derived_sheets.json"
SHEET_TTM = "YhOty9"
SHEET_YOY = "Oj41pd"
SHEET_SUMMARY_SOURCE = "WIPtkJ"
SUMMARY_TITLE = "汇总一览表（26.9.9）"


def col_name(index):
    out = []
    while index:
        index, rem = divmod(index - 1, 26)
        out.append(chr(65 + rem))
    return "".join(reversed(out))


def rounded(value):
    if value is None or not isinstance(value, (int, float)):
        return value
    return round(float(value), 1) if abs(float(value)) < 10 else value


def style_groups(sheet_id, rows, row_offset=2, col_offset=2):
    integer, decimal = [], []
    for r, row in enumerate(rows, row_offset):
        for c, value in enumerate(row, col_offset):
            if value is None or not isinstance(value, (int, float)):
                continue
            cell = f"{sheet_id}!{col_name(c)}{r}:{col_name(c)}{r}"
            (decimal if abs(float(value)) < 10 else integer).append(cell)
    styles = []
    if integer:
        styles.append({"ranges": integer, "style": {"formatter": "0", "thousandSeparator": True}})
    if decimal:
        styles.append({"ranges": decimal, "style": {"formatter": ""}})
    return styles


def percentage_style(sheet_id, rows, row_offset=2, col_offset=2):
    ranges = []
    for r, row in enumerate(rows, row_offset):
        for c, value in enumerate(row, col_offset):
            if isinstance(value, (int, float)):
                ranges.append(f"{sheet_id}!{col_name(c)}{r}:{col_name(c)}{r}")
    return [{"ranges": ranges, "style": {"formatter": "0.00%"}}]


def summary_percentage_styles(sheet_id, row_count):
    columns = ["G", "K", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "W", "Y", "Z"]
    return [{"ranges": [f"{sheet_id}!{column}3:{column}{row_count + 2}" for column in columns],
             "style": {"formatter": "0.00%"}}]


def write_and_verify(token, spreadsheet, sheet_id, start, matrix):
    start_col, start_row = start
    end_col = start_col + max(len(row) for row in matrix) - 1
    end_row = start_row + len(matrix) - 1
    target = f"{sheet_id}!{col_name(start_col)}{start_row}:{col_name(end_col)}{end_row}"
    request("PUT", f"{BASE}/sheets/v2/spreadsheets/{spreadsheet}/values", token,
            {"valueRange": {"range": target, "values": matrix}})
    encoded = urllib.parse.quote(target, safe="!")
    values = request("GET", f"{BASE}/sheets/v2/spreadsheets/{spreadsheet}/values/{encoded}", token)["data"]["valueRange"].get("values", [])
    if values != matrix:
        raise RuntimeError(f"Readback mismatch: {target}")
    return target


def find_or_add_summary(token, spreadsheet):
    sheets = request("GET", f"{BASE}/sheets/v3/spreadsheets/{spreadsheet}/sheets/query", token)["data"]["sheets"]
    for sheet in sheets:
        if sheet["title"] == SUMMARY_TITLE:
            return sheet["sheet_id"], False
    reply = request("POST", f"{BASE}/sheets/v2/spreadsheets/{spreadsheet}/sheets_batch_update", token, {
        "requests": [{"addSheet": {"properties": {"title": SUMMARY_TITLE, "index": len(sheets), "gridProperties": {"rowCount": 201, "columnCount": 30}}}}]
    })["data"]["replies"][0]
    return reply["addSheet"]["properties"]["sheetId"], True


def copy_summary_headers(token, spreadsheet, new_sheet):
    source = f"{SHEET_SUMMARY_SOURCE}!A1:AD2"
    encoded = urllib.parse.quote(source, safe="!")
    headers = request("GET", f"{BASE}/sheets/v2/spreadsheets/{spreadsheet}/values/{encoded}", token)["data"]["valueRange"]["values"]
    def plain(value):
        if isinstance(value, list) and all(isinstance(part, dict) for part in value):
            return "".join(str(part.get("text", "")) for part in value)
        return value
    headers = [[plain(value) for value in row] for row in headers]
    return write_and_verify(token, spreadsheet, new_sheet, (1, 1), headers)


def summary_matrix(rows):
    fields = ["name", "top5", "total_mv_trillion", "count", "avg_mv_yi", "over_800", "over_800_ratio", "pe",
              "total_profit_yi", "avg_profit_yi", "profit_yield", "pb", "roe", "ret_250", "ret_ytd", "ret_5",
              "ret_10", "ret_20", "ret_60", "ret_120", "daily_ret", "vol", "turnover", "amount", "week_ret",
              "month_ret", "count", "rank", "index_code", "latest"]
    result = []
    for row in rows:
        values = []
        for field in fields:
            value = row.get(field)
            percentage_ratio_fields = {"over_800_ratio", "profit_yield", "roe"}
            percentage_point_fields = {"ret_250", "ret_ytd", "ret_5", "ret_10", "ret_20", "ret_60", "ret_120",
                                       "daily_ret", "turnover", "week_ret", "month_ret"}
            if field in percentage_point_fields and value is not None:
                value /= 100  # 百分数 -> 飞书百分比单元格底层比例
            elif field == "vol" and value is not None:
                value *= 10000  # Tushare 申万日线：万股 -> 股
            elif field == "amount" and value is not None:
                value *= 1000  # Tushare 申万日线：千元 -> 元
            values.append(value if field in percentage_ratio_fields | percentage_point_fields else rounded(value))
        result.append(values)
    return result


def main():
    load_env_file()
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    token = tenant_token()
    spreadsheet = spreadsheet_token(token, os.environ.get("FEISHU_WIKI_TOKEN", DEFAULT_WIKI_TOKEN))

    ttm_rows = [[rounded(v) for v in row] for row in data["ttm"] if row is not None]
    # 审计数据以百分数记录（如 71.74）；飞书百分比单元格底层应写 0.7174。
    yoy_rows = [[None if v is None else float(v) / 100 for v in row] for row in data["yoy"] if row is not None]
    ttm_range = write_and_verify(token, spreadsheet, SHEET_TTM, (2, 2), ttm_rows)
    yoy_range = write_and_verify(token, spreadsheet, SHEET_YOY, (2, 2), yoy_rows)
    request("PUT", f"{BASE}/sheets/v2/spreadsheets/{spreadsheet}/styles_batch_update", token,
            {"data": style_groups(SHEET_TTM, data["ttm"][:len(ttm_rows)])})
    request("PUT", f"{BASE}/sheets/v2/spreadsheets/{spreadsheet}/styles_batch_update", token,
            {"data": percentage_style(SHEET_YOY, yoy_rows)})

    summary_sheet, created = find_or_add_summary(token, spreadsheet)
    header_range = copy_summary_headers(token, spreadsheet, summary_sheet)
    summary = summary_matrix(data["summary"])
    summary_range = write_and_verify(token, spreadsheet, summary_sheet, (1, 3), summary)
    request("PUT", f"{BASE}/sheets/v2/spreadsheets/{spreadsheet}/style", token, {"appendStyle": {
        "range": f"{summary_sheet}!A1:AD2", "style": {"font": {"bold": True}, "backColor": "#D9EAF7",
                                                        "hAlign": 1, "vAlign": 1}
    }})
    request("PUT", f"{BASE}/sheets/v2/spreadsheets/{spreadsheet}/styles_batch_update", token,
            {"data": style_groups(summary_sheet, summary, row_offset=3, col_offset=1)})
    request("PUT", f"{BASE}/sheets/v2/spreadsheets/{spreadsheet}/styles_batch_update", token,
            {"data": summary_percentage_styles(summary_sheet, len(summary))})

    numeric = sum(isinstance(v, (int, float)) for matrix in (ttm_rows, yoy_rows, summary) for row in matrix for v in row)
    print(json.dumps({"ttm": ttm_range, "yoy": yoy_range, "summary_sheet": summary_sheet,
                      "summary_created": created, "headers": header_range, "summary": summary_range,
                      "numeric_cells": numeric, "as_of": data["as_of"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
