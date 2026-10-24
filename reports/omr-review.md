# PDF 识谱小样复核

日期：2026-10-24。状态：**四个真实页面可运行识谱并导出 MusicXML，准确性仍需人工检查；没有完成全谱识别。**

## 实际执行

Audiveris 5.11.0，commit `9e1e55cd2746037d059345881c53e6a6754bffbd`，应用自带 OpenJDK 25.0.3、Tesseract 5.5.2。官方 Windows console MSI 的 SHA-256 为 `5f1b4e96a12c53c7da426814b76e599363c4181e291855996e0a6878dda95f71`，与官方发行元数据一致。

使用只读 MSI 数据流提取后，将程序、缓存和用户配置放在项目 `.tools/` 下。没有将它作为系统应用安装。初次行政解包返回 1603 后改用只读提取；初次 `tessdata_fast` 模型不含所需 legacy 引擎数据，日志显示 OCR 失败，已改用官方 `tesseract-ocr/tessdata` 的英文模型并重新执行独立样本。保留失败日志，不将其标为成功。

每个样本从用户 PDF 的指定物理页以 300 DPI 渲染 PNG，再单独执行 `-batch -transcribe -export -save`。四个样本分别保存 `.omr`、`.mxl` 和处理日志。单独输入避免最初选择不连续原谱页时出现 `.mvtnull.mxl` 同名导出覆盖的问题；`output/omr/modern-samples` 中的初次多页结果不是最终样本。

| 样本 | 原始物理页 | 导出 parts | 每 part 的 measure 数 | pitched 元素数 |
| --- | --- | ---: | ---: | ---: |
| modern-opening | 100 页重排谱第 1 页 | 23 | 3 | 60 |
| modern-ending | 100 页重排谱第 100 页 | 21 | 5 | 293 |
| scan-opening | 99 页扫描谱第 3 页 | 25 | 3 | 138 |
| scan-ending | 99 页扫描谱第 99 页 | 21 | 5 | 345 |

这些数字来自实际解包 MXL 并解析 XML，见 `reports/omr-samples.json`。**parts 不等于原谱谱表数量，pitched 元素数也不等于音符正确数。** 连音分段、移调、颤音、声部拆分和识谱错误都可能影响比较，不据此生成准确率。

## 需要复核的内容

- 同段开头在扫描谱和重排谱中的导出音符数量差异很大，需要逐声部比较漏识、误识与节奏。不能直接把扫描版结果用作全曲对齐真值。
- 末页两种输入的导出也不一致；需复核移调乐器、八度标记、配器合并与终止节奏。
- 独立页面导出的 MusicXML 小节从 1 重新编号。末页样本的 1–5 不能直接当成全曲第 1–5 小节；与原谱 531 起始编号的联系尚需保存为外部映射。
- 样本没有覆盖第 10 页无独立小节线的华彩，也没有覆盖中段复杂节奏。本阶段不据此宣称华彩 OMR 已通过。
- `.omr` 文件保留了识别内部信息，但本次同步使用的页面坐标来自矢量 PDF 原始线条及印刷编号，**不是从这四份 OMR 推导出的全谱定位**。

## 运行与阅读

复现脚本为 `scripts/run_omr_samples.ps1`。输出目录为 `output/omr/samples/`。可用解包的 Audiveris 打开对应 `.omr`，在图形界面检查并修正；导出 MusicXML 后也应在谱面编辑器中核对。

保留的证据包括 `reports/audiveris-version.log`、`reports/omr-modern.log`（初次 OCR 失败）、`reports/omr-samples.log`（修复后的重排谱）、`reports/omr-scan-samples.log`（扫描谱），以及输出目录中每个样本的完整日志。程序返回并导出文件，只证明流程可运行，不证明识谱准确。

官方来源：[Audiveris 5.11.0 发行](https://github.com/Audiveris/audiveris/releases/tag/5.11.0)、[安装文档](https://audiveris.github.io/audiveris/_pages/tutorials/install/binaries/)、[Tesseract 英文模型](https://github.com/tesseract-ocr/tessdata/blob/main/eng.traineddata)。程序许可为 AGPL-3.0；OCR 模型与其他依赖保留原许可，素材授权独立处理。
