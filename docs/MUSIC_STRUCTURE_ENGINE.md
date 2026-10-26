# 独立音乐结构分析引擎

**MusicXML后续接入：** 当前全谱符号主路线为`backend/musicxml_analysis/`与`analysis/musicxml/`，逐谱窗口继续提供直接读谱核查；见[MusicXML接入与音乐分析](../reports/ravel-musicxml-analysis-20261026.md)。下文的“当前”描述保留此前阶段的历史语境。

**2026-10-26研究调整：** 当前主路线为 `backend/score_studies.py` 与 `analysis/score-studies/`。精细和声／对位使用局部逐谱底稿；配器与全曲层级独立研究，不受全局未匹配数约束。旧自动引擎仅为可选辅助。下文保留其历史范围与限制，旧C/D开关只约束该自动实验。见[当前音乐成果与流程](../reports/ravel-musical-studies-20261026.md)。

本轮实现离线候选生成与播放器接入；没有完成音乐学院标准的全曲自动分析。试验只处理现有拉威尔矢量总谱物理1–3、10–15页。A/B尚未通过逐音内容验收，C/D不扩展。具体结果见[实测报告](../reports/ravel-structure-engine.md)。

## A/B续轮

当前播放稿为 `round1-a7657439303a57e6`。新增基于bassa方向的八度归属、符干／小节线区分、单音与双音震音几何、未改变MIDI的记谱持续性记录，以及8组分维读谱抽查。代理记录与清单指纹绑定，保存在冻结轮次之外；旧稿和修订稿保留。MIDI note-on/off层不等于源谱指法，源谱休止与参考长键值的差别必须显式保留。当前问题与测试见[续轮报告](../reports/ravel-ab-notation-review.md)。

## 流程与依赖

`原PDF／辅助MIDI → 分离的原始观测 → 理论候选 → 引用与指纹校验 → 四维HUD`

计算入口为 `backend/structure_analysis/`。处理依赖沿用 `requirements-processing.txt`；播放和证据接口只使用标准库及原播放器依赖，不导入 pdfplumber 或 mido。运行示例：

```powershell
python -m backend.structure_analysis build --profile analysis/engine/profiles/ravel-vector-pilot.json --output analysis/engine/ravel-pilot --activate
python -m backend.structure_analysis validate analysis/engine/ravel-pilot/round1-9bf0f07362a89fb9
```

`--activate` 只切换 `analysis/engine/current.json`。不改媒体、alignment、measure-map、旧事件、文章或用户锚点。相同输入、代码与运行库版本复用同一轮；冻结文件被改动时拒绝覆盖。输出清单记录算法源码、输入、产物指纹及运行库版本。

## 原始证据与对应

本适配器读取现有矢量谱的原生SMuFL字符、五线谱、谱号、调号、临时变音和部分八度线。页／谱表拓扑、乐器与移调关系保存在指纹绑定的 `profiles/ravel-vector-pilot.json`。这不是通用PDF识谱器。

- 原生字符锚点是PDF观测；音头外框按锚点和谱间距估计，原字体框另存，不能把字体行高当作音头位置。
- 记谱音、移调实音及八度线解码均为候选。MIDI轨道、端口、通道、音高、离键与CC64延音分别保留。
- 完整节奏、连音／延音线、连奏线和声部身份尚未从PDF恢复。MIDI时值不能冒充校对过的PDF转录。
- 对应采用音序和候选小节约束，保留未匹配与八度分歧；延续音及震音实现采用单独的对应类型。
- `midi_measure_candidate` 是参考分节，不是已经核验的原谱号码。物理系统索引也不强行套用旧同步几何。

记谱编码参照[SMuFL音头](https://smufl.formats.music/latest/tables/noteheads.html)、[谱号](https://smufl.formats.music/latest/tables/clefs.html)、[力度](https://smufl.formats.music/latest/tables/dynamics.html)、[八度](https://smufl.formats.music/latest/tables/octaves.html)和[键盘记号](https://smufl.formats.music/latest/tables/keyboard-techniques.html)规范。字形含义与它在具体谱面中的音乐解释分开保存。

## 已实现的算法及其边界

| 模块 | 真正运行的步骤 | 仍依赖校对／判断 |
|---|---|---|
| Harmony | 按起音、离键、延音终点分窗；同时音集与跨时分解集合分开；实际模型低音、有限三度和弦模板及转位；四度／五声集合；竞争级数语境、音阶时值拟合；部分经过／辅助音与邻接进行候选 | 局部主音、功能、转调、完整非和弦音／挂留与终止；真实踏板和录音衰减 |
| Counterpoint | 分轨高低音投影；加倍、平行、运动方向、起音网格与持音重叠；持音＋快速音型候选 | 真实声部追踪、主副旋律层级、严格模仿／卡农／赋格；不能把轨道视为天然声部 |
| Orchestration | 参与、进入／退出、音域；独立提取力度／奏法／八度／踏板记号；规则化职责假设、层数与音域变化 | 动态记号归属及跨段延续、旋律权重、音色融合、真实材料交接及其形式意义 |
| Motif | 五音半音轮廓＋起音间隔比例的精确对应；移调、时间比例、入口差与原型／回答音符 | 同主题身份、变形与真实模仿；相同音型可能只是伴奏；不重叠入口不称严格对位模仿 |
| Form | 拍号、参考速度、候选动机、音响与配器的多类边界信号；Work→Movement→Section→Phrase→Motif | 完整乐句／乐段、终止、呈示／展开／再现等功能与全曲模型。Phrase目前是含动机片段，不能计作已认定乐句 |

同一配器变化产生的“进入”和“密度”只算一类边界证据。单一信号不足以宣告分部；多信号也仅生成候选。没有默认奏鸣曲式或三部曲式标签。

## 冻结文件

每轮目录包含：

| 文件 | 内容 |
|---|---|
| `profile.json` | 源指纹、试验范围、谱表／乐器移调适配 |
| `pdf-observations.json` | 音头锚点、记谱音候选、谱表、标记 |
| `notes.json` / `correspondence.json` | MIDI逐音与离键／延音、参考时钟、候选对应及缺口 |
| `harmony.json` | 纵向窗口、按键／延音双层、分解集合、进行与非和弦音候选 |
| `counterpoint.json` | 分轨投影、间隔／节奏／运动见证、复合旋律候选 |
| `instrument-activity.json` | 活动边缘、乐器职责假设及记谱标记 |
| `theme-identities.json` | 轮廓、重复位置与原型／回答；主题身份未指定 |
| `form.json` | 信号、候选边界、结构层级及未决功能 |
| `hud-events.json` | 四维展示事件及原始、中间证据ID |
| `validation.json` / `manifest.json` | 分维统计、验收门槛、指纹及版本 |

每个HUD事件包含唯一ID、维度、结论、范围、框架、理由、原始音符ID、中间证据、结构关系、核查状态与不确定项。`verification.score=pending`；算法不得自行设为verified。原始字形／MIDI、理论候选和文章诠释不合成单一“置信度”。

## 文献比较与修订

算法输入不含论文或旧文章。此前会话已经接触文献，因此本轮是输入独立实验，不能称为历史意义上的盲研究。保留早期冻结稿 `round1-0b80fb2654179afd`；之后修复音头框、离键边界、跨谱表轮廓等，不反写旧轮。

第二轮比较须在独立目录外另存，必须区分一致、分歧、独立但未验证、未决四类；没有分歧时如实留空：

```powershell
python -m backend.structure_analysis compare --run analysis/engine/ravel-pilot/round1-9bf0f07362a89fb9 --input analysis/engine/comparisons/ravel-ab-round2.input.json --output analysis/engine/comparisons/my-round2.json
```

输出绑定第一轮清单指纹，验证证据ID，拒绝覆盖已有比较或写入冻结目录。当前比较保存于 `analysis/engine/comparisons/ravel-ab-round2.json`。旧D/A解释的收窄另见 `analysis/revisions/return-tonic-layer-20261025.json`，不是用文献观点覆盖独立结果。

## HUD与接口

- `/api/research` 合并既有研究与当前候选；原事件文件不被批量替换。
- `/api/structure?track=ravel-left-hand` 返回清单和四维统计。
- `/api/structure-evidence?track=ravel-left-hand&event_id=…` 返回逐音、原生音头、乐器移调、原谱标记、理论记录及形式层级／材料见证。
- `reference_interval_candidate` 使用绑定MIDI指纹的前闭后开tick区间，由既有候选对齐投影；不保存新的录音秒数，也不冒称精确小节实播。
- 新窗口与旧PDF几何不完全一致时，卡片明确列出证据页范围。候选卡片不会获得“已校准跳播”能力。
- 四个维度独立更新，未变的卡片不重建。异步证据响应与曲目切换隔离；文章DOM及滚动位置不因HUD更新而重置。
- 引擎损坏或指纹失效时拒绝自动结果，保留既有文章和播放器，并显示原因。

## 验证顺序

```powershell
python -m unittest discover -s tests -v
node --test --test-isolation=none tests/test_engine_hud.mjs tests/test_structural_hud.mjs tests/test_hermeneutic_navigation.mjs
# 另开8766服务后运行；这是实际模块＋HTTP的内存DOM联调
node scripts/check_research_app.mjs
```

内容样例检查真实音集、低音／转位、踏板层、加倍、材料对应及边界信号；不是只检查JSON格式。结构检查、代理图像抽查、真实浏览器实播、人工音乐校对与专家审核必须分别报告。A/B仍有识谱与声部缺口，不能因为软件检查通过就开放C/D。
