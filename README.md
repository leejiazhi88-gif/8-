# 8- 利润表

通过飞书开放 API 同步申万一级行业季度归母净利润。当前数据覆盖 2022Q1–2026Q2，共 18 个季度、31 个行业，单位为亿元。

## 文件

- `data/quarter_profit.json`：已同步的数据矩阵及取数统计
- `data/derived_sheets.json`：TTM、同比和最新行业汇总审计数据
- `scripts/write_quarter_profit.py`：写入飞书并回读校验
- `scripts/write_derived_sheets.py`：写入第 2、3 表，并新增刷新后的第 4 表副本
- `scripts/inspect_feishu_sheet.py`：读取 Wiki 表格结构和内容快照

## 使用

复制 `.env.example` 为 `.env`，填写飞书应用凭据。应用需要目标 Wiki/电子表格的读取和编辑权限。

```bash
cp .env.example .env
python3 scripts/write_quarter_profit.py --check
python3 scripts/write_quarter_profit.py
```

默认写入 Wiki `PkYRwLa92il1oEkLI0kcE8zknEc` 的首个工作表 `676109`，范围为 `B2:AF19`。也可通过环境变量覆盖 Wiki token 和 Sheet ID。写入后脚本会回读全部 558 个单元格并逐项核对。

脚本始终写入数值类型：绝对值达到 10 的数值使用整数和千位分隔符显示；仅绝对值小于 10 的数值四舍五入到 1 位小数并使用常规数字格式。原始数值及精度保留在 `data/quarter_profit.json`。

“年TTM利润同比涨幅”以数值比例写入并使用两位小数的百分比格式，例如底层数值 `0.7174` 显示为 `71.74%`。

最新“汇总一览表”的 G、K、M、N～U、W、Y、Z 列以数值比例写入，并使用两位小数的百分比格式。

## 数据口径

- 数据源：Tushare 利润表
- 指标：归属于母公司股东的净利润（`n_income_attr_p`）
- 行业：申万 2021 一级行业
- 单季值：Q1 直接取累计值；Q2/Q3/Q4 使用本期累计值减上期累计值
- 重复报表：优先采用 `update_flag=1` 的最新记录
- 单位：亿元，保留两位小数
