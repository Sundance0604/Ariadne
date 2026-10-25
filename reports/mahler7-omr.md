# 马勒第七：PDF → MusicXML 实测

日期：2026-10-25。结论：**已跑通第 1 页的自动转换、MusicXML 解析、MuseScore 重新排版和缓存复用；音乐准确性未通过验收。没有转换其余 256 页。**

## 输入和工具

- 输入为 `resource/mahler No.7/IMSLP927114-PMLP30475-Mahler,_G._-_7._Symphony_in_E_minor_---_Full_Score_(Dover_Reprint).pdf`，257 页。本次使用物理第 1 页，印刷页码也是 1。
- 原 PDF 保持原样。视频未参与识谱，也未处理录音同步。
- Audiveris 5.11.0，commit `9e1e55cd2746037d059345881c53e6a6754bffbd`，自带 OpenJDK 25.0.3、Tesseract 5.5.2。本机已有项目内便携版，实测调用 `-version` 核实，无需重新安装或编译。
- 先以 300 DPI 识谱，再以 450 DPI 使用新接口重跑。两次均实际生成 `.omr`、`.mxl`，并解析为 `.musicxml`。
- 本机便携 MuseScore Studio 成功打开两次 MXL 并导出 PNG。450 DPI 结果重排成两页，两个 PNG 均已检查。

## 实测数据

| 项目 | 原谱目视参考 | 300 DPI 初试 | 450 DPI 接口实测 |
| --- | --- | ---: | ---: |
| 谱表 | 17 条 | 17 | 17 |
| MusicXML part | 原谱有合并配器和分谱表，不等于乐器人数 | 17 | 17 |
| 小节 | 同一系统 4 小节 | 每 part 4 | 每 part 4 |
| 拍号 | 4/4 | 全部漏识 | 全部漏识 |
| 带音高 note 元素 | 未逐音符人工计数 | 684 | 656 |
| rest 元素 | 未逐休止符人工计数 | 42 | 37 |
| note 元素总数（包含休止符） | 未建立人工真值 | 726 | 693 |

上述 656 是 XML 元素数量，**不是 656 个正确音符**。更高 DPI 没有消除识别错误，音符数量的变化也不能证明准确率提高。最终保留 450 DPI 为接口复现样本，并保留初试供比较，不声称其更准确。

MusicXML 容器、XML 解析、part ID 与 part-list 一致性、小节/音符数据检查通过。450 DPI 的自动报告有 17 条 `missing_time_signature`，每个 part 一条；未在拍号缺失时擅自按 4/4 计算节奏正确率。原谱的 4/4 目视结论没有被自动补写进输出。

## 交付与对照

450 DPI 的任务目录为：

`output/omr/mahler7/IMSLP927114-PMLP30475-Mahler,_G._-_7._Symphony_i-d8be024bc1b4c89a/`

其 `page-0001/attempt-001/` 包含：

- [MusicXML 明文](../output/omr/mahler7/IMSLP927114-PMLP30475-Mahler,_G._-_7._Symphony_i-d8be024bc1b4c89a/page-0001/attempt-001/page-0001.musicxml)
- [压缩 MusicXML](../output/omr/mahler7/IMSLP927114-PMLP30475-Mahler,_G._-_7._Symphony_i-d8be024bc1b4c89a/page-0001/attempt-001/page-0001.mxl)
- [Audiveris 工程](../output/omr/mahler7/IMSLP927114-PMLP30475-Mahler,_G._-_7._Symphony_i-d8be024bc1b4c89a/page-0001/attempt-001/page-0001.omr)
- [测试输入页 PNG](../output/omr/mahler7/IMSLP927114-PMLP30475-Mahler,_G._-_7._Symphony_i-d8be024bc1b4c89a/page-0001/attempt-001/page-0001.png)
- [重新排版第一页](../output/omr/mahler7/IMSLP927114-PMLP30475-Mahler,_G._-_7._Symphony_i-d8be024bc1b4c89a/page-0001/attempt-001/rerender-1-1.png) 和 [第二页](../output/omr/mahler7/IMSLP927114-PMLP30475-Mahler,_G._-_7._Symphony_i-d8be024bc1b4c89a/page-0001/attempt-001/rerender-1-2.png)
- `audiveris.log`、引擎自身日志及 `musescore-1.log`。

[三栏视觉对照](../output/omr/mahler7-review/comparison.png) 左侧是原页，中间和右侧是同一段音乐的两页重排结果。原谱的一页分成两页属于排版变化，不表示凭空多识别了音乐页。

[机器质量报告](../output/omr/mahler7/IMSLP927114-PMLP30475-Mahler,_G._-_7._Symphony_i-d8be024bc1b4c89a/report.json) 包含输入指纹、逐 part 数据、引擎诊断、缓存状态和全部输出路径；[视觉复核索引](../output/omr/mahler7-review/review.json) 固定记录这次样本。

初试位于 `output/omr/mahler7-probe/`；其输入原页 PNG 和完整控制台日志位于 `tmp/omr/mahler-probe/`，引擎自身日志、OMR、MXL、明文 XML 和重排 PNG 保留于输出目录。

## 已确认的问题

1. **拍号漏识**：原谱各谱表开头的 4/4 没有进入任一导出 part；不能用 MuseScore 的默认拍号补充来声称原始导出正确。
2. **节奏与震音失真**：原谱木管与弦乐的重复节奏、震音在重排中出现多余和弦、缺漏节奏及奇怪的连音组合。Audiveris 明确报告第 2、3 小节 `no correct rhythm`，第 2 小节 P3/P6 出现 `No timeOffset`，并警告全部 4 个小节没有可确定的目标时值。
3. **错误谱号变化**：原谱 Tenorhorn in B. 这一行在本页使用高音谱号；450 DPI 导出在第 3 小节末附近插入低音谱号，延续到下一重排页，造成明显音高表示风险。300 DPI 初试也存在错误谱号变化。
4. **多余音符与文字碎片**：长笛行部分原本单音变成和弦；弦乐下方出现原谱没有的歌词式碎片（如零散字母），一些演奏记号和震音被错误解释。
5. **名称和分组不完整**：双簧管等名称没有准确识别，部分声部成为 `Voice` 或仅剩数字；大提琴等分谱表的名称/分组需校对。17 个 part 与 17 条谱表吻合，只说明没有丢掉整条谱表，不代表配器或声部关系正确。

没有逐音符校对全部 4 小节，没有给出虚构准确率。MuseScore 日志还记录其便携安装目录的日志/崩溃配置文件写入受限，但两个 PNG 输出成功且均可解码；不把这些环境警告当作识谱正确的证据。

建议先在 Audiveris `.omr` 中校正拍号、谱号、误识的和弦/震音、节奏及配器分组，再重新导出并与原谱逐声部核对。若这些问题不先解决，暂不宜将全谱自动批量结果用于逐音符对齐。

## 复现和验证

在 Windows PowerShell 的项目根目录执行：

```powershell
./scripts/convert_score.ps1 -Pages '1' -MuseScore 'D:\software\MuseScorePortable\App\MuseScore\bin\MuseScore4.exe'
```

这条命令已实际执行：首次运行转换成功，重复运行命中 1 页缓存；原始输出的 SHA-256 与 MusicXML 结构在缓存返回前再次检查。加 `-Force` 可保留旧结果并重新识谱。

接口位于 `backend/score_processing/`，支持 PDF 路径、页码范围、输出目录、DPI、每页超时、额外重试次数、缓存和可选 MuseScore 重排。不同页面独立输出；不合并全曲声部，不推断原谱全曲小节编号。依赖与详细行为见 [接口说明](../docs/pdf-to-musicxml.md)。

11 项自动测试通过，覆盖 MXL 容器与明文解析、和弦/backup 时值、缺失拍号、结构空结果、谱表/小节不匹配、非法页码、缓存损坏、部分失败重试、失败后恢复以及渲染器返回 0 却无输出等情形。另以真实 Python 子进程验证超时能同时终止启动器和子进程，避免重试时后台识谱继续写入。引擎行为测试使用模拟引擎；本报告的数据和视觉检查来自真实 Audiveris/MuseScore 执行。测试日志为 `reports/mahler7-omr-tests.log`。

官方参数依据：[Audiveris CLI](https://audiveris.github.io/audiveris/_pages/guides/advanced/cli/)。
