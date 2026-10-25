# PDF → MusicXML

这是独立的离线预处理模块，不依赖录音、MIDI 或播放器。引擎为本机 Audiveris，PDF 渲染使用 PDFium。当前支持逐页转换，不拼接多页的声部、延音线或原谱小节编号。

## 依赖

在项目根目录使用 Python 3.11+：

```powershell
python -m pip install -r requirements-omr.txt
```

另行准备 [Audiveris 官方发布版](https://github.com/Audiveris/audiveris/releases)。当前机器已在 `.tools/audiveris-portable/Audiveris/Audiveris.exe` 解包 5.11.0，并有自带 Java。其他机器可用 `--audiveris` 或环境变量 `AUDIVERIS_PATH` 指定启动程序；自动发现顺序为显式参数、环境变量、项目便携版、PATH。不自动下载安装或编译。

Audiveris 的工作配置位于 `.tools/audiveris-data`。OCR 需要该配置目录中的 `AudiverisLtd/audiveris/config/tessdata/eng.traineddata`；当前实测模型来自 [Tesseract 官方 tessdata](https://github.com/tesseract-ocr/tessdata/blob/main/eng.traineddata)，并非缺少 legacy 引擎数据的 tessdata_fast。模型缺失或语言配置错误会记录在日志中，不能以导出文件存在认定文字识别正确。

可选安装 MuseScore，通过 `--musescore` 或 PowerShell 的 `-MuseScore` 指定实际程序，生成可对照的 PNG。MusicXML 的成功打开和重新排版不代表识谱正确。

## 使用

推荐先处理少量物理页。物理页从 1 开始，和谱面印刷页码可能不同。PowerShell 封装默认使用项目 `.venv`，无该环境时使用 PATH 中的 Python：

```powershell
./scripts/convert_score.ps1 -Pages '1' -MuseScore 'D:\software\MuseScorePortable\App\MuseScore\bin\MuseScore4.exe'
```

通用命令：

```powershell
./.venv/Scripts/python.exe -m backend.score_processing '输入.pdf' --pages '1,3-5' --output 'output/omr/example' --dpi 300 --retries 1 --timeout 900
```

Python CLI 不提供 `--pages` 时会处理全部页。PowerShell 封装为便于小样验证，默认只处理第 1 页。`--expected-staves` 和 `--expected-measures` 可用原谱已知数字进行对照，只生成风险提示，不修改识谱结果；多页时此数字应用于每个页面。

```python
from backend.score_processing import convert_pdf

report = convert_pdf('input.pdf', 'output/omr/example', pages='1-2',
                     dpi=300, retries=1, timeout=900)
```

输入 PDF 保持原样。每页先渲染为 PNG，再按官方 CLI 的 `-batch -transcribe -export -save` 运行。选择位图输入是为了固定 DPI，并隔离各页的失败和导出命名。程序不伪造音符，也不根据录音补写 MusicXML。

## 输出与状态

输出目录中按输入 SHA-256、引擎版本/程序和 DPI 建立任务目录。每页有 `page-NNNN/result.json`，每次实跑有新的 `attempt-NNN`，其中保存原页 PNG、`.omr`、`.mxl`、解包的 `.musicxml`、完整控制台日志、可选的重排 PNG。任务根目录中的 `report.json` 汇总本次请求的页面和校验数据。已有的其他页面仍可从各自目录读取。

- `converted_needs_review`：XML 可解析，声部 ID 一致，各声部有小节，存在音符数据；始终保留 `musical_accuracy_verified=false`。
- `failed`：外部程序出错/超时、缺失工程/导出文件，或结构校验失败。失败目录与 `failure.json` 保留。
- `render.status=rendered_needs_review`：MuseScore 成功输出可解码 PNG；还需对照原谱。
- `render.status=failed`：音乐转换已完成，但复排失败。CLI 返回非零，下一次调用不会直接复用这个页面。

自动检查包括声部/谱表/每声部小节数、带音高及无固定音高音符和休止符数量、拍号缺失、声部时值范围与拍号的差异，支持 chord、backup、forward 和继承的 divisions。检查不是完整 MusicXML XSD 验证；节奏提示可能包含合法的局部声部情况，不能当作准确率。`engine_diagnostics` 保留引擎警告，完整信息以日志为准。

## 缓存与恢复

缓存命中前校验输出 SHA-256 并重新解析 MusicXML。文件丢失或被改动时新建尝试；原文件保留。`--retries N` 是每页失败后的额外尝试次数。一页失败后仍处理本次选中的后续页，整体返回失败状态。`--force` / `-Force` 可要求新跑，同时保留旧结果。

每次导出使用独立目录，不会把上一次失败留下的 MXL 当成新结果。任务锁防止同一输入参数并发写入。如果进程被强制关闭留下 `processing.lock`，先确认对应进程已停止，再只删除该锁后重跑。更改 OCR 模型、引擎安装中的库或手工配置后使用 `--force`；当前缓存键不追踪这些文件。

Python API 的文件缺失、无效页码等请求错误会抛出异常；逐页执行错误写入返回报告。CLI 转换失败或复排失败返回 1，结构转换成功且复排未失败返回 0。退出码 0 不能作为音乐质量验收。

## 验证

```powershell
./.venv/Scripts/python.exe -m unittest discover -s tests -p test_score_processing.py -v
```

这些测试使用模拟引擎检查校验、缓存损坏、部分导出失败、重试与渲染无输出等行为；真实马勒样本的引擎日志、结果与视觉对照单独保存在实测报告中。

## 按乐章连续转录

`works/mahler-7/movements.json` 保存经谱面确认的物理页范围：I 1–80、II 81–118、III 119–154、IV 155–183、V 184–257。清单附带 PDF 指纹，防止误用其他版本。标题采用这份谱面的写法。

```powershell
./scripts/transcribe_mahler.ps1 -Movement 1
./scripts/transcribe_mahler.ps1 -Movement 1 -Status
```

首条命令转录第一乐章，第二条只读取进度。`-Movement` 可选 1–5。可用 `-ThroughPage 2` 先处理乐章开头至指定物理页，再去掉该参数继续。`-BatchSize` 默认为 4，每次累计导出到本批最后一页，不会把四页误称为整个乐章。

此模式先由 PDFium 将一个乐章以 450 DPI 转为灰度多页 TIFF，再使用 Audiveris 的原生多页 book 连续识别。统一图像输入已在前两页实测绕过直接 PDF 输入的第二页 CHORDS 崩溃。TIFF 逐页写入，不同时持有整部乐章的图像。用 `-Dpi` 可调整分辨率。

第一批读取该乐章的 TIFF，后续批复制上一批的 `.omr`，复用已经完成的识别步骤，再处理新页；启用 `-swap` 降低内存占用。导出和工程按批次留存。默认输出在 `output/omr/mahler7-by-movement/movement-NN/`，每个乐章有独立目录和进程锁，可中断后重跑同一命令恢复。标准化图像有独立输入指纹校验缓存。

进度依据工程中已完成 `PAGE` 步骤且实际保存了 sheet 数据的页面；页面缺失或被引擎标为无效都不能计为完成。`movement-report.json` 保存进度、XML 数据、导出源页范围和日志位置。`--status` 会在运行期间尝试读取最新工程检查点；ZIP 正在更新时暂用上一份报告。

所有乐章结果仍标为待人工复核。`partial_needs_review` 表示只覆盖了乐章的一部分；只有所有目标页面完成才可能得到 `converted_needs_review`。如果引擎将同一乐章导出成多份 MusicXML，记录片段数量，完整乐章状态使用 `fragmented_needs_review`，不擅自合并不确定的乐器身份。跨页配器对应、移调、延音线与音乐准确性仍需校对。

TIFF 内部页码从 1 开始，报告自动映射回源 PDF 的物理页。例如第二乐章 TIFF 第 1 页对应 PDF 第 81 页。进度显示的始终是源 PDF 页码。

当前每批分为两段：先到 MEASURES 保存工程，检查是否存在“第一空小节的结束竖线完全位于该谱表左端之前”的异常，再继续后续识别。只有同时满足空小节、其余声部小节数一致、尚未进入和弦/节奏处理等严格条件才自动修复；真实弱起、包含音符的小节以及已处理的节奏结构不会因此被删除。`unrepaired/` 保留修复前副本，`repairs/` 保存修复副本和审计 JSON。

大于 16 MiB 的 MusicXML 使用按声部流式校验；MXL 也流式解包，避免把整个乐章的 XML 和对象树同时保存在内存中。结构校验允许单独的全休止声部，要求全曲存在实际发声音符。读取状态时还会返回最近一次成功导出的覆盖页和文件路径，便于运行中检查已完成的批次。

`part_mapping.map_musicxml` 支持使用与 PDF 指纹绑定的、已按原谱核对的谱表清单整理声部。它要求每个导出源页都有对应清单、谱表结构一致、工程的小节跨度与 XML 一致，并核对全部发声音符内容保持不变。没有核对的页会被拒绝，不会按行号擅自套用开头的乐器配置。目前已核对的清单只覆盖马勒第七前四页，示例见实测报告。

低层 CLI 支持 `--resume-book` 显式导入属于同一个标准化 TIFF 的原生多页工程。它与之前以独立 PNG 输入生成的单页工程不能直接互换。`--native-pdf` 保留直接 PDF 输入供诊断，更改该选项、DPI 或输入后应使用新的输出目录，避免混用缓存。
