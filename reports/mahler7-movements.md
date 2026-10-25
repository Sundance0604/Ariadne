# 马勒第七：按乐章转录

日期：2026-10-25。范围依据用户提供的 257 页 PDF 谱面逐个确认，不使用书签文件名猜测乐章边界。源文件 SHA-256 和准确范围保存在 `works/mahler-7/movements.json`。

| 乐章 | 源谱标题/速度 | PDF 物理页 | 页数 |
| --- | --- | --- | ---: |
| I | Langsam (Adagio) | 1–80 | 80 |
| II | II: Serenade / Allegro moderato | 81–118 | 38 |
| III | III / Schattenhaft | 119–154 | 36 |
| IV | IV: Serenade / Andante amoroso | 155–183 | 29 |
| V | Rondo - Finale / Allegro ordinario | 184–257 | 74 |

五个范围首尾相接，共 257 页；物理页和谱面底部页码在检查的边界处吻合。源谱上方的大数字多为排练号，不能当作页码或乐章小节编号。[边界页视觉证据](../output/omr/mahler7-movements/boundaries.png) 包含每个乐章的首页与末页。

## 方法与进度

### 继续处理后的进展

第一乐章已成功累计导出物理第 1–20 页，80 页任务仍在继续。运行中请使用 `-Status` 查看最新检查点；本记录中的数字是本次写入时的快照，不代表第一乐章已完成。

已定位并修复反复触发崩溃的一类根因：部分谱表的系统起始竖线被当作第一小节的结束线，形成一个在谱表左端之前结束的空小节，进而破坏各声部的小节对应。新增流程先运行至 MEASURES，再对这种严格限定的情况修复工程副本，之后继续 CHORDS 至 PAGE。第 3 页的 5 个伪小节修正后，前四页首次完整导出；第 9 页的同类问题也在后续批次中自动处理。修复不删除识别的音符头、休止符或符干，原工程与每次修复记录均保留。

另外，已依据原谱左侧乐器名及印刷声部编号，逐页核对前四页的谱表身份，建立 `works/mahler-7/part-mapping-opening.json`。将自动输出的 64 个重复逻辑 part 整理为 21 个固定谱表身份，并保留全部 2,285 个带音高 note 元素。分开的大提琴谱表继续分开保留；打击乐共用谱表不等于已经正确编码了演奏乐器的切换。此映射只覆盖前四页，没有推广到未复核的其他页面。

可检查的前四页结果：

- [谱表对应已核对的 MusicXML](../output/omr/mahler7-opening-corrected/mahler7-opening.musicxml)
- [压缩 MXL](../output/omr/mahler7-opening-corrected/mahler7-opening.mxl)
- [原始连续识别工程](../output/omr/mahler7-repair-probe/test-1.omr)
- [逐页映射和音符保留检查](../output/omr/mahler7-opening-corrected/mahler7-opening.review.json)

该结果为每声部 18 个候选小节，拍号、节奏、音高和移调仍未逐项校正。谱表身份的修正不代表这些音乐内容正确，仍保留 `musical_accuracy_verified=false`。MuseScore 已实际打开最新 XML 并重新排版为 8 页；原谱 4 页与重排页数不同属于排版变化。

原生 `.omr` 的外部声部映射在再次由 Audiveris 导出时曾得到 0 part 的空文件，虽退出码为 0，已被独立 XML 校验拦截。失败输出和日志保存在 `mahler7-opening-corrected/failed-native/`，不作为交付文件。最终映射直接基于实际导出的 MusicXML、工程中的源页小节跨度和经核对的声部清单，边界处完整继承源 attributes，并核对全部发声音符内容保持不变。

新增修复、声部映射、续跑优先级与流式校验测试后，相关自动测试共 32 项通过，日志仍为 `reports/mahler7-movement-tests.log`。流式校验与原方式对真实 20 页导出的结果完全一致：330 个原始候选 part、9,141 个带音高 note 元素。前四页以后的累计 MusicXML 保持原始候选声部，仍可能有大量重复 part；这些结果与已核对的前四页示例明确区分。

为避免后续大文件一次性读入内存，当前程序按 part 流式解析超过 16 MiB 的导出，并流式解包 MXL。已在保留 20 页检查点后重启转换任务，让后续批次使用新校验方式；不会重跑已完成的音符识别。当前第一乐章任务继续向第 24 页及后续批次推进。

每个乐章先由 PDFium 流式生成 450 DPI 灰度多页 TIFF，再使用一个原生 Audiveris 多页工程。每批累计导出该乐章已完成的页面，保留之前批次；后续调用复用 `.omr` 中的识别步骤。跨页声部连接交给引擎处理，不将独立单页 MusicXML 的 part ID 按位置硬拼。

首次原生多页测试选择物理 1–2 页，默认 PDF 读取分辨率为 300 DPI。第 1 页到达 PAGE，第 2 页在 CHORDS 阶段触发 `NullPointerException: measure is null`，未生成有效的两页连续 MusicXML。工程与完整失败日志位于 `output/omr/mahler7-movements/movement-01/`。该次失败不能算第一乐章已转录。

随后以 `org.audiveris.omr.image.ImageLoading.pdfResolution=450` 新建独立多页测试，第二页仍然崩溃，结果保存在 `output/omr/mahler7-movements/native450-probe/`。还实际验证了从这一失败 `.omr` 恢复时能记录失败和保存进度，不把尚未完成的第二页计为成功。

第三次改用 PDFium 450 DPI 灰度多页 TIFF，**第 1–2 页成功到达 PAGE，导出为一份连续 MXL，并由 MuseScore 成功重新排版为 4 个 PNG**。样本与完整日志在 `output/omr/mahler7-movements/raster450-probe/`：

- [两页 MusicXML 样本](../output/omr/mahler7-movements/raster450-probe/mahler7-first-two.musicxml)
- [多页 Audiveris 工程](../output/omr/mahler7-movements/raster450-probe/mahler7-first-two.omr)
- [重新排版四页总览](../output/omr/mahler7-movements/raster450-probe/review-contact.png)
- [结构与质量检查](../output/omr/mahler7-movements/raster450-probe/review.json)

这个两页样本有 8 个候选小节、1240 个带音高 note 元素、214 个 rest 元素；仍全部缺失拍号。原两页分别有 17、19 条谱表，引擎导出 35 个逻辑 part，并在未匹配的页面填入休止符。这说明**跨页乐器身份对应尚未解决**，不能把“一份 XML”当作正确连接了配器。尚未做逐音符校对；没有伪造准确率或人工确认状态。

已启动第一乐章完整 80 页的分批任务，第一乐章的标准化 TIFF 已生成。最新运行进度、已完成页、每次导出覆盖范围和片段数量以 `output/omr/mahler7-by-movement/movement-01/movement-report.json` 和 `-Status` 查询结果为准。每次批次导出都是待复核候选，记录异常声部数量。第二至第五乐章尚未开始。

## 运行

```powershell
./scripts/transcribe_mahler.ps1 -Movement 1
```

第一乐章默认范围 1–80，默认每 4 页建立一次累计导出快照，450 DPI。只测试开头两页时加 `-ThroughPage 2`；之后去掉该参数即可继续。其他乐章使用 `-Movement 2` 至 `-Movement 5`。每个乐章独立输出、独立失败重试。若已有同乐章进程运行，命令会拒绝第二次并发写入，可用 `-Status` 只读查看。

查看第一乐章进度：

```powershell
./scripts/transcribe_mahler.ps1 -Movement 1 -Status
```

`partial_needs_review` 仅表示乐章的一部分完成；`converted_needs_review` 需要所有乐章页都已保存并导出，仍不代表音符准确。若引擎把乐章拆成多个 MusicXML，记录为 `fragmented_needs_review`。任何缺页、无效页或缺少真实 sheet 数据的工程都不能冒充完整转录。

## 验证

相关 19 项自动测试通过，包括原有 11 项转换测试及新增 8 项乐章测试。新增测试涵盖乐章范围完整覆盖、工程声明完成却缺少 sheet 数据、无效页、累计导出与续跑、引擎返回 0 却漏页、分片结果、输入指纹不匹配、多页 TIFF 的帧数/灰度/缓存完整性以及乐章内页码映射。测试日志为 `reports/mahler7-movement-tests.log`；这些测试不替代真实谱面的音乐校对。

已知 OMR 音乐错误和单页样本见 [先前实测报告](mahler7-omr.md)。按乐章组织可以隔离、续跑和校正，但不会自动解决拍号、节奏、震音、移调或乐器名称错误。

原生命令参数依据 [Audiveris CLI](https://audiveris.github.io/audiveris/_pages/guides/advanced/cli/) 中的 `-sheets`、`-swap`、`-save` 和 `-export`。PDF 分辨率常量还核对了本机 5.11.0 的 `ImageLoading$Constants`，没有假设更高 DPI 能保证正确。
