# Ariadne · 曲谱同步与导聆

**从这里开始：** [项目导航](项目导航.md) · [文档目录](docs/README.md) · [视频制作流程](docs/workflows/video-production.md) · [分析撰写流程](docs/workflows/analysis-writing.md)。

日常使用根目录的“启动播放器.bat”和唯一字幕入口“编辑视频字幕.bat”。字幕编辑器启动后选择鹅妈妈、拉威尔完整版或95秒样片，可修改文字、时间、位置、字体及滚动速度。视频脚本集中在 `scripts/video_export/`，本机草稿与字号偏好在 `local/video-export/`，当前拉威尔完整版JSON仍在 `output/video-export/ravel-full-001/captions-editable.json`。项目与位置配置统一见 `config/video-export.json`。演出视频和本机资源包不上传GitHub。

拉威尔当前四个模块为**和声、配器与织体、声部关系与复调、曲式与主题发展**；动机关系为共享数据，不新增第五个面板。其他作品的已有模块和数据保持独立，以下历史记录保留当时的称谓与验证范围。

材料如何选择、如何为新作品生成同步，以及各处理环节的适用范围，见 **[AGENTS.md](AGENTS.md)**。本轮成果与限制见 [工作总结](docs/WORK_SUMMARY.md)。

**马勒演出视频不随 GitHub 仓库分发。** 使用马四预计算同步需自行在本机放置清单对应的视频；没有该视频时，一键启动会选择材料齐全的曲目。原有两首音频示例可独立使用。

## 拉威尔独立视频版

曲目菜单新增“拉威尔 · 左手钢琴协奏曲（艾马尔视频）”，入口为 `/?track=ravel-left-hand-video`。原齐默尔曼音频版保留。视频使用自身音轨重新对齐，复用原总谱、导聆、5篇研究文章及MusicXML证据；不会把两场演出的录音时间混用。片头和谢幕可继续观看，音乐窗口外停用和声／活跃乐器及谱面播放线。

视频仅存本机，不提交Git。其他机器需按 `works/ravel-left-hand-video/media-sync.json` 的路径、字节数和SHA-256恢复同一视频；缺失时启动器继续选择可播放曲目。视频版通过HTTP与模拟DOM／媒体联调，本轮浏览器控制被Work设置禁用，未声称已真实浏览器实播验收。[同步与检查报告](reports/ravel-video-20261026.md)。

## 当前研究路线：先形成音乐判断

谱面上方现只有一套四维HUD：**和声、配器与织体、对位、曲式**。和声区分当前记谱音响与具有独立范围的背景分析；配器区分活跃分部和职责候选。宽度足够时单排四卡，较窄时两列，移动端可折叠。分析区域已加高，支持拖动右下角调整高度；和弦、并列层读法及全部活跃分部不再截断，曲式显示段落范围与已有模型说明。内容较多时各卡片可独立滚动。点击卡片，在右侧“技术证据”查源音符及研究来源，一键返回正在播放的谱页。完整小节阅读器也移到该面板，默认折叠，不跳录音。

此次整合的自动测试与实际HTTP／模拟DOM联调已通过；浏览器控制被Work设置禁用，**本轮真实布局与实播未运行**。[统一HUD与四组音乐案例报告](reports/musicxml-hud-integration-20261026.md)。原音频版此前的真实浏览器检查保留为[历史验收记录](reports/ravel-acceptance-20261026.md)，不代替本轮验收。

拉威尔完整管弦乐MusicXML已接入主要符号流程：music21解析37个分部、535小节，生成逐音事件、6,660个和声窗口、转位、声部音程和全谱乐器活动；XML小节与PDF区域独立关联。录音同步继续使用原有结果，音乐分析不再以MIDI—PDF匹配清零为门槛。默认技术卡片并列展示逐谱研究与XML证据，旧自动候选可勾选查看。

“技术证据”中的完整小节数据可独立选择全部535小节，查看和声、配器、声部与逐音底稿；该选择不跳转录音。源音符ID可点开核查。罗马数字以指定局部调性为条件；重建音集不一致时显示“条件性级数待审查”，冻结原输出仍保留。全谱自动计算与人工签核分别记录，尚非全曲最终和声归约。

[MusicXML接入与实际分析报告](reports/ravel-musicxml-analysis-20261026.md) · [逐音表](output/research/ravel-musicxml/note-events.csv) · [全谱和声台账](output/research/ravel-musicxml/harmonic-ledger.csv) · [乐器活动](output/research/ravel-musicxml/instrument-activity.csv)。重算可选安装`requirements-analysis.txt`，预计算播放仍仅需原最小依赖。

[音乐分析成果与工作流](reports/ravel-musical-studies-20261026.md) · [符号底稿、原谱图与人工签核范围](analysis/score-studies/symbolic-windows-20261026.md)。底稿由代理逐谱录入与图像对照，人工签核仍待完成；不把候选数量或软件通过当作音乐学验收。

## 拉威尔研究范式试验

可折叠的“谱面技术分析”按各自范围更新四张卡，缺少背景归约时显示“待分析”，不会把上一瞬间的和弦继承为背景。既有35条研究事件、直接读谱记录及第1–3、10–15页的旧离线候选均保留；旧PDF/MIDI候选在技术证据面板按需勾选，**不是已人工核验的逐音分析**。同一主张的不同来源在详情并列，XML小节索引不再重复生成四个主按钮。手动翻页会分别标明播放位置和浏览页。

右侧新增“诠释研究”，提供5篇可独立滚动的跨区间文章。默认阅读不随播放、翻页或seek重置；可开启“自动跟随相关诠释”。文章的相关乐段按钮目前仅打开谱页，提示音频位置待核查，不把粗页码直接当成可信的音频起点。《云雀高飞》和马四没有新研究数据时显示空状态，原导聆与媒体播放继续使用。

数据放在 `analysis/structural-events.json`、`hermeneutic-essays.json` 与 `essays/`，接口为 `/api/research?track=ravel-left-hand`。录音秒数在运行时投影，不永久写进作品分析。版次与PDF指纹错误会拒绝套用；原15段短导聆、同步、谱面映射及录音资料保持不变。方法、数据规范和测试范围见 [研究范式](docs/design/research-paradigm.md) 与 [拉威尔试验报告](docs/archive/ravel-pilot-report.md)。

## 早期PDF＋MIDI辅助引擎（保留为可选证据）

新增可复现流程：`PDF＋辅助MIDI → 原始证据 → 四维推断 → 验证 → HUD`。Harmony、Counterpoint、Orchestration、Form 各自输出不同粒度的记录，Motif 保留可替换接口。算法不读取旧文章或论文；文献比较另存，冻结记录不覆盖。播放预计算结果仍只需要最小 Python 依赖。

```powershell
# 在 synctoolbox 或其他处理环境中运行
python -m pip install -r requirements-processing.txt
python -m backend.structure_analysis build --profile analysis/engine/profiles/ravel-vector-pilot.json --output analysis/engine/ravel-pilot --activate
python -m backend.structure_analysis validate analysis/engine/ravel-pilot/round1-a7657439303a57e6
```

旧自动引擎快照保留为**辅助候选**。其局部逐音实验的范围不再阻塞独立配器和全曲结构研究；完整节奏、声部、踏板与曲式功能仍分别核查。`/api/structure` 提供统计，`/api/structure-evidence` 提供逐音证据。版次或冻结文件损坏会拒绝该轮自动结果，并保留既有文章及播放器。

使用、数据格式、两轮研究与重建边界见[引擎说明](docs/design/music-structure-engine.md)，实际音乐内容、逐维统计和未通过的验收项见[本轮报告](reports/ravel-structure-engine.md)。

第二轮记谱核查修复八度归属、临时记号与震音展开，增加8组可展开的代理读谱记录；剩余分歧与实际音乐判断见[续轮报告](reports/ravel-ab-notation-review.md)。

## 首次使用

Windows 可直接双击根目录的 **[启动播放器.bat](启动播放器.bat)**。脚本自动进入项目目录、使用或创建 `.venv`，缺少播放组件时安装 `requirements.txt`，随后打开本地播放器（优先本地材料齐全的马勒第四，否则选择可用曲目）。若同一项目已经运行，会直接打开现有实例；端口占用时自动选择其他本地端口。首次创建环境需要已安装 Python 3.11 或更新版本，安装依赖时需要联网；预计算结果播放不需安装 OMR／对齐工具。

需要 Python 3.11 或更新版本，推荐 Python 3.12。仓库包含两首作品的音频、PDF、MIDI、分析和预计算同步结果，克隆后无需重新计算。播放器依赖可通过 pip 安装，不需要 Codex、Conda、Node.js 或系统 PDF 工具。

```sh
git clone https://github.com/Sundance0604/Ariadne.git
cd Ariadne
```

Windows（PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe start.py
```

macOS / Linux：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python start.py
```

打开终端显示的 [本地播放器地址](http://127.0.0.1:8765/)，在顶部选择作品。关闭时在终端按 Ctrl+C。如端口占用，可运行 `python start.py --port 8766` 并打开对应地址。首次打开每张谱页时会在本机生成图片，之后读取缓存。请在浏览器中点击播放；人工校正使用“保存人工锚点”写入本地项目。

播放器在本机运行，GitHub 仓库页面本身不是在线播放器。公开仓库中的示例媒体由项目提供者明确授权随项目上传；运行时不会把音频、乐谱或校正数据发送给远程分析服务。

若希望重新计算同步或运行全部测试，再安装 `requirements-processing.txt`；也可运行 `conda env create -f environment.yml` 后使用 `synctoolbox` 环境。后文 OMR 小样属于可选研究流程，仍需另行准备 Audiveris 和 Poppler，不影响已收录曲目的播放。

## 已收录曲目

新增本地马勒《第四交响曲》视频试验入口：[打开马勒第四](http://127.0.0.1:8765/?track=mahler-4)。视频直接发声，底部统一控制播放、进度、音量、速度和 A/B 循环；顶部可切换研读、观演与专注布局。原有纯音频曲目使用同一播放器。

已提取用户视频的音轨，并用四个乐章 MIDI 完成全曲离线候选对齐（1,244 个参考段，不能直接当作原谱小节号）。原扫描谱现已接入 **172 个系统区域与 384 个小节细分候选**，支持自动高亮、翻页、区域跟随及点击跳转。108 个系统在参数对照中较稳定，64 个仍需重点复核；红框提示疑点，也可勾选“仅显示稳定候选”。全部结果仍未完成人工逐音验收，不能称为精确逐小节同步。人工区域时间校正在“同步信息与人工校正”中保存并立即生效。新的分析稿、9 项文献和四乐章正文已接入；当前导聆拆为 **38 个短段落**（最长 5 页，部分同页分段），随谱面位置切换，手动翻页也能阅读对应段落。下方进度条提供 **四个乐章按钮**，点击同步跳转视频、谱页与导聆，单乐章作品不显示。马四另新增可点击的小节编号层与“乐章＋小节号”定位：**≈ 表示识图计数候选**，各乐章从 1 重新计数；排练号作为独立位置参考。可在“同步信息与人工校正 → 小节编号校正”修改编号与本框小节数，后续自动号码随之更新。详见 [小节编号与定位](reports/mahler4-measure-numbering.md)。详见 [跟谱与分析实测](reports/mahler4-score-sync.md)。视频只在本机读取，不随项目数据导出，默认忽略 MP4/MKV 文件。

如需重建马勒第四候选结果，先安装 `requirements-processing.txt` 与 `requirements-media.txt`，再运行 `python scripts/build_mahler4_video.py --align`。该入口复用现有离线引擎，不替代 PDF → OMR；没有 MIDI 的自动对齐仍依赖可用的 OMR 结果。仅播放预计算结果仍只需 `requirements.txt`。

原有两首纯音频曲目仍保留：拉威尔《左手钢琴协奏曲》与沃恩·威廉斯《云雀高飞》（The Lark Ascending）。打开本地页面后在顶部选择曲目；也可直接打开 [《云雀高飞》](http://127.0.0.1:8765/?track=lark-ascending)。切换会暂停媒体，并同步切换谱页、小节时间轴、导聆、录音阵容与文献。

曲库白名单位于 `library.json`。拉威尔保留原有根目录数据；《云雀高飞》的同步、谱面映射、项目、录音资料、分析导出与报告隔离在 `works/lark-ascending/`。人工锚点也分别存储；当前页面暂存的锚点在切回曲目时恢复，关闭页面前仍需点击保存。

《云雀高飞》使用用户提供的希拉里·哈恩、科林·戴维斯爵士、伦敦交响乐团录音及 35 页 Godderis 署名谱。全曲得到 309 个候选分节，其中 98 个标为重点复核、211 个尚未人工确认。其原稿保留备份，修订导聆覆盖所有谱页；实际同步结果与限制见 `works/lark-ascending/reports/`。所有结果仍须人工试听确认，华彩和自由节奏处的播放线只表示所在谱面区域的估计进度。

## 拉威尔既有测试与通用操作

已经用用户创建的 Conda `synctoolbox` 环境完成真实录音的**MIDI 辅助全曲离线对齐测试**。已提供 535 个候选小节的时间映射、原始重排 PDF 的页面区域、本地播放校验页、异常清单和试听文件。

当前是可检查的自动候选结果。**33 个小节被标为重点复核，其余 502 个也尚未人工确认。** 全谱 PDF → OMR → 无用户 MIDI 的端到端路径尚未完成，不能把本次 MIDI 测试当作该路径的验收。

## 打开本地校验页

在此目录的终端运行：

```powershell
conda activate synctoolbox
python scripts/serve_review.py
```

打开 [本地校验页](http://127.0.0.1:8765)。服务器只监听 `127.0.0.1`。如端口被使用，可以加 `--port 8766` 并访问对应端口。

可以播放、暂停、跳转小节、调节速度、查看原 PDF 高亮、保存人工锚点和导出 JSON。第 33–36 个 MIDI 候选小节共用华彩谱面区域，不会绘制不存在的小节线。页面坐标对应 **100 页重排 PDF**；99 页扫描谱目前只用于核对和 OMR 小样，不能复用重排谱坐标。

新增贯穿当前 PDF 整页的红色播放线，播放时连续移动，暂停时停留，跳转与变速后跟随录音位置；可用“显示播放线”开关隐藏。旁边显示小节内（华彩时为整个共用区域）的估计进度。位置由已有非线性对齐映射反查参考时间，再在谱面区域内插值，**不是逐音符坐标或准确的拍点**；华彩共用区域连续推进，不在每个候选小节开头重置。

当前播放器沿用本地 Python 与原生 JavaScript。右侧已经支持用户分析工作稿的随播放导聆、曲目信息与参考文献；正文已完成面向听众的成稿修订；逐音符及同步精度另行复核。

## 分析文档、曲目信息与论文

右侧“当前导聆”读取 `resource/ravel left hand piano concerto/analysis/Ravel_Left_Hand_Concerto_Full_Analysis.md` 的第 9 节，以修订后的 15 个页码范围覆盖当前 100 页谱面。已将任务式工作稿改为导聆成稿，并核对关键速度标记和页面边界；原稿备份与证据见 `reports/analysis-editorial-review.md`。内容跟随**播放位置**切换，手动翻看其他谱页时不会误把播放导聆切到那一页。选择“导聆段落”可直接跳到对应位置；也可展开完整原文。修改文档后点击“刷新分析文档”即可重新读取，不需重跑对齐。

“曲目信息”来自 `metadata/recording.json`，当前阵容为 Krystian Zimerman / Pierre Boulez / London Symphony Orchestra（LSO）。该文件分别保存作品、录音、演奏者、指挥、乐团及分析文档关联，音频和 PDF 指纹不匹配时会拒绝套用这份资料。

“参考文献”保留第 11 节的 8 项资料，区分研究论文、学位论文、作品导赏及研究另一部协奏曲的延伸比较。两篇 MTO 论文与当前分析有关的章节已经核对，其余文献逐项说明实际阅读状态。

运行 `python scripts/analysis_data.py` 可导出 `analysis/annotations.json`，其中标明定位精度为原稿 PDF 页码范围。实际显示直接从原稿读取，因此不依赖导出 JSON 是否重新生成。Markdown 渲染使用 Conda 环境中已有的 Mistune 3.3.3；依赖记录在 `requirements-review.txt`。

## 重新计算与校正

```powershell
python scripts/align_recording.py
python scripts/validate_alignment.py
python -m unittest discover -s tests -v
```

第一次运行会提取整首音频的特征，随后从 `.tools/features/` 读取按输入指纹命名的缓存。算法为 Sync Toolbox 1.4.2 的 MrMsDTW，使用 chroma + DLNCO，另外计算 chroma-only 对照。没有按固定 BPM 或总时长均分小节。

在校验页试听并保存后，人工锚点位于 `review-anchors.json`。用新输出文件重算以保留旧结果：

```powershell
python scripts/align_recording.py --anchors review-anchors.json --output alignment.corrected.json
```

重算入口验证文件指纹与锚点顺序，并保护已有人工复核结果，拒绝直接覆盖含确认状态或人工锚点的输出。拉威尔在校验页读取根目录 `alignment.json`；纠正版应先独立检查，再明确切换，不会静默替换。原拉威尔验证脚本也固定处理根目录 `alignment.json`。《云雀高飞》读取自身目录的数据，不能把一首作品的锚点用于另一首作品。

## 输出

| 文件 | 用途 |
| --- | --- |
| `project.json` | 输入指纹及各处理环节状态 |
| `alignment.json` / `alignment.path.npz` | 候选小节时间映射、质量指标、原始全曲 DTW 路径 |
| `measure-map.json` | PDF 页面、印刷编号、候选 MIDI 小节与矩形区域；包含局限说明 |
| `reports/alignment-test.md` | 实测报告、测试证据与尚未完成的事项 |
| `reports/alignment-anomalies.csv` | 重点复核小节与依据 |
| `reports/omr-review.md` | 四页真实 OMR 小样的结果与识谱风险 |
| `output/alignment/alignment-diagnostics.png` | 全曲路径、特征分歧与独立音频诊断 |
| `output/alignment/review-opening.wav` | 开头试听，左声道录音、右声道按映射重定时的简化音符参考 |
| `output/alignment/review-cadenza.wav` | 华彩段相同形式的试听 |
| `output/alignment/review-ending.wav` | 结尾相同形式的试听 |
| `output/alignment/ravel-recording-timed.mid` | 按录音时间重定时的 MIDI 听辨辅助文件；其拍位置不能当作原谱小节位置 |

试听参考用简单正弦音色，局部录音做了响度归一化以便比较。它们不是原录音的新版本，不代表已由人工试听验收。运行中的缓存、处理及校正均保存在本地。

## PDF / OMR 复现

新增通用 PDF → MusicXML 接口，马勒第七的物理第 1 页已实际转换、解析并用 MuseScore 重新排版。当前输出仍有拍号、节奏、谱号及文字识别错误，属于待人工校正的 OMR 草稿；实测对照和数字见 [马勒第七报告](reports/mahler7-omr.md)。

按乐章的连续识别入口为 `./scripts/transcribe_mahler.ps1 -Movement 1`，读取 `works/mahler-7/movements.json` 的五个乐章范围；加 `-Status` 可查看该乐章的检查点进度。它使用原生多页 `.omr` 连续导出，独立保存每个乐章，并保留失败和分段状态。当前范围确认与处理情况见 [乐章转录记录](reports/mahler7-movements.md)。

```powershell
./scripts/convert_score.ps1
```

默认仅转换马勒第七第 1 页，450 DPI，重复执行会验证并复用缓存。可用 `-Pages '1,3-5'`、`-Pdf '其他乐谱.pdf'`、`-Output 'output/omr/其他作品'` 指定输入，用 `-MuseScore 'MuseScore4.exe 的实际路径'` 生成重排 PNG。各页独立输出 `.omr`、`.mxl`、`.musicxml` 和日志，不会自动合并为全曲。详细 API、依赖及失败恢复见 [接口说明](docs/guides/pdf-to-musicxml.md)。

已在 `.tools/` 解包官方 Audiveris 5.11.0，未作为系统应用安装；英文 OCR 模型来自官方 Tesseract 仓库。运行样本：

```powershell
./scripts/run_omr_samples.ps1
```

重建 PDF 坐标需要安装 `requirements-processing.txt` 中的 `pdfplumber`；OMR 小样图像转换另需 Poppler。运行：

```powershell
python scripts/map_pdf.py
```

该几何提取器针对已提供的矢量 PDF，不是通用 PDF 识谱工具。原工作流仍是 `docs/workflows/ravel-left-hand-original.md`；历史输入审查见 `reports/input-audit.md`，后续实测状态以本次测试报告为准。

## 暂缓事项

M4A 仅为用户询问，现按要求悬置，未接入当前曲目流程；当前仍使用已提供的 MP3。相关早期实验记录不作为正式支持承诺。
