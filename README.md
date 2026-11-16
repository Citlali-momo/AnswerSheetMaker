# A3 数学答题卡生成器

把原来那份 TikZ 版 `A3答题卡条形码版.tex` 改成可配置的生成器：改标题、换涂卡/填表、
上彩色或黑白、给 15—19 题插立体几何图，最后输出 A3 PDF 直接打印。

有两个版本，版面参数完全一致：

| 版本 | 入口 | 需要什么 |
|---|---|---|
| **网页版（推荐给老师）** | `web\打开答题卡生成器.bat` | 只要一个能用的浏览器，不装 Python、不装 LaTeX、不联网 |
| Python 版 | `answer_sheet.py` | Python + matplotlib + Pillow |

老师用的操作说明在 `web\使用说明_老师版.md`，全部鼠标操作。

---

## 0. 网页版（学校里最常用）

双击 `web\打开答题卡生成器.bat`，浏览器会打开一个左右分栏的页面：左边填表，右边实时预览。

- 改大标题 / 副标题 / 页脚
- 答题卡版本二选一：**标准考试版**（带注意事项、填涂样例、试卷类型、缺考标记、条形码）/ **平时考试版**（这五块全省，选择题与填空上移，16 题独占中栏）
- 选择题在「机读涂卡」和「填写答案（表格）」之间切换
- 彩色 / 黑白，还能点色块换主色
- 15—19 题（含续答区，共 8 个位置）各自贴一张图，填宽度自动等比缩放
- 点「生成 PDF 文件」直接下载；PDF 打不开时可以用「另存为图片」
- 「直接打印（A3）」跳过 PDF 直接唤起打印

脚本会依次尝试 Edge、Chrome，都没有就让 Windows 自己挑程序打开 html。

**Windows 7 注意**：不需要装任何东西，但浏览器要支持画布功能。IE11 不行，会显示大字提示；装 Chrome 或用 360/QQ 浏览器的「极速模式」即可。

自动检查：浏览器地址后面加 `?selftest=1`，会跑 29 项检查（量字宽、页高、两种模式的版面高度、两种答题卡版本的版式差异、页面墨迹、PDF 结构、xref 偏移等），全过显示绿条，有失败项显示红条并把序号标出来。

---

## 1. Python 版快速开始

```bat
cd /d D:\Cyrene-work\AnswerSheetMaker

:: 1) 直接生成默认答题卡
python answer_sheet.py -o out\答题卡.pdf

:: 2) 只改大标题
python answer_sheet.py --title "2026年某某中学高三年级第一次模拟考试" -o out\答题卡.pdf

:: 3) 黑白 + 填答案表格
python answer_sheet.py --choice-mode table --color-mode bw -o out\答题卡_黑白.pdf

:: 4) 给第 15 题右上角插立体几何图
python answer_sheet.py --image 15=figs\cube.png --image-width 4.6 -o out\答题卡.pdf

:: 5) 顺带生成 PNG 预览（会得到 preview-1.png / preview-2.png），并做版面自检
python answer_sheet.py -o out\答题卡.pdf --preview out\preview.png --check
```

懒人版：双击 `run_samples.bat`，会在 `out\` 里生成彩色涂卡版和黑白填答版（带插图）各一份。

依赖：`matplotlib`、`Pillow`（本机已具备）。

---

## 2. 两种答题卡版本

| 版本 | 参数 | 版面 |
|---|---|---|
| 标准考试版 | `--layout standard`（默认） | 注意事项、填涂样例、试卷类型、缺考标记、条形码粘贴区齐全；第一页中栏是「续15题 + 16题」上下分栏 |
| 平时考试版 | `--layout daily` | 这五块全部省掉；第一栏选择题/填空/15 题整体上移 4.88 cm，15 题答题区从 11.0 cm 变成 15.9 cm；中栏由 16 题独占 |

也可以写进配置文件：`"layout": "daily"`。页脚、页码、顶部定位码、姓名和考生号都保留。

---

## 3. 两种选择题模式

| 模式 | 参数 | 样子 |
|---|---|---|
| 机读涂卡 | `--choice-mode bubble`（默认） | 1—11 题按 4 行 3 列排布，每题 A B C D 四个涂卡括号 |
| 填答案表格 | `--choice-mode table` | 上面「单项选择题 1—8」一张表，下面「多项选择题 9—11」一张表；**多选格宽度是单选的 2 倍** |

表格模式下，单选题每格宽约 1.36 cm，多选题每格宽约 2.71 cm，答案行高 0.92 cm，够写 `ABD`。

题量可改：`single_choice_count` / `multiple_choice_count`。涂卡模式按每列 4 题排，超过 12 题请改用表格模式。

---

## 4. 配色

| 需求 | 参数 |
|---|---|
| 彩色（默认粉色 255,50,165） | `--color-mode color` |
| 换成红色 | `--color-mode color --primary-color 255,0,0` |
| 黑白（省钱、校内速印） | `--color-mode bw` |

`--primary-color` 支持 `255,50,165`、`#FF32A5`、`FF32A5` 三种写法。
黑白模式下所有色值统一为黑，答题框、涂卡括号、页脚都不会失真。

---

## 5. 插图（立体几何图）

键名对应答题区域：

| 键 | 位置 |
|---|---|
| `15` | 第 1 页左列，解答题框（15 题起始区） |
| `cont15` | 第 1 页中列上 1/4（续 15 题） |
| `16` | 第 1 页中列下 3/4 |
| `17` | 第 1 页右列 |
| `18` | 第 2 页左列 |
| `cont18` | 第 2 页中列上半（续 18 题） |
| `19` | 第 2 页中列下半 |
| `cont19` | 第 2 页右列（续 19 题） |

图片默认贴在区域**右上角**，按原比例缩放；不写 `width`/`height` 时取 4.8 cm 宽。
图片过大时会自动按区域大小等比缩小，不会压出边框。

命令行写法：

```bat
python answer_sheet.py --image 15=figs\cube.png --image 17=figs\a.png --image-width 4.6
```

配置文件的写法（可以给每张图单独设尺寸/边距/左右）：

```json
"images": {
  "15": { "path": "figs/cube.png", "width": 4.6, "margin": 0.15, "align": "top-right" },
  "19": { "path": "figs/cone.png", "height": 3.2, "align": "top-left" }
}
```

- `width` / `height` 只给一个时按比例推算另一个；两个都给就按给定尺寸拉伸。
- `margin` 是图片与答题框内边的距离（cm），默认 0.15。
- `align`：`top-right`（默认）或 `top-left`。

想先看看效果，可以生成一张示例图：`python demo_figure.py figs\cube.png`。

---

## 6. 配置文件

不带 `-c` 时，程序会自动读取当前目录的 `config.json`；也可以 `-c 我的配置.json`。
命令行参数优先级高于配置文件。

| 字段 | 说明 | 默认 |
|---|---|---|
| `title` | 大标题（过长会自动缩字号，再长会拆两行） | 2026年普通高等学校招生全国统一考试 |
| `subtitle` | 副标题 | 数学答题卡 |
| `footer_template` | 页脚，可用 `{page}` `{pages}` | 数学答题卡第{page}面（共{pages}面） |
| `choice_mode` | `bubble` / `table` | bubble |
| `color_mode` | `color` / `bw` | color |
| `primary_color` | 主色 | [255, 50, 165] |
| `single_choice_count` | 单选题数 | 8 |
| `multiple_choice_count` | 多选题数 | 3 |
| `student_id_digits` | 考生号格数 | 10 |
| `paper_types` | 试卷类型两行文字 | 试卷A / 试卷B |
| `question_labels` | 各题题号与分值文字 | 15.（13分）… |
| `continuation_split` | 续答区占整列的比例（16 题顶部的「续15题」、19 题顶部的「续18题」） | 0.25 / 0.5 |
| `notes` | 注意事项条目（字符串数组） | 与原题一致 |
| `blank_questions` | 填空题题号 | 12 / 13 / 14 |
| `hint_text` | 答题区提示语 | 请在各题目的答题区域内作答… |
| `fonts.latin` | 数字与英文字体 | Times New Roman（新罗马） |
| `fonts.body_cn` | 中文正文字体 | SimSun（宋体） |
| `fonts.bold_cn` | 中文加粗字体 | SimHei（黑体） |

字体用「西文在前、中文在后」的回退链实现：数字和字母命中新罗马，新罗马没有的汉字自动落到宋体或黑体。想换西文字体，把 `latin` 改成 `Arial`、`Georgia` 等即可，中文部分不受影响。

把当前配置导出成模板（方便对照着改）：

```bat
python answer_sheet.py --dump-config config.json
```

---

## 7. 打印

- 纸张：**A3 横向**，每页排 3 个 A4 竖版答题区；共 2 页。
- 缩放：**实际大小 / 100%**，不要选「适合页面」，否则涂卡位置会偏。
- 双面：两页正好是一张 A3 的正反面，选**短边翻转**；裁开或对折后就是 6 个 A4 面。
- 彩色版建议彩色打印（粉色细线黑白复印会变浅），校内速印用 `--color-mode bw` 更清晰。

---

## 8. 版面自检

```bat
python answer_sheet.py --check
```

会检查三类问题：文字越出页面、文字超出所在边框、文字之间重叠。
换长标题、改题量、加图之后跑一遍比较稳妥。

---

## 9. 文件说明

```
AnswerSheetMaker/
├─ answer_sheet.py                    Python 版主程序（生成矢量 PDF）
├─ config.json                        默认配置
├─ demo_figure.py                     生成示例立体几何图
├─ run_samples.bat                    一键出两份示例
├─ figs/cube.png                      示例插图
├─ web/
│  ├─ answer_sheet.html               网页版（单文件，无外部依赖）
│  ├─ 打开答题卡生成器.bat               双击启动网页版
│  └─ 使用说明_老师版.md                老师用的操作说明
├─ samples/                           生成效果示例（PDF + 首页预览图）
├─ out/                               本地生成物（已在 .gitignore 中忽略）
├─ LICENSE                            MIT
└─ README.md
```

示例效果（仓库 `samples/` 里）：彩色涂卡版、黑白填答版（带立体几何插图）各一份 A3 两页 PDF 和首页预览图。

---

## 10. 和原 .tex 的差别

- 用 Python 绘制 PDF 代替 XeLaTeX 编译，机器上不需要 TeX 环境；线宽、字号都按 cm/pt 精确换算，版面坐标沿用原文件的 cm 体系。
- 原文件里 15—19 题的续答区（「（续15题）」等）保留，且可以单独插图。
- 选择题新增「填答案表格」模式；涂卡模式保留原来的中括号样式。
- 页脚「第N面（共2面）」、条形码粘贴区、试卷类型、填涂样例、缺考标记、8 个定位黑块、考生号格都按原位保留。
- 网页版复用同一套版面参数，用浏览器画布重绘，让没有 Python / TeX 的机器也能直接用。

---

## 11. 致谢与许可

版面依据一份 TikZ 编写的 A3 数学答题卡（`A3答题卡条形码版.tex`）重建，条形码区、涂卡样式与页脚沿用其设计。

代码以 MIT 许可发布，见 [LICENSE](LICENSE)。

