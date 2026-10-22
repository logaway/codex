# 设计规范（contract）

规范是一份 JSON：配色、字号层级、边距、网格，再加上何时用、何时不用、禁止清单。它是机器可读的设计系统：提示词里的要求模型可以无视，规范里的算术不行。

## 内置规范

| 名称 | 适合 |
|---|---|
| `editorial-report` | 复盘、评审，需要细读或打印。论述多于数字 |
| `exec-brief` | 给决策者的短汇报，5 分钟，数字是主角 |
| `technical-deck` | 架构评审、技术分享，投影而非打印。深色、信息密 |
| `stat-callout` | 战略汇报，要权威感，一页一个超大数字 |
| `review-scorecard` | 季度业务回顾、客户成功汇报，目标与偏差要经得起追问 |

按场景选，不按话题选。`python3 scripts/deckforge_cli.py contracts` 会列出每套规范的 `use_when` / `not_when`；`not_when` 能把你从"看起来很合适"的近似选项引到正确的那套。

## 手写一套规范

适用于用户直接给了色值、要合并多个参考，或者要微调提取结果。做法：

```bash
python3 scripts/deckforge_cli.py show exec-brief > <工作目录>/styles/acme.json
```

改完以后，`name` 字段要和文件名一致（这里是 `acme`），名字不要与内置规范重名。渲染时带上同一个 `--styles` 目录。

```json
{
  "name": "acme",
  "use_when": "Acme 品牌对外汇报",
  "not_when": {},
  "signature": "一句话描述这套设计的辨识特征",
  "avoid": ["这套设计里不该出现的东西", "..."],
  "canvas": {"w": 1280, "h": 720},
  "grid": 8,
  "margin": {"x": 80, "top": 72, "bottom": 56},
  "gutter": 56,
  "fonts": {"serif": "思源宋体", "sans": "思源黑体", "heading": "可选，标题专用字体"},
  "colors": {"bg": "#FFFFFF", "ink": "#111111", "body": "#3C4650",
             "muted": "#6B7280", "accent": "#C8102E", "rule": "#DCDCDC"},
  "type": {
    "display": {"size": 56, "font": "serif", "weight": 600, "color": "ink"},
    "lead":    {"size": 24, "font": "sans", "color": "muted"},
    "metric":  {"size": 68, "font": "serif", "weight": 600, "color": "ink"},
    "h2":      {"size": 34, "font": "serif", "weight": 600, "color": "ink"},
    "h3":      {"size": 21, "font": "sans", "weight": 600, "color": "ink"},
    "body":    {"size": 18, "font": "sans", "color": "body"},
    "eyebrow": {"size": 14, "font": "sans", "tracking": 2, "color": "accent"},
    "caption": {"size": 13, "font": "sans", "color": "muted"}
  },
  "rules": {"dividers": true, "cards": false, "index": false}
}
```

要点：

- **8 个字号角色缺一不可**（display、lead、metric、h2、h3、body、eyebrow、caption），`font` 引用 `fonts` 里的键
- **标题与正文的字号比保持在 2.5 倍以上**（display / body）。层级弱是 deck 显得业余的最大单一原因
- **颜色对比度**：ink 对 bg ≥ 7，body ≥ 4.5，muted 与 accent ≥ 3。强调色只用于眉标、标记和当前阶段，不要大面积填充
- **margin 和 gutter 用 8 的倍数**，否则几何检查会报网格偏移
- **`avoid` 要具体。** 实际最常发生的失败是装饰悄悄回来了，而不是漏了什么。"任何渐变""为每栏配不同颜色"比"保持简洁"有用得多
- `rules.dividers`：是否画发丝分隔线。`rules.index`：points 页是否加 01/02 序号
