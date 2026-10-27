# Ariadne：部署、材料选择与曲谱同步生成指南

本文件面向部署者、提供材料的用户，以及继续开发本仓库的代理。请从仓库根目录执行示例命令。用户明确的任务范围优先；不要因本文件增加未被要求的上传、通知或审批流程。

## 1. 当前能力与边界

Ariadne 是本地 Python HTTP 服务加原生 JavaScript 模块的曲谱导聆播放器。目前不是 React 应用，也不需要 Node.js 才能播放。音频／视频、谱页、高亮、估计播放线、分段赏析和文献可以在同一界面研读。

| 路径 | 已实现的工作 | 不应误称为已完成的工作 |
|---|---|---|
| 录音 + 辅助 MIDI | 离线 chroma + DLNCO 特征、MrMsDTW、候选时间映射、异常诊断和人工锚点重算 | 精确逐音同步、独立校准过的准确率 |
| 矢量 PDF | 已有拉威尔和《云雀高飞》的谱面几何适配 | 对任何新 PDF 都可直接运行的通用识谱器 |
| 马四扫描谱 | 系统／小节框候选、识图计数、可点击号码、编号与时间分别校正 | 所有生成号码都等于已核验的原谱小节号 |
| 本地视频 | 音轨提取、视频主时钟、统一播放、同次演出音画锚点、乐章跳转 | 不同演出间可靠的自动音画同步 |
| PDF → MusicXML | 本地 Audiveris 接口、结构检查、失败重试、可选 MuseScore 重排、按乐章续跑实验 | 任意扫描总谱无校对即可完成全曲音符级对齐 |
| 赏析 | 按页／谱面段落关联正文、同页多段、出处和实际阅读状态 | 把 GPT 草稿或仅看过摘要的文献标为已核验全文 |

马四当前的 1,244 个 MIDI 参考段、1,253 个图像小节框候选与谱上的排练号是三种不同的标识。不要强行让它们一一同号。`≈` 代表自动识图计数候选。

## 2. 只想部署并播放

### Windows

安装 Python 3.11+，双击根目录 `启动播放器.bat`。它会进入项目目录，使用或创建 `.venv`，安装最小播放依赖，优先打开本地材料齐全的曲目，复用本项目已有服务或选择空闲本地端口。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe start.py --port 8765
```

### macOS / Linux

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python start.py --port 8765
```

打开终端显示的 `http://127.0.0.1:8765/`。端口占用时改为 8766 等空闲端口；终端 Ctrl+C 停止服务。服务只监听回环地址，不提供公网部署的账户、访问控制或反向代理配置。

预计算结果播放不需要 Audiveris、MuseScore、Conda 或 Node.js。首次创建环境与安装依赖需要联网，播放和本地识图不向外部分析服务上传材料。

**GitHub 不分发任何马勒演出视频。** 克隆后，拉威尔与《云雀高飞》的既有示例可播放；若缺少马四本地视频，一键启动会选择其他材料齐全的曲目。马四的数据和赏析保留在仓库，不能据此认为视频也已下载。

### 恢复马四本地视频

1. 查看 `works/mahler-4/media-sync.json` 的 `video.path`、`sha256`、`bytes`。
2. 将自己持有的**同一文件**放到 `video.path` 对应的项目相对位置；不要上传仓库。
3. 可用 PowerShell `Get-FileHash -Algorithm SHA256 -LiteralPath '实际视频路径'` 对照指纹。
4. 同一文件改过名字时，核对内容指纹后调整本地路径；如果重新压制、剪辑、变速或换了演出，必须重新准备媒体并对齐，不能改 JSON 指纹来假装兼容。
5. 刷新页面，选择马四。若报素材不匹配，保留旧结果，先核对输入；不要关闭校验来绕过。

## 3. 应该提供哪些材料

### 选择路线

| 手头材料 | 推荐路线 | 可以先得到什么 |
|---|---|---|
| PDF + 完整录音 + 同作品 MIDI | 优先使用 MIDI 辅助离线对齐，再建立 PDF 小节几何 | 候选时间同步，随后逐步增加谱面定位与校正 |
| PDF + 完整录音 + 经校对的 MusicXML | 保留 XML 原稿，导出辅助 MIDI，再核对 XML 与原 PDF 的对应 | 更可检查的结构参考；仍需解决 PDF 坐标 |
| 只有 PDF + 录音 | 先做少量页 OMR、人工校对，再决定是否扩展 | OMR 草稿与试验结果；不保证直接生成全曲同步 |
| 视频自带演出声音 + PDF + MIDI | 从该视频提取分析音轨，以视频为主时钟对齐 | 视频、谱面与赏析共用时间轴 |
| 视频 + 独立音频文件 | 先确认是否同一次演出，确认后设置音画锚点 | 锚点覆盖范围内的音画映射 |
| 无声音视频 | 人工时间锚点，不做不存在的音频特征匹配 | 人工定位；不能凭静音视频生成音高对齐 |
| 只有分析文字或不同版本材料 | 先补齐／核对对应的媒体与谱面 | 可读分析；不要制造同步边界 |

### PDF 选择

- 提供完整总谱，优先清晰的矢量 PDF；扫描件尽量端正、谱线连续、边缘完整、对比清楚。加高 DPI 不会自动修复印刷模糊、遮挡或音符粘连。
- 乐谱版本、编制、删节和反复应与实际演出相容。钢琴缩编、独奏分谱、不同修订版不能因为曲名相同就共用总谱坐标。
- 记录实际 PDF 物理页数、各乐章第一页和最后一页、封面／目录／空白页。物理第 5 页可能印着第 231 页，二者分别保存。
- 保留原文件。重新排版、裁切或重新扫描会改变指纹与坐标，需要新的映射；不要把旧矩形复制到新 PDF。
- 小节号是逐小节计数；排练号是间隔放置的位置标记；拍号是每小节节拍组织。识别到数字后先判断种类，不能把方框 7 直接认作第 7 小节。

### 录音选择

- 推荐连续、完整、可本地解码的 MP3、WAV 或 FLAC；保留作品开头、结尾和乐章之间的真实停顿。分轨录音先明确每轨所属乐章及顺序。
- 可以有片头／掌声，但必须记录音乐真正开始与结束的位置，并重点检查这些区域；DTW 的全文件端点约束并不是音乐入口已正确定位的证据。
- 不要用固定 BPM、总时长均分小节或按页数平均分配录音时间。自由速度、延长、华彩和停顿需要实际特征与人工锚点。
- 保留原始媒体指纹。为分析生成 WAV 缓存时同时记录源文件，不把解码缓存冒充用户原文件。

### MIDI / MusicXML 选择

- 优先同作品、同编制、结构完整的文件，检查乐章顺序、反复、删节、弱起、换拍、移调乐器和长休止。
- MIDI 是结构／音符参考，不必与录音采用相同速度；但乐曲顺序或内容不同，不会仅靠 DTW 自动变成正确。
- 检查开头、乐章中部、高潮、结尾的主题与原谱是否相符，而不是只看文件名或总时长。
- MIDI 常缺少可信的原谱编号、换拍或排版信息。必须把 MIDI 推断分节与 PDF 小节分开保存，直到有实际对应证据。
- MusicXML 需检查拍号、谱号、节奏、和弦、延音线、反复、声部身份与移调。若使用 MuseScore 导出 MIDI，保留原 XML 与导出说明。
- 当前对齐 CLI 的 `--midi` 接受 MIDI，不直接接受 `.mxl`；不要把后缀改成 `.mid`。

### 视频与独立音轨

- 推荐本地 MP4，浏览器通常更适合 H.264 视频与 AAC 音轨。FFmpeg 能读取的容器，不等于浏览器能直接播放。
- 视频自带音轨时，优先提取这一音轨用于对齐；不要拿另一场演出的唱片音轨替代，却继续宣称音画同源。
- 独立音频与视频即使曲名、指挥、乐团相同，也可能是不同剪辑或不同场次。没有同次演出证据时，不自动启用双源同步。
- 人工音画锚点至少两个，两列时间都严格递增，只在覆盖范围内映射。未覆盖区间不外推；较大漂移应暂停复核。

### 赏析与文献

- 提供可编辑的 Markdown、可靠来源链接与演出阵容。区分乐谱事实、文献观点、听觉解释与尚待核验的判断。
- 段落应给出物理页范围，最好进一步给出系统和页内位置或已核对的真实小节号；不必机械地“一页一段”，同页可以有多个段落。
- 对暂时没有位置依据的事件，保存 `unlocated`，不要按篇幅、页数或时间平均分配。
- 保留书目、DOI／链接以及实际阅读范围：全文、相关章节、摘要、出版信息或未阅读。GPT 原稿声称引用不等于已核验。

## 4. 文件组织与输入清单

新增作品使用独立目录，避免覆盖根目录的拉威尔示例：

```text
resource/my-work/
  score.pdf
  performance.mp3             # 或本地 performance.mp4，视频不提交 Git
  reference.mid
  analysis/full-analysis.md
works/my-work/
  project.json
  alignment.raw.json
  alignment.json
  measure-map.json
  metadata/recording.json
  analysis/annotations.json
  reports/
```

按需要增加 `media-sync.json`、`midi-movements.json`、`score-measures.json` 和人工校正文件。路径存为仓库相对路径，不依赖某位开发者的盘符、用户名或 Conda 目录。

输入清单至少记录：作品／曲目 ID、每个源文件的路径与 SHA-256、字节数、媒体时长、PDF 物理页数、乐章范围、录音阵容及信息来源、MIDI／XML 来源、编制／版本差异、反复与删节、当前复核状态。可以参考各作品的 `project.json`，但不要复制其他演出的指纹。

将曲目注册进 `library.json` 的 `tracks`，例如：

```json
{"id":"my-work","title":"作曲家 · 作品名","data_root":"works/my-work"}
```

`id` 是白名单标识，不是可由 URL 任意拼接的文件路径。`data_root` 必须位于项目目录内。仅增加曲库项不会自动生成缺失的对齐、谱面或分析文件。

## 5. 实现工作流程

### 第一步：小范围审查

先读取输入清单，核对 PDF 页数、乐章标题、媒体轨道与参考文件。选开头、中段、结束以及换拍／华彩的少量页进行试验，确认路线可行再扩展。不要直接把几百页扫描谱整部跑完后才发现参考版本不符。

### 第二步：准备处理环境

播放环境与计算环境可以分开。处理环境安装：

```powershell
python -m pip install -r requirements-processing.txt
python -m pip install -r requirements-media.txt
```

OMR 另安装 `requirements-omr.txt` 并准备本机 Audiveris。可选 MuseScore 用于重新排版核对。工具便携版、OCR 模型和音频特征缓存均放 `.tools/`，不提交 Git。路径通过参数或 `AUDIVERIS_PATH`、`FFMPEG_BINARY` 等已有配置指定；不要在新代码中写死本机软件盘符。

### 第三步：生成录音候选时间映射

通用 MIDI 辅助入口：

```powershell
python scripts/align_recording.py --audio "resource/my-work/performance.mp3" --midi "resource/my-work/reference.mid" --output "works/my-work/alignment.raw.json"
```

输出包含参考音符／推断小节、录音秒数、稀疏 `time_map`、原始 DTW 路径和异常信息。读取候选 JSON，检查时间单调、区间长度、重复材料和首尾定位；然后按本作品整理正式 `alignment.json`，增加真实乐章标记。不要仅重命名文件便称为已经人工确认。

视频先做本地准备：

```powershell
python scripts/prepare_video.py --video "resource/my-work/performance.mp4" --output "works/my-work"
python scripts/align_recording.py --audio "resource/my-work/performance.mp4" --midi "resource/my-work/reference.mid" --output "works/my-work/alignment.raw.json"
```

`prepare_video.py` 把分析音轨写入忽略的 `.tools/video-audio/`，并生成媒体清单。后一命令会复用该音轨。正式打包时参考 `build_mahler4_video.py`，使对齐使用的源视频指纹、播放主时钟与 `media-sync.json` 一致。

**作品适配边界：** `build_mahler4_video.py`、`map_mahler4_pdf.py`、`number_mahler4_pdf.py` 是当前马四素材的适配器；`map_pdf.py` 和 `map_lark_pdf.py` 也分别针对现有版本。新作品需要新增或参数化适配器，不能只改曲名就运行旧适配器。马四 MIDI 合并器当前要求四文件及 240 PPQ，其他文件须另行处理，不能静默套用。

### 第四步：建立原 PDF 几何

先区分矢量谱和扫描谱：矢量谱可读取线段和文字；扫描谱需要图像谱线／小节线／系统检测。几何与音符识别是两项不同任务，识别出矩形不代表音高和节拍已正确。

- 对所有谱页建立物理页号、系统索引、页面宽高、实际矩形。
- 坐标统一使用 PDF 点和左上角原点：`rect_pt=[x,y,width,height]`。从底部原点的 PDF 文本坐标转换时，要按实际页面高度换算。
- 编排变化时去重同一系统；双小节线算一个边界，不按两根竖线增加两小节。
- 华彩、无小节线片段可使用共用区域；不要等宽切出原图不存在的边界。
- 只有核对对应关系后，才将 `measure_id` 关联到具体矩形。没有证据时可先用系统候选，或保留空 `measures` 并手动翻页。

`measure-map.json` 至少需要 `pdf_path`、`pdf_sha256`、`page_count` 和 `measures` 数组。普通小节条目可参考现有数据：

```json
{
  "measure_id":"midi-m0001",
  "page_number":1,
  "system_index":0,
  "page_width_pt":672,
  "page_height_pt":864,
  "rect_pt":[100,120,80,500],
  "printed_measure_number":null,
  "resolution":"bar",
  "review_status":"unreviewed"
}
```

这里只是字段格式，坐标、尺寸、ID 都必须换成本次实际观测，不能复制为真值。多乐章另保存 `movements` 中的 `movement`、标题、`first_pdf_page`、`last_pdf_page` 和 `first_sequence_index`。

### 第五步：识图计数与位置锚点

马四已有可复现入口：

```powershell
python scripts/map_mahler4_pdf.py
python scripts/number_mahler4_pdf.py
```

第二步读取第一步的指纹绑定缓存，补充多个谱表共同支持的边界，生成独立 `score-measures.json`。保留 `region_id`、几何指纹、源 PDF／MIDI 指纹、时间匹配来源、候选号码及证据，不把自动计数填成 `printed_measure_number`。

排练号可作为独立地标，但先核对它位于哪个真实小节，再作为编号锚点。不能遇到排练号就重置小节计数。弱起、跨行续段、多小节休止和反复路径分别处理：纸面号码与演出中第几次经过同一小节，不是同一字段。

前端在保留原 PDF 的情况下叠加可点击号码，号码绑定实际框。为文字避让而移动标签时，只移动标签，不移动小节矩形。缩放和翻页后仍使用同一套 PDF 坐标。

### 第六步：PDF-only 的 OMR 分支

没有可靠 MIDI／XML 时，先处理一到两页：

```powershell
python -m backend.score_processing "resource/my-work/score.pdf" --pages "1-2" --output "output/omr/my-work" --dpi 450 --audiveris "Audiveris实际路径"
```

可增加 `--musescore` 指定本机程序生成 PNG。MusicXML 能打开、外部程序返回 0、或重排页数增加，都不能证明识谱正确；必须检查输出确有内容、part-list 对应、拍号、谱号、节奏、音高、震音、移调与声部身份。

逐页接口不会自动拼接整部作品。按乐章原生连续识别可参考：

```powershell
python -m backend.score_processing.movements --manifest "works/my-work/movements.json" --movement 1 --through-page 2 --output "output/omr/my-work-by-movement" --dpi 450
```

先建立与 `works/mahler-7/movements.json` 同结构、且边界已核对的清单；`--through-page` 是目标物理页。使用 `--status` 查看检查点。不要让两个进程同时写同一乐章目录；失败时保留原 `.omr` 和日志，从检查点恢复，不清空全部工程。

目前马七连续识别仍有失败与缺页，不是完成全曲转录的示范。前四页声部身份校正样本与后续原始候选分别保存；仅核对声部身份不代表音符、拍号或节奏也正确。详见 `docs/guides/pdf-to-musicxml.md` 和马七报告。

### 第七步：绑定赏析与文献

为新曲目建立 `metadata/recording.json`：包含 `work`、`recording`、`analysis_document`，并绑定录音和 PDF 指纹。根据本作品原稿格式添加解析／关联逻辑，不照搬其他作品的章节序号。

已有入口 `python scripts/analysis_data.py --track my-work` 可导出已配置曲目的分析 JSON，但前提是该作品的元数据与解析方式已经适配。马四使用 `import_mahler4_analysis.py` 导入四章正文与 `score-guide.json` 中的 38 段导聆。

按音乐内容拆短段，可跨数页，也可在同页分段。马四的 `score_start`／`score_end` 使用 `[物理页,0起始系统索引,页内横坐标点数]`，范围前闭后开；页首的横坐标 0 表示该系统开始。不要为拆短正文而冒充已查明严格曲式边界。

### 第八步：联调并人工复核

确认曲库注册后打开 `/?track=my-work`，检查播放／暂停、跳转／变速、首尾与乐章切换、自动翻页、点击矩形／编号、同页多段赏析以及无视频的兼容行为。

三种校正分开处理：

| 文件／功能 | 修正什么 | 生效方式 |
|---|---|---|
| `review-anchors.json` | MIDI 参考时间到录音时间的锚点 | 独立输出重算，检查后切换 |
| `score-region-anchors.json` | 某个 PDF 区域的录音起止时间 | 播放器立即采用人工区间 |
| `score-measure-corrections.json` | 小节起始号与本框计数 | 即时更新后续候选号码，至下一人工锚点 |

例如重算到新文件：

```powershell
python scripts/align_recording.py --audio "resource/my-work/performance.mp3" --midi "resource/my-work/reference.mid" --anchors "works/my-work/review-anchors.json" --output "works/my-work/alignment.corrected.json"
```

保留原文件和校正历史。确认过的结果、分析正文、文献与人工校正不能被首次初始化的空占位数据覆盖。

## 6. 验证与失败处理

最小播放依赖下可运行部分测试；完整处理测试还需要计算依赖。可用：

```powershell
python -m unittest discover -s tests -v
node --test --test-isolation=none tests/test_video_playback.mjs tests/test_score_follow.mjs tests/test_analysis_playback.mjs tests/test_movements.mjs tests/test_measure_numbers.mjs
```

Node 只用于可选前端测试。若当前 Node 不支持 `--test-isolation=none`，可在允许子进程的环境按该版本支持的方式运行测试；这不影响播放器安装。

`scripts/check_mahler4_app.mjs` 需要本地 8766 服务及马四材料，用内存 DOM 调用实际模块。它不是真实浏览器实播；编号保存响应使用模拟，真实保存由隔离的 Python HTTP 夹具测试。不能把两者混为用户实播验收。

| 现象 | 处理方式 |
|---|---|
| 视频缺失／文件指纹不匹配 | 提供清单对应原文件，或新建目录重新生成；不改 hash 绕过 |
| 其他机器缺少 `.tools` 缓存 | 预计算播放不需要它；要重算时安装处理依赖并重新建立 |
| 新 PDF 页码或框偏移 | 核对物理页、页面尺寸、旋转、PDF 版本与坐标原点 |
| MIDI 分节与原谱不同 | 保留为参考段，单独建立原谱号码，使用实际锚点关联 |
| 乐章停顿／华彩／片头附近漂移 | 局部试听与人工时间锚点，不强行按速度均分 |
| OMR 返回 0 但无有效 XML | 按失败处理；检查结构、实际 sheet 数据与日志 |
| OMR 缺少拍号／错谱号／重复 part | 与原谱逐声部校对，修复副本后重新导出；不靠默认值伪装正确 |
| 新谱面匹配后旧编号拒绝载入 | 旧时间来源已失效，重新建立编号索引与关联，保留旧人工校正供审查 |
| 推送检查报视频或大文件 | 从待提交索引排除，保留本机文件；不要 `git add -f` 绕过 |

测试通过只说明该检查覆盖的行为成立。报告分别记录：结构验证、图像几何、特征对照、人工试听、真实浏览器验证和音乐内容校对。没有做的环节明确写未完成，不输出虚构百分比。

## 7. 仓库发布规则

本轮用户明确要求：**所有马勒视频都不推送 GitHub。** 当前忽略规则进一步覆盖常见视频容器及大小写扩展名。视频可留在本机 `resource/`，路径、hash、字节数和处理报告可以提交。

可提交代码、依赖清单、文稿、元数据、预计算 JSON、必要小样和获授权的非视频材料。`.tools/`、`.venv/`、`tmp/`、环境私密配置和约 700 MB 的 `output/omr/mahler7-by-movement/` 累计快照留在本机；后者不是删除任务，不能为了推送清理掉用户的续跑工程。

发布前先看 `git status`，明确加入相关文件，再运行：

```powershell
python scripts/check_publish.py
git diff --cached --check
git diff --cached --stat
```

检查器读取 Git 索引中的实际 blob，拒绝视频扩展名、若干改名后仍可识别的视频容器头和单个达到 100 MiB 的文件。它不能代替查看提交范围，也不自动暂存或推送。已有被跟踪的视频不会因 `.gitignore` 自动消失，必须检查索引。

只在用户授权的范围提交和推送。不覆盖无关改动、不自动强推、不把本机绝对工具路径变成其他用户必须复制的设置。不要将生成任务尚在运行的累计快照当作稳定发布结果。

## 8. 后续代理的实现约定

- 优先读取现有数据模式与适配器，保留原有两首音频曲目的兼容性；新作品放独立目录。
- 不把音符识别、谱面几何、编号、录音时间和赏析解释合并成一个“置信度”。它们分别需要证据。
- 保留真实素材指纹、稳定区域 ID、算法来源、人工修改及旧值。`stable_candidate` 不是 `verified`。
- 复杂扫描先做小样；只有结构与视觉检查通过后才扩大处理。原版、修复副本、失败输出和最终候选分别记录。
- 本机播放与预计算结果仍应只需最小 Python 依赖。OMR、FFmpeg、Node 测试等组件保持可选。
- 变更后运行与改动有关的测试；报告已测范围与实际限制。未执行真实浏览器／试听时，不写成已经验收。
- 若用户报告 PDF 标记辅助定位有效，可记录为用户反馈，但不能扩大为全曲音符、编号或时间已逐项确认。

工作进展总览见 `docs/WORK_SUMMARY.md`，各作品的详细实测以 `reports/` 与 `works/*/reports/` 为准。

## 9. 音乐研究优先规则（2026-10-26用户调整）

- 暂停以消除全部MIDI—PDF未匹配为主要目标；旧诊断与冻结记录保留，不把清零作为研究门槛。
- 和声及精细对位先使用少量直接读谱录入的窗口，逐音、节奏、移调与声部证据明确后再作推导。代理读谱与人工签核分开，不代填人类审核。
- 配器直接核查乐器活动、音域、奏法、加倍与织体变化，不要求全曲音符级MIDI覆盖；精确音域未录入时说明范围层级。
- 曲式建立材料／主题、乐句、段落和全曲的可修订关系；用动机比较、终止、配器与调性证据修订，不预设固定奏鸣曲式。
- 未匹配记录按打击乐、震音、八度、移调、节奏、踏板、真实错误分类；证据不足时保留未分类，不把诊断假设当作已证实错误。
- 已有可用MusicXML时，以`analysis/musicxml/`为主要符号来源，`analysis/score-studies/`保留直接读谱的校核与理论推导。旧自动引擎的A/B或C/D开关只约束其自动实验，不能阻塞独立配器与结构研究。播放器默认展示谱面研究与XML证据，旧自动候选为可选辅助。

## 10. 拉威尔MusicXML主要数据路线（2026-10-26）

- 入口为`python -m backend.musicxml_analysis.pipeline --source "resource/ravel left hand piano concerto/maurice-ravel-piano-concerto-for-the-left-hand.mxl" --output "analysis/musicxml/新的目录"`。处理环境可安装`requirements-analysis.txt`；预计算播放不导入music21。
- 该入口目前适配此拉威尔版次。先检查源指纹、PDF布局与关键位置；失败保存接入审计，不激活结果。不能把MuseScore转录自动标为校勘版或人工逐音核验。
- MusicXML分部、谱表、声部、小节与原音符序号分别保存。应用显式移调一次；区分XML编码音、八度线下的印刷记谱音及实音。乐器变化按每音符的乐器引用与当前移调记录，不只看最初分部标题。
- 公共时轴使用原XML的小节序列及局部有理数时值，保留整小节休止的解析差异和华彩实际长度。不得将music21各分部独立累计的偏移直接合并，也不由此生成假录音秒数。
- 无音头或不打印的事件隔离保留；装饰音不虚构实播时长。踏板、震音、延音线与原奏法保留中间依据，记谱时值不代替声学余响。
- 和声保存窗口全体音符ID、实际低音、音集、转位及条件性级数；同一小节的分解音集合不冒充同时和弦。调性轮廓相关系数不称为正确概率。
- XML→PDF关系单独保存在快照`pdf-map.json`，目前为小节／共享系统包含关系，不是逐音头框。首华彩第11页的单谱表区域独立补出；旧同步与旧PDF映射不因此覆盖。
- 当前指针为`analysis/musicxml/current.json`。JSON中间证据、输入及代码有指纹；可用`scripts/export_musicxml_research.py`导出CSV台账。人工签核、全曲和弦外音、完整和声归约与最终曲式裁定仍另行进行。

## 11. 并列解释与当前激活（2026-10-26验收）

- 用户允许有依据的多个读法并列；和声层、低音层、局部调性及曲式模型不必强制合为唯一答案。每个归约保存取用音符及另外列出的音符。
- `python -m backend.musicxml_analysis.completion --output "analysis/musicxml/新的解释目录"`生成解释、时点激活和录音投影，指针为`interpretation-current.json`。本地处理另需可选mido；播放仍不导入music21或mido。
- 当前乐器列表使用XML实际记谱时值区间，区分同一小节内先后入口；不将整小节活动并集称为某时点的活跃乐器，也不把余响自动延长为记谱音。
- 录音继续采用原DTW时间映射；MIDI速度与小节结构只桥接已有录音时钟到XML，不成为音乐分析的音符匹配门槛。最后未覆盖的0.4个XML四分音符不外推。
- XML→PDF区域在运行时适配原播放器，不覆盖旧同步和旧映射。首华彩缺失的单谱表区域由独立几何补充。
- 前端模块必须检查实际HTTP导入依赖图；内存DOM通过不能代替浏览器资源加载和实播检查。真实浏览器确认长文章的非零滚动位置、播放推进、多个活跃乐器及跨曲清理。
- 代理验收、关键谱例核查、人类签核与专家逐音审定分别记录。当前研究版通过代理功能验收，不伪造人类或专家签名。详见`reports/ravel-acceptance-20261026.md`。

## 12. 拉威尔独立视频版（2026-10-26）

- `ravel-left-hand-video` 使用艾马尔视频自身音轨独立计算DTW，数据位于 `works/ravel-left-hand-video/`；原齐默尔曼音频版不覆盖。视频继续留在本机，不提交Git。
- 曲库的 `score_source` 显式引用原曲目。共享前核对作品、PDF和参考MIDI身份；复用研究原稿、XML快照与谱例，演出阵容及录音投影独立。不要把共享谱面误当成两场演出同源。
- `musicxml-recording-projection.json` 绑定本视频、独立alignment及共享XML快照；上游谱面或本地时间映射变化须重建投影，不能改指纹绕过。
- 已从视频的27.5–1162.5秒分析窗口重算，并按27.5秒偏移回原视频时钟。此边界为代理画面／频谱估计，尚无人类试听签核。完整文件首尾DTW草稿单独保留，不激活；`score_time_coverage` 之外不显示虚构的和声、乐器与播放线。
- `scripts/build_ravel_video.py` 封装已生成的原始对齐；拒绝覆盖已存在的视频版。`scripts/check_ravel_video_app.mjs` 使用实际HTTP及模拟DOM／媒体，不是真实视频解码实播。本轮浏览器控制被Work设置禁用，范围见 `reports/ravel-video-20261026.md`。

## 13. 统一四维技术HUD（2026-10-26）

- PDF上方仅有和声、配器与织体、对位、曲式四个入口。`musicxml-live.mjs` 为单一数据提供者，不生成第二套面板；`score-analysis-model.mjs` 组合事实、局部分析及结构范围，各维度按稳定签名更新。
- `#hud-detail` 与默认折叠的 `#musicxml-reader` 位于右侧 `#panel-evidence`，源音符ID及完整小节数据按需读取，不自动seek。播放、详情开关和证据查阅不得替换 `#essay-body`。
- `analysis/hud/current.json` 指向小型案例／罗马数字兼容性核查层，绑定原XML和解释快照。它不重建和声引擎、不覆盖原快照；无可靠跨时范围时显示背景待分析。
- 罗马数字重建与所选层音级不一致时暂缓展示为有效读法，原字段仍在冻结证据中；兼容性检查不是和声功能或准确率认证。
- 四组示范用源音符、时值和进入事件核对；原同步、几何、研究正文、校正与旧引擎历史保持原样。测试及本轮浏览器不可用范围见 `reports/musicxml-hud-integration-20261026.md`，不得沿用历史截图冒充新版布局验收。
- 用户随后认可四维组织形式，但要求增加显示空间。当前HUD默认约240–360 CSS像素，可拖动调高；全部活跃分部、和弦／并列层及曲式模型完整换行，不再按两行或前四个分部截断。四个标题保留可见，卡片各自滚动；不要机械恢复任务书早期100–160像素的密度目标。

## 14. 项目组织与日常制作（2026-10-26）

- 先看根目录`项目导航.md`与`docs/README.md`。视频制作和分析撰写的当前流程分别在`docs/workflows/video-production.md`、`docs/workflows/analysis-writing.md`；历史任务书在`docs/design/`或`docs/archive/`，不据其文字假定功能已完成。
- 视频脚本集中在`scripts/video_export/`。`scripts/export_video.py`保留兼容入口，其余引用使用新路径。代码仍是本地Python与原生JS，不增加框架。
- `config/video-export.json`统一配置本机导出位置及`editor_projects`中的项目／文稿对。根目录只保留`编辑视频字幕.bat`，启动时选择鹅妈妈、拉威尔完整版或样片；Python统一入口为`scripts/video_export/edit_video_captions.py`，支持`--project`并兼容`--full`。不再生成旧的完整版、鹅妈妈或字号专用入口，也不要解析批处理文本猜路径。
- 样片草稿、字号偏好和最近视频指针移到`local/video-export/`，不上传GitHub。当前完整版仍使用`output/video-export/ravel-full-001/captions-editable.json`，未搬动用户正在编辑的JSON或导出包。
- 拉威尔后两个模块名为“声部关系与复调”“曲式与主题发展”。JSON直接存新名称，读取兼容旧键；不要保存后退回旧名。和声、配器、四宫格及其他作品保持独立。
- 文件整理不能重新安排字幕时间或重算分析。原始媒体、激活与冻结快照、人工校正、历史OMR及未提交工作不因目录整理删除。根目录拉威尔同步数据仍保留原位置。
- 发布保留现有媒体排除规则；`local/`与`output/video-export/`均为本机资料。按第7节检查实际Git索引后，才在用户授权的范围提交和推送。
