# 第一阶段：拉威尔《左手钢琴协奏曲》输入审查

日期：2026-10-24（Asia/Shanghai）。状态：**素材可读；作品与版本兼容性仍待逐段复核**。

执行依据为 `WORKFLOW_Ravel_Left_Hand_Concerto.md`。本阶段只审查输入与工具，不表示已经完成 PDF 识谱、音频解码试听、全曲对齐或 MVP。

## 工作区与输入

原工作区只有工作流 Markdown 和 `resource/ravel left hand piano concerto/`，没有现成代码、依赖、测试或 Git 仓库。共发现 1 份 MP3、1 份 MIDI 和 2 份 PDF。未修改任何原始素材。

| 输入文件 | 大小（字节） | 实际检查结果 |
| --- | ---: | --- |
| `Krystian Zimerman,London Symphony Orchestra,Pierre Boulez - Piano Concerto for the left hand in D.mp3` | 43,844,440 | MPEG-1 Layer III；1,096.045714 秒（18:16.046）；44,100 Hz；双声道；320,000 bit/s，CBR |
| `IMSLP01581-Ravel_-_Piano_Concerto_for_the_Left_Hand_(Orchestral_Score).pdf` | 7,892,327 | 99 页；每页 648 × 864 pt；99 页均未提取到文字；抽样图像为扫描管弦乐总谱 |
| `maurice-ravel-piano-concerto-for-the-left-hand.pdf` | 1,996,742 | 100 页；每页 842 × 1191 pt；100 页均能提取文字或音乐字体字符；MuseScore Studio 4.5.2 输出的重排总谱 |
| `maurice-ravel-piano-concerto-for-the-left-hand.mid` | 629,776 | SMF Type 1；39 轨；480 ticks/四分音符；1,046.543489 秒（17:26.543）；26,141 个非零力度 note-on |

MP3 的 ID3 标题为 `Piano Concerto for the left hand in D`，演奏者字段为 Krystian Zimerman / London Symphony Orchestra / Pierre Boulez，专辑字段为 `Ravel: Piano Concertos; Valses nobles et sentimentales`。这些是文件自带标签，尚未通过发行资料或试听独立核验。Mutagen 未标记 header sketchy；这不等于全文件解码完整性检查。

## 两份 PDF 的可视核对

已用 Poppler 渲染并实际查看以下六页，页码均指 PDF 中从 1 开始的物理页：

| PDF | 检查页面 | 观察 |
| --- | --- | --- |
| 99 页扫描谱 | 第 1 页 | 封面为 Maurice Ravel、Concerto pour la main gauche、Piano et Orchestre，Durand 出版标识 |
| 99 页扫描谱 | 第 2 页 | 乐器编制表，非音乐正文；不能分配小节 |
| 99 页扫描谱 | 第 3 页 | 音乐开头，印刷正文第 1 页，Lento（四分音符 = 44），3/4；低弦开头与低音巴松进入可见 |
| 99 页扫描谱 | 第 99 页 | 印刷第 97 页，方框排练号 53、Allegro、6/8，终止线可见 |
| 100 页重排谱 | 第 1 页 | 标题同为 Concerto pour la main gauche；Lento（四分音符 = 44）、3/4，开头织体与扫描谱相似 |
| 100 页重排谱 | 第 100 页 | 小节起始标记 531、方框排练号 53、Allegro、6/8；末页五个小节的布局与扫描谱末页相似 |

**已观测到的异常：**重排 PDF 内部 `/Title` 是 `Une Barque Sur l'Ocean`，与页面标题冲突。页面首尾支持它是目标协奏曲的重排谱；内部标题可能是遗留元数据，但这是待确认解释，不能据此保证全部内容正确。

两份谱的首尾抽样支持同一作品，尚未比较全部音符、删节、华彩记法与中段页序。扫描谱暂作为原谱核查基准，重排谱作为 OMR 质量对照；这是可调整的工程选择，不是权威版本鉴定。PDF 页号、正文页号、方框排练号和小节号必须分开存储；尤其排练号 53 不能当作第 53 小节。

能从数字 PDF 提取字符不等于已经获得 MusicXML。扫描谱的 OMR 与页面坐标均尚未生成，不能将空文字层当作没有音符。

## MIDI 实际检查

使用 mido 1.3.3 读取全部事件，按合并轨道的 tempo map 积分。库给出的总时长和逐事件积分时长相差不到 `1e-6` 秒。此项只验证时间计算一致，不能独立证明 MIDI 记谱正确。

| 项目 | 观测值 |
| --- | --- |
| 轨数 / 分辨率 | 39 / 480 ticks per quarter note |
| 速度事件 | 74；四分音符速度约 10.00002–210.00021 BPM |
| 开始速度 | 约 40 BPM；两份 PDF 开头均印为 44，需记录差异 |
| 拍号事件 | 38 |
| 出现的拍号 | 2/4、3/4、4/4、5/8、6/8、9/8、12/8、13/8、15/8、34/16 |
| 调号事件 | 586；分布在多轨，不能视为 586 次全局转调 |
| marker 事件 | 53；尚未逐项证明与 PDF 排练号一一对应 |
| 音符发声起点 | 26,141 个（排除了 velocity = 0 的 note-on） |
| 非音符事件 | 大量控制器、程序、端口与 pitchwheel 事件；原数据应保留 |

轨名覆盖木管、铜管、打击乐、竖琴、钢琴和弦乐；钢琴名轨为索引 23、24，两轨分别有 3,789 和 1,947 个非零力度 note-on。这不是两只手或两个钢琴声部的可靠证明。部分轨名按 mido 默认 Latin-1 解码出现乱码，之后需人工或按来源核对编码，不能静默修改原数据。多 MIDI port 与 channel 信息也应保留，不能仅按通道合并声部。

复杂拍号（例如 34/16）和极低速度值得与华彩或自由节奏处核对；目前不能宣称它们一定错误，也不能反过来宣称它们已经正确表达华彩。

## 兼容性判断与待办

| 问题 | 状态 / 依据 | 下一步 |
| --- | --- | --- |
| 是否同一作品 | PDF 首尾可视抽样及 MP3 自带标签支持；MIDI 配器仅为旁证 | 复核 MIDI 开头、主题位置、华彩和结尾音符，对照原谱并试听录音 |
| MP3 与 MIDI 时长 | MP3 比 MIDI 长约 49.502 秒，约为 MIDI 时长的 4.73% | 通过非线性对齐区分演奏速度差、静音、延长、删节等；不能从总时长直接判断原因 |
| 两份 PDF 页数 | 99 与 100；扫描谱前两页为封面/编制，重排谱第 1 页即正文 | 为每份 PDF 单独建立小节坐标，不按页数直接映射 |
| 重排谱内部标题冲突 | `needs_review`；内部 Title 与实际页面不一致 | 保留原文件和指纹，在项目显示作品标题的人工确认值与来源 |
| PDF 与 MIDI 初始速度 | 44 与约 40 BPM | 作为输入差异记录；MIDI 秒不能直接当作录音秒 |
| 中段、华彩、反复与版本 | 未完成逐段核对 | 获得 OMR 后比较真实音符/节奏事件，再选择人工锚点 |
| 完整音频及全页视觉完整性 | 未完成 | 后续做全曲解码、波形/特征检查和异常页复核 |

**兼容性最终状态：`needs_score_and_audio_review`。** 没有输出伪造的置信度或时间戳。

## 文件指纹

指纹为原始文件完整内容的 SHA-256，全部值保存在机器可读的 `reports/input-audit.json`，其中还保留全部页面尺寸、逐轨摘要及速度/拍号事件位置。

```text
MP3          a9078597fef47f6ac99cf4d3241984721d1992a28ced3a97182f18c7de3f56d4
扫描 PDF     4ef405bb68ad16fbd8011af6a3e9f19de104b1631accfbd8661bd59fa3b4e149
重排 PDF     67aa60cc89160ea7e475fd7fa45352ec6e0c45f6cd3557421d8caafc18531083
MIDI         f9ba8d12d461fa9f869ae4e083d2f47f58f4d87a5ad85fbfc4b84f9d5649a8a3
```

## 复现方式

脚本 `scripts/audit_inputs.py` 只在本地读取素材并写审查 JSON，不上传数据。依赖记录在 `requirements-audit.txt`；本次实际版本为 pypdf 6.10.0、mutagen 1.47.0、mido 1.3.3，Python 3.12.14。

普通 Python 环境可以运行：

```powershell
python -m pip install -r requirements-audit.txt
python scripts/audit_inputs.py
python scripts/audit_inputs.py --skip-midi --output tmp/input-audit-without-midi.json
```

本机实际执行使用应用自带 Python：

```powershell
& 'C:\Users\32599\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/audit_inputs.py
```

mutagen/mido 安装在项目 `.tools/audit-packages`；脚本自动读取该目录，mido 只在真正审查 MIDI 时导入。无 MIDI 文件时状态为 `not_provided`；显式跳过时为 `skipped_by_request`。这只是输入审查层的可选设计，**尚未验证无 MIDI 的 OMR/对齐端到端流程**。

## 本阶段实际验证与边界

- 已实际运行四个素材的完整指纹计算与元数据读取；两份 PDF 全部页面可解析，成功写出 4 项素材的审查 JSON。
- 已实际渲染并人工查看上述 6 个真实 PDF 页面，首尾没有发现空白谱页；没有逐页视觉核对全谱。
- 已读取 MIDI 全部事件并按速度变化积分；未采用固定 BPM 或平均小节时长。
- 已实际运行 `--skip-midi`，成功写出 3 项素材的 JSON，状态为 `skipped_by_request`；这是显式跳过测试，尚未另做物理删除 MIDI 文件的用例。
- 已重新计算四个原素材的 SHA-256，与报告一致；有/无 MIDI 审查中的 MP3/PDF 指纹一致，页面数量断言和 MIDI 时间积分一致性检查全部通过。
- 未运行 React、OMR、DTW、音频试听或全曲解码，没有宣称这些测试通过。

下一步按工作流进入数据格式和本地接口设计，再对真实 PDF 做 OMR 小样。识谱、对齐与研究分析将各自保留独立状态和证据。
