#!/usr/bin/env python3
import json
import os
import subprocess
import urllib.parse
from pathlib import Path

BASE = "https://open.feishu.cn/open-apis"
ROOT = Path(__file__).resolve().parents[1]


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
    command = ["curl", "--fail-with-body", "--silent", "--show-error", "--request", method,
               "--header", "Content-Type: application/json; charset=utf-8"]
    if token:
        command += ["--header", f"Authorization: Bearer {token}"]
    if body is not None:
        command += ["--data-binary", json.dumps(body, ensure_ascii=False)]
    command.append(url)
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=60)
    payload = json.loads(result.stdout) if result.stdout.strip() else {"code": result.returncode, "msg": result.stderr.strip()}
    if payload.get("code") != 0:
        raise RuntimeError(payload)
    return payload


def col_name(index):
    out = []
    while index:
        index, rem = divmod(index - 1, 26)
        out.append(chr(ord("A") + rem))
    return "".join(reversed(out))


def main():
    load_env_file()
    app_id, secret = os.environ.get("FEISHU_APP_ID"), os.environ.get("FEISHU_APP_SECRET")
    if not app_id or not secret:
        raise SystemExit("Set FEISHU_APP_ID and FEISHU_APP_SECRET")
    token = request("POST", f"{BASE}/auth/v3/tenant_access_token/internal", body={
        "app_id": app_id, "app_secret": secret
    })["tenant_access_token"]
    wiki = os.environ.get("FEISHU_WIKI_TOKEN", "PkYRwLa92il1oEkLI0kcE8zknEc")
    query = urllib.parse.urlencode({"token": wiki})
    node = request("GET", f"{BASE}/wiki/v2/spaces/get_node?{query}", token)["data"]["node"]
    spreadsheet = node["obj_token"]
    sheets = request("GET", f"{BASE}/sheets/v3/spreadsheets/{spreadsheet}/sheets/query", token)["data"]["sheets"]
    result = []
    for sheet in sheets:
        props = sheet.get("grid_properties", {})
        rows, cols = min(props.get("row_count", 200), 200), min(props.get("column_count", 26), 40)
        cell_range = f"{sheet['sheet_id']}!A1:{col_name(cols)}{rows}"
        encoded = urllib.parse.quote(cell_range, safe="!")
        values = request("GET", f"{BASE}/sheets/v2/spreadsheets/{spreadsheet}/values/{encoded}", token)["data"]["valueRange"].get("values", [])
        result.append({"metadata": sheet, "range": cell_range, "values": values})
    output = ROOT / "work" / "feishu_snapshot.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({"node": node, "sheets": result}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"sheet_count": len(result), "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

