# 第一阶段：技术审查与候选方案

> 后续更新：2026-10-24 已在用户创建的 Conda 环境中实跑 Sync Toolbox 1.4.2，并以便携方式运行 Audiveris 5.11.0。以下保留首次审查的历史状态；实际结果与当前限制见 `reports/alignment-test.md`、`reports/omr-review.md`。

审查日期：2026-10-24（Asia/Shanghai）。执行依据：`docs/workflows/ravel-left-hand-original.md`。

## 审查结论与状态

工作区开始时只有工作流说明和 `resource/` 素材，没有 Git 仓库、前端、后端、依赖清单或测试。本阶段只建立可重复的素材审查，不先生成播放器或虚构同步数据。

建议进入原型验证的组合：**Audiveris 本地识谱 + 原始 PDF 页面坐标 + Sync Toolbox 离线全局对齐 + React/TypeScript/Vite 播放器**。这是基于官方资料与部分源码的选型判断，**尚未在本作品上执行 OMR 或 DTW，不代表准确度已验证**。

MIDI 为可选旁证。正式路径应为 PDF → OMR → 经复核的 MusicXML → 符号音符特征 → 录音全曲 DTW；不能用用户提供的 MIDI 取代 PDF 识谱验收。由 OMR 结果生成的中间 MIDI 可以是内部格式，但不得成为要求用户额外提供的输入。

## 官方资料比较

下表的“支持”是资料或源码层面的能力；所有候选引擎的本地运行、Windows 安装和真实素材效果均为**待验证**。安装难度是基于依赖的工程估计。

| 工具 | 输入与输出 | 离线全局对齐 | PDF / OMR 与坐标 | 许可 | 安装成本与主要限制 | 本项目用途 |
| --- | --- | --- | --- | --- | --- | --- |
| Audiveris | PDF/图像 → `.omr`；导出 MusicXML 4.0 的部分 OMR 数据 | 不提供音频对齐 | OMR 引擎和人工编辑器；`.omr` 保存内部数据，坐标关联需验证 | AGPL-3.0 | 中等；官方 Windows 安装包含 JRE；复杂总谱仍需人工修正 | 首选 OMR 候选，保留原 PDF 与 `.omr`，不只留 MusicXML。[官方说明](https://github.com/Audiveris/audiveris)、[许可](https://github.com/Audiveris/audiveris/blob/master/LICENSE) |
| Sync Toolbox | 音频与特征序列；官方谱音示例使用符号音符 CSV；返回 DTW 路径 | 有 MrMsDTW 全局序列对齐实现 | 不识别 PDF，不产生页面坐标；源码提供 MusicXML 转音乐时间 CSV 工具 | MIT；示例数据另计 | 中等；依赖 librosa/scipy/numba/music21 等；谱面时间、秒与小节转换需处理 | 首选离线引擎候选。[README](https://github.com/groupmm/synctoolbox/blob/master/README.md)、[依赖](https://github.com/groupmm/synctoolbox/blob/master/pyproject.toml) |
| SSV Alignment | README 面向 MEI 编码和录音；所读脚本实际还要求 reference MIDI、MEI URI 和录音目录 | 基于 Sync Toolbox，支持离线流程 | 不含 PDF OMR；不能直接把 MEI 宣传为 PDF 输入 | MIT | 较高；脚本有硬编码假设与旧依赖；当前入口要求至少两份音频 | 参考谱面映射和 Listen Here 输出；不直接接入原脚本。[README](https://github.com/Signature-Sound-Vienna/alignment)、[源码](https://github.com/Signature-Sound-Vienna/alignment/blob/main/align-to-score.py)、[依赖](https://github.com/Signature-Sound-Vienna/alignment/blob/main/requirements.txt) |
| Matchmaker | 示例为 MusicXML 乐谱 + 录制 WAV，或实时音频/MIDI；输出拍位置 | 主要是在线跟谱；录音 simulation 仍运行在线算法，不能据此宣称全局最优 | 核心库不处理 PDF 的页面映射 | Apache-2.0 | 中高；FluidSynth；Windows 原生依赖可能需要额外配置 | 作为对照，不作默认主引擎。[官方说明](https://github.com/pymatchmaker/matchmaker) |
| OpenVoicing | MusicXML/Guitar Pro、录音、同步图与 `.ovb` 项目包 | 有录音同步编辑与播放；已读材料不足以认定有自动全局对齐引擎 | OMR 在 README 中列为计划功能；重排记谱不能代替原 PDF 坐标 | MIT；第三方 alphaTab 为 MPL-2.0，字体与音色另有声明 | 中等；Node 22+、pnpm；pre-1.0 API 和包格式会变化 | 参考播放器交互、嵌入和包格式；不整套替代本项目。[README 与许可说明](https://github.com/pjdoland/openvoicing) |
| Matchmaker Demo | MusicXML/MEI/PDF，录制音频或 MIDI；浏览器显示同步结果 | simulation 可预计算，但算法类别仍需按 Matchmaker 区分 | README 描述 Audiveris → `.omr` → MIDI + pixel mapping；PDF 支持实验性 | Apache-2.0；Audiveris 等依赖各有许可 | 较高；Python 3.12、Node 20+、FluidSynth、Audiveris，或 Docker | 参考 `.omr` 坐标提取接口；不能直接照搬模拟模式完成离线验收。[官方说明](https://github.com/pymatchmaker/matchmaker-demo) |

## 已阅读的关键实现及影响

### Sync Toolbox

工作流提供的 `meinard-mueller/synctoolbox` 地址未能读取；搜索定位到当前可访问的 [groupmm/synctoolbox](https://github.com/groupmm/synctoolbox)，其包元数据仍包含旧 `meinardmueller` 地址。集成前应固定实际版本与提交，不能把默认分支当成固定发布版本。

已阅读[官方谱音 notebook](https://github.com/groupmm/synctoolbox/blob/master/sync_audio_score_full.ipynb)和 [csv_tools.py](https://github.com/groupmm/synctoolbox/blob/master/synctoolbox/feature/csv_tools.py)。前者展示符号音符的 chroma/onset 特征与录音特征进行 MrMsDTW，不要求先将整份乐谱合成为管弦乐录音。后者提供 `music_xml_to_csv_musical_time`，处理连音与反复，并检查各声部小节数量和位置是否一致。**其音乐时间 CSV 不是直接可当作秒的输入**；MusicXML → 音符时间轴 → 特征的适配与原始小节 ID 的关联仍需实测。弱起、无拍号华彩、移调乐器、打击乐、重复与再现必须单独复核。

当前读取的 pyproject 标为 1.4.2、Python `>=3.10,<3.15.0`；README 的历史安装提示较宽，应以选定版本元数据为准。候选参数可以参考官方示例的 22,050 Hz、50 特征帧/秒、chroma + DLNCO，正式结果必须记录实际参数、运行版本、耗时和异常，不能把示例参数说成针对拉威尔已调优。

### SSV Alignment

`align-to-score.py` 的命令行要求 `--referenceMidi`、`--meiUri`，并检查至少两份录音。源码中的 `midiTempo = 120` 注释指向 Verovio 生成的参考 MIDI，不能套用到用户这份有速度变化的 MIDI。依赖清单固定了旧版 numpy/librosa 等，因此不应在本机 Python 3.12 中直接照抄整份环境。上述为源码审查发现，未执行该脚本。

### PDF 识谱与定位

Audiveris 官方明确说明识别不可能始终达到 100%，且 MusicXML 只导出部分内部信息。后续需要同时保留 `.omr`、MusicXML、原 PDF 指纹和每页坐标变换。Matchmaker Demo 的页面映射流程目前仅核对了 README，尚未核对具体解析代码；小节边界、跨页、声部合并及坐标轴方向均标记待验证。

软件许可证与录音/乐谱授权分开记录。暂不复制第三方工程代码或分发它们的示例素材；若以后复用实现，保留其许可与第三方声明。本报告没有作软件组合的法律判断。

## 本机实际检查

| 检查 | 实际结果 |
| --- | --- |
| Node / npm | Node 24.18.0，npm 11.16.0，可调用 |
| Python | 应用附带 Python 3.12.14 可调用；系统 `python` 命令只定位到 WindowsApps 入口，未作为有效运行环境使用 |
| PDF | bundled pypdf、pdfplumber 与 Poppler 可用；已用 pypdf 读取，用 pdftoppm 渲染样本页面 |
| MP3 / MIDI 审查 | 项目 `.tools/audit-packages` 安装 mutagen 1.47.0、mido 1.3.3；可本地读取素材 |
| Audiveris / Java / FluidSynth / ffprobe | 当前 PATH 未找到；不等同于对全盘安装情况的断言 |
| 对齐依赖 | 当前 bundled Python 中未发现 synctoolbox、librosa、scipy、partitura、soundfile；本阶段未安装对齐环境 |

依赖仅用于本地读取素材。联网操作只读取官方项目资料与下载开源库，没有上传音频、MIDI 或 PDF。

## 下一阶段的具体验证顺序

1. 定义版本化数据格式，分别存储输入指纹、内部小节 ID、印刷编号、排练号、页面、坐标、谱面时间与录音秒；分析注释独立保存。
2. 建立本地前后端接口；先能播放 MP3、显示原始 PDF 和明确展示“未对齐”。不要生成按时长均分的小节。
3. 在 99 页扫描总谱第 3 页和 100 页重排谱第 1 页执行 OMR 小样，保存原始输出、错误和坐标；再选一页华彩/密集织体做人工检查。小样完成后写 `reports/omr-review.md`，尚未识谱前不生成“识别通过”报告。
4. 基于 OMR 结果走一次**不提供用户 MIDI**的全曲对齐路径；再用现有 MIDI 作为旁证。允许内部格式转换，但必须保留 PDF → MusicXML 的证据链。
5. 对华彩或速度伸缩段抽查，与人工锚点比较；记录秒误差和定位依据。单调性仅是必要检查，不是准确性证明。
6. 研究报告可独立推进；播放器最后组合对齐结果、原谱坐标和有来源的注释。

## 阶段验收

已完成：工作区盘点、官方工具资料比较、部分源码审查和真实输入审查，具体数字与验证见 `reports/input-audit.md`。未完成：候选引擎本地安装试跑、识谱、全曲对齐、音乐分析和播放器。当前交付属于第一阶段，不能标记整个 MVP 已完成。
