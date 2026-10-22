# deck.json 与版式

## 目录
- 整体结构
- 结论式标题
- 8 种版式（title / metrics / points / compare / timeline / statement / table / pipeline）
- 字数上限
- 页面节奏

## 整体结构

```json
{
  "meta": {"contract": "exec-brief", "org": "NORTHWIND", "date": "Q3 2026", "footer": "内部资料"},
  "pages": [ {"shape": "title", ...}, ... ]
}
```

- `meta.contract`：设计规范名（内置的，或 `style` 命令返回的 name）
- `meta.org` / `meta.date`：每页顶部的细栏，左边机构名，右边日期或状态。建议填写：它在读者读内容之前就交代了"这是什么文件"
- 每页都可以加 `eyebrow`（2–6 字的小引语）和 `stamp`（右上角标记，如「草稿」「机密」）
- **不要加别的字段。** 多余字段会被当成错误，几何字段更是不存在

## 结论式标题

title 和 statement 以外的每一页，`title` 都写成一句陈述该页结论的完整句子。

| 标签（不要） | 结论（要） |
|---|---|
| 四个阶段 | 分四阶段切换，每阶段都可回滚 |
| 风险 | 三个风险需要在本周决策 |
| Q3 业绩 | Q3 销量超计划，毛利未达标 |

渲染时，像标签的标题（6 字以内，或以「概述」「分析」「总结」结尾）会出现在 warnings 里。看到就改写。

## 8 种版式

### title：封面，第 1 页必须是它
```json
{"shape": "title", "eyebrow": "年度复盘", "title": "增长守住了，结构在承压", "subtitle": "一句可选的定调"}
```
标题控制在 14 字内。标题折成三行就不像标题了。

### metrics：2–4 个数字就是论据
```json
{"shape": "metrics", "title": "营收超额 4%，获客成本同步恶化",
 "items": [{"label": "营收", "value": "104%", "unit": "达成率", "note": "一两句背景。"}]}
```
`value` 要短：「42%」「3.1pt」「¥2.4M」。在 value 里写句子，这个版式就失去意义了。孤立的数字没有说服力，尽量在 unit 或 note 里给出对照基准（同比、目标、行业）。

### points：2–4 个同等权重的并列要点
```json
{"shape": "points", "title": "...", "items": [{"heading": "短标题", "body": "两三句话。"}]}
```
只在真正并列时使用。如果其中一条明显更重要，就把它单独做成 statement，其余删掉。

### compare：正好两侧的真对立
```json
{"shape": "compare", "title": "...",
 "sides": [{"label": "可复制", "heading": "来自产品与流程", "rows": ["每条一行", "2–5 条"]},
           {"label": "不可复制", "heading": "来自一次性因素", "rows": ["...", "..."]}]}
```
适合前后、我方与对手、可持续与一次性。两个只是并存的话题不要用它。

### timeline：2–5 个有先后意义的阶段
```json
{"shape": "timeline", "title": "...", "steps": [{"when": "Q1", "heading": "阶段名", "body": "做什么。"}]}
```
顺序本身要承载读者需要的信息。只是凑巧有五条的列表不是时间线。

### statement：一句主张，全篇的转折点
```json
{"shape": "statement", "eyebrow": "建议", "text": "先收折扣权限，再谈华东加投。", "attribution": "可选的一行补充"}
```
全篇最多一两次。它的力量来自稀缺：满篇 statement 等于一直在喊。

### table：对照或评估表
```json
{"shape": "table", "title": "...", "columns": ["指标", "华东", "其他", "差距"],
 "weights": [3, 1, 1, 1], "rows": [["获客成本", "¥3.2k", "¥2.1k", "+52%"]]}
```
2–5 列，最多 8 行，每行列数等于 columns。`weights` 是各列的相对宽度，第一列会作为行标题加粗。

### pipeline：阶段 + 当前位置
```json
{"shape": "pipeline", "title": "...",
 "stages": [{"label": "诊断", "state": "done", "note": "一两行。"},
            {"label": "设计", "state": "current"}, {"label": "试点", "state": "next"}]}
```
适合观众需要知道"项目走到哪了"的场合。只能有一个 `current`，它是唯一被强调色填充的格子。

## 字数上限（中文按字计）

| 字段 | 上限 | 字段 | 上限 |
|---|---|---|---|
| title | 24 | heading | 12 |
| text（statement） | 30 | label | 8 |
| subtitle | 34 | value | 10 |
| attribution | 26 | unit | 14 |
| eyebrow | 8 | note | 44 |
| body | 90 | compare 每行 | 24 |

超限会被校验拦下来，或者在渲染时被截断。正确做法是删字，而不是换个版式硬塞。

## 页面节奏

- 不要连续用同一种版式。连续五页 points，每页都没错，整份却很单调。常见节奏：`title → metrics → compare → timeline → statement`
- 各页的饱满度保持接近。忽空忽满的翻页体验，读起来就像没有规划，即使每页单独看都合格
