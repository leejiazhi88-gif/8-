#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import urllib.parse
from pathlib import Path

BASE = "https://open.feishu.cn/open-apis"
ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "quarter_profit.json"
DEFAULT_WIKI_TOKEN = "PkYRwLa92il1oEkLI0kcE8zknEc"
DEFAULT_SHEET_ID = "676109"


def load_env_file():
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def request(method, url, token=None, body=None):
    command = [
        "curl", "--fail-with-body", "--silent", "--show-error",
        "--request", method, "--header", "Content-Type: application/json; charset=utf-8",
    ]
    if token:
        command += ["--header", f"Authorization: Bearer {token}"]
    if body is not None:
        command += ["--data-binary", json.dumps(body, ensure_ascii=False)]
    command.append(url)
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=60)
    payload = json.loads(result.stdout) if result.stdout.strip() else {
        "code": result.returncode, "msg": result.stderr.strip()
    }
    if payload.get("code") != 0:
        raise RuntimeError(payload)
    return payload


def validate_data(data):
    matrix = data.get("matrix", [])
    if len(matrix) != 18 or any(len(row) != 31 for row in matrix):
        raise ValueError("Expected an 18 x 31 matrix")
    if len(data.get("periods", [])) != 18 or len(data.get("l1s", [])) != 31:
        raise ValueError("Period or industry metadata has an unexpected size")
    return matrix


def column_name(index):
    out = []
    while index:
        index, rem = divmod(index - 1, 26)
        out.append(chr(ord("A") + rem))
    return "".join(reversed(out))


def number_styles(sheet_id, matrix):
    integer_ranges, decimal_ranges = [], []
    for row_index, row in enumerate(matrix, start=2):
        for column_index, value in enumerate(row, start=2):
            column = column_name(column_index)
            cell_range = f"{sheet_id}!{column}{row_index}:{column}{row_index}"
            (decimal_ranges if abs(float(value)) < 10 else integer_ranges).append(cell_range)
    return [
        {"ranges": integer_ranges, "style": {"formatter": "0", "thousandSeparator": True}},
        {"ranges": decimal_ranges, "style": {"formatter": ""}},
    ]


def display_matrix(matrix):
    """Round only single-digit values to one decimal, preserving numeric types."""
    return [
        [round(float(value), 1) if abs(float(value)) < 10 else value for value in row]
        for row in matrix
    ]


def tenant_token():
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        raise SystemExit("Set FEISHU_APP_ID and FEISHU_APP_SECRET in .env or the environment")
    return request("POST", f"{BASE}/auth/v3/tenant_access_token/internal", body={
        "app_id": app_id, "app_secret": app_secret
    })["tenant_access_token"]


def spreadsheet_token(token, wiki_token):
    query = urllib.parse.urlencode({"token": wiki_token})
    node = request("GET", f"{BASE}/wiki/v2/spaces/get_node?{query}", token)["data"]["node"]
    if node.get("obj_type") != "sheet":
        raise RuntimeError(f"Wiki node is not a sheet: {node.get('obj_type')}")
    return node["obj_token"]


def main():
    parser = argparse.ArgumentParser(description="Write quarterly industry profit data to Feishu Sheets.")
    parser.add_argument("--check", action="store_true", help="Validate local data without calling Feishu.")
    args = parser.parse_args()
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    matrix = validate_data(data)
    if args.check:
        print(json.dumps({"rows": len(matrix), "columns": len(matrix[0]), "cells": 558}))
        return

    load_env_file()
    token = tenant_token()
    wiki_token = os.environ.get("FEISHU_WIKI_TOKEN", DEFAULT_WIKI_TOKEN)
    sheet_id = os.environ.get("FEISHU_SHEET_ID", DEFAULT_SHEET_ID)
    spreadsheet = spreadsheet_token(token, wiki_token)
    target_range = f"{sheet_id}!B2:AF19"
    written_matrix = display_matrix(matrix)
    written = request("PUT", f"{BASE}/sheets/v2/spreadsheets/{spreadsheet}/values", token, {
        "valueRange": {"range": target_range, "values": written_matrix}
    })
    styles = number_styles(sheet_id, matrix)
    request("PUT", f"{BASE}/sheets/v2/spreadsheets/{spreadsheet}/styles_batch_update", token, {"data": styles})
    verified = request(
        "GET",
        f"{BASE}/sheets/v2/spreadsheets/{spreadsheet}/values/{urllib.parse.quote(target_range, safe='!')}",
        token,
    )["data"]["valueRange"].get("values", [])
    if verified != written_matrix or not all(isinstance(value, (int, float)) for row in verified for value in row):
        raise RuntimeError("Read-back verification did not match the written matrix")
    print(json.dumps({
        "range": target_range, "rows": 18, "columns": 31, "cells": 558,
        "revision": written.get("data", {}).get("revision"),
        "all_numeric": True,
        "integer_cells": len(styles[0]["ranges"]),
        "decimal_cells": len(styles[1]["ranges"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
