# 本地曲谱同步与导聆

播放器现支持曲目切换：拉威尔《左手钢琴协奏曲》与沃恩·威廉斯《云雀高飞》（The Lark Ascending）。打开本地页面后在顶部选择曲目；也可直接打开 [《云雀高飞》](http://127.0.0.1:8765/?track=lark-ascending)。切换会暂停音频，并同步切换谱页、小节时间轴、导聆、录音阵容与文献。

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

校验页是轻量测试界面，尚未实现工作流规定的最终 React 导聆播放器。右侧已经支持用户分析工作稿的随播放导聆、曲目信息与参考文献；正文已完成面向听众的成稿修订；逐音符及同步精度另行复核。

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

试听参考用简单正弦音色，局部录音做了响度归一化以便比较。它们不是原录音的新版本，不代表已由人工试听验收。素材、缓存、处理及校正均留在本地。

## PDF / OMR 复现

已在 `.tools/` 解包官方 Audiveris 5.11.0，未作为系统应用安装；英文 OCR 模型来自官方 Tesseract 仓库。运行样本：

```powershell
./scripts/run_omr_samples.ps1
```

重建 PDF 坐标需要 `pdfplumber` 和 Poppler。本次使用应用附带的 PDF Python 运行时：

```powershell
& 'C:\Users\32599\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/map_pdf.py
```

该几何提取器针对已提供的矢量 PDF，不是通用 PDF 识谱工具。原工作流仍是 `WORKFLOW_Ravel_Left_Hand_Concerto.md`；历史输入审查见 `reports/input-audit.md`，后续实测状态以本次测试报告为准。

## 暂缓事项

M4A 仅为用户询问，现按要求悬置，未接入当前曲目流程；当前仍使用已提供的 MP3。相关早期实验记录不作为正式支持承诺。
