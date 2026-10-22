---
name: deckforge
description: 生成看起来像专业设计、而不是 AI 模板的 PPT，输出原生可编辑的 .pptx。只要用户要做 PPT、幻灯片、演示文稿、汇报、复盘、路演、评审 deck、slides、presentation，就使用本技能；用户抱怨 AI 生成的 PPT 难看、廉价、像模板、不专业，或者上传图片、截图、品牌规范 Excel，要求"照这个风格 / 用我们的品牌色"做 PPT 时，也要使用，即使没有明确说"生成 PPT"。还涵盖把 PPT 生成接入 LangChain / agent 应用。
---

# deckforge

做出看起来经过设计、而不是生成出来的 PPT。

## 核心分工：你写内容，脚本算几何

**不要手写任何坐标、宽度、间距、字号或颜色。**

这不是风格偏好。模型写出来的几何会以一种可测量的方式出错：三张并列卡片宽 368 / 368 / 395，同类图标半径 18 / 16 / 19，一页里有几十处偏离 8px 网格。代码里看不出来，读者却会觉得"不专业"，又说不出原因。

几何是算术，比如 `(内容宽 - 栏间距 × (n-1)) / n`，交给脚本算。你的工作是决定每页讲什么、属于哪种信息结构、标题写成什么结论。

## 流程

所有命令在本技能目录下执行（`python3 scripts/deckforge_cli.py ...`），输出都是 JSON。
`--styles` 和 `--out` 指向用户的工作目录，不要写进技能目录。

### 1. 弄清场景，别问审美

用户通常说不清想要什么视觉效果，所以问情境，最多三个问题：

- 谁看，有多少时间？
- 有没有喜欢的参考稿、品牌色或品牌规范？（有就走第 2 步的"有参考"）
- 大概几页？

信息够推断的话就不问，在回复里用一句话写明你的假设，然后继续。

### 2. 定样式

**用户上传了图片或 Excel 作为样式参考**：

```bash
python3 scripts/deckforge_cli.py style <文件> --styles <工作目录>/styles
```

返回的 `name` 就是要用的规范名。把下面几项用一两句话告诉用户：从文件里取到了什么（`from_file`）、哪些颜色因可读性被调整过（`adjustments`）、需要安装哪些字体（`notes`）。颜色被改了却不说，用户会以为你取错了色。

上传的 Excel 如果是**数据**（销量表、财务表），它是内容来源，不是样式参考，不要提取样式。分不清时问一句。

细节、能力边界和常见情况见 `references/style-reference.md`。

**没有参考**：

```bash
python3 scripts/deckforge_cli.py contracts
```

按 `use_when` / `not_when` 选，看场景，不看话题。"技术话题就用深色科技风"恰恰是产出模板感的那种反射：同样的内容，给投资人看和给工程师看，需要的设计不同。

### 3. 先定结构，再写字

写一份 `deck.json`：每页先判断信息的**结构**，再选版式。格式、8 种版式的字段和字数上限见 `references/shapes.md`，写之前先读。

两条最影响观感的规则：

- **标题写结论，不写标签。** 「华东续约率落后其他大区 9 个点」，而不是「区域分析」。只读标题就能跟上整份论证，这是专业 deck 和"一堆幻灯片"的主要区别，而且不花任何视觉成本。
- **结构决定版式，不要反过来。** 有先后才用 timeline，真对立才用 compare，数字是论据才用 metrics。至少换用两种版式；statement 全篇最多一两次。

不确定的数字不要编。用户没给数据的地方，写成定性陈述，或者在回复里请用户补。

### 4. 渲染

```bash
python3 scripts/deckforge_cli.py render deck.json --out <工作目录>/out --styles <工作目录>/styles --preview
```

- `errors` 非空：按错误修改 deck.json 后重跑。错误写得很具体，比如"第 2 页 items 有 6 项，上限 4"。
- `warnings`：标题像标签、文字被截断。截断说明文案太长，要**删字**，排版不会替你解决。
- `findings` 里的 P0 / P1：几何问题。正常情况下引擎不会产生；出现了说明内容极端（比如一页塞满上限）。拆页或精简内容。
- `avoid`：所选规范的禁止清单，交付前逐条对照内容自查。

### 5. 看渲染结果，不看代码

有 `--preview` 时打开 `out/review.png`，逐页看 **PPTX 的渲染**。PowerPoint/LibreOffice 会替换字体、重新排字，结构上完全正确的文件仍可能出现：

- 数字被拆成两行、页脚折行
- 大片死白，或某页明显比其他页满
- 技术上没错、但视觉上呆板的页面

有问题就改 deck.json 重渲染。没有 LibreOffice（`preview` 失败）时，在回复里说明你没能目视检查。

### 6. 交付

给出 `.pptx` 路径，并如实说明：这是高质量初稿，花十分钟人工微调效果最好。把生成稿说成定稿，用户发现问题后会失去信任。

如果规范里用了用户电脑上可能没有的字体（尤其是从 Excel 读到的品牌字体），提醒用户：字体缺失时 PowerPoint 会替换字体，并可能重新换行。

## 依赖

需要 Python 3.10+ 和 `python-pptx`、`pydantic`；样式提取需要 `Pillow`、`openpyxl`；预览需要 `libreoffice` 与 `pdftoppm`。缺包时先 `pip install python-pptx pydantic Pillow openpyxl`。

## 参考文件

- `references/shapes.md`：deck.json 格式、8 种版式、字数上限。**写 deck.json 前必读**
- `references/style-reference.md`：从图片 / Excel 提取样式的能力与边界
- `references/contracts.md`：设计规范的字段，以及如何手写一套新规范（比如用户直接给了色值）
- `references/langchain.md`：用户要把 PPT 生成接入 LangChain / agent 应用时读
