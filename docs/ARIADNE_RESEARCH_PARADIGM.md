# Ariadne 双阅读路径与研究数据规范 v0.1

## 两种时间尺度

谱面技术仪表（Structural HUD）位于中间谱面容器顶部。和声、对位、曲式、配器分别索引与更新；动机维度在数据层保留。播放中只查询预载事件，不调用模型。变化边界由各条事件的谱面定位决定，不能统一退化为“每页一个和弦”。

右侧“诠释研究”用于长文、比较和论证。默认固定文章与其独立滚动位置，切换原有三个标签不销毁文章。开启“自动跟随相关诠释”时，只有匹配的专题发生变化才换文；缺少匹配时保留正在阅读的文章。主动选择文章或从HUD打开关联文章会关闭自动跟随。

界面同时保留短导聆、录音阵容、文献、音视频控制、循环和人工校正。新增研究数据缺失时显示空状态，不影响旧曲目的播放。窄屏的技术栏默认折叠，避免占用谱面首行；可手动展开。

## 三个认识层次

| 字段 | 含义 | 不能自动升级的情况 |
| --- | --- | --- |
| `score_observation` | 当前谱面中可观察的事实 | 查看关键页不等于全谱逐音确认 |
| `theoretical_analysis` | 采用某个框架的结构解释 | 作者提出的分析不等于唯一的乐谱事实 |
| `hermeneutic_interpretation` | 跨区间的历史、审美或意义诠释 | 不能冒充已证明的作曲意图 |

任务书提到的汉斯立克、Nattiez／Molino及阿多诺是后续方法论参照；本次没有读取其著作，也没有为本曲强行套用这些哲学立场。对非功能性和声、音集合或有争议的分析允许并列观点，不强制填充罗马数字。

## 文件与接口

每首作品自己的 `analysis/` 中可包含：

- `structural-events.json`：`schema_version`、`work_id`、`edition`、`events`。
- `hermeneutic-essays.json`：相同的版本绑定和 `essays`。
- `sources.json`：可选补充来源。已有文献复用 `analysis_data.load_analysis()` 的 `source_id` 和实际阅读状态，不重复声明已读全文。
- `essays/*.md`：可编辑正文；条目也可内联Markdown，两者只能选一个。

`GET /api/research?track=ravel-left-hand` 使用既有曲目白名单，返回 `available`、`edition`、`events`、`essays`、`sources`。缺文件返回200及合法空结果；错误曲目返回404；结构、来源、路径或指纹错误返回422。前端研究层显示读取错误并清空旧内容，原播放器继续运行。

研究loader同时核对当前PDF真实内容指纹、项目版次、作品身份及原导聆绑定。演奏专属观察还必须明确 `recording.recording_id` 和 `recording.audio_sha256`，并检查实际录音文件。路径经解析后必须仍位于当前项目内。Markdown沿用Mistune安全转义；不接受任意脚本HTML。

## 坐标及精度

分析首先绑定 `edition.edition_id` 与 `edition.pdf_sha256`。页码始终是物理PDF页码，不能与印刷页码或其他谱本混用。

| `score_spans[].precision` | 激活方式 | 显示与导航 |
| --- | --- | --- |
| `page_range` | 当前播放谱页位于首末页之间 | 本页／本段背景，不能用作即时和弦；只打开PDF，不seek音频 |
| `score_segment_candidate` | 页码与实际区域／参考ID都匹配 | 候选区域提示；不冒称原谱编号 |
| `score_segment` | `[物理页,0起始系统索引,横坐标点数]` 前闭后开 | 可同页多段；未知系统／横坐标时不激活 |
| `unlocated` | 不自动激活 | 保留研究条目，无页码和可点击时间 |

`pdf_page_start/end` 是闭区间；精细段落使用 `score_start/end`。`region_ids` 必须来自当前映射。原谱小节、拍位和声部可以作为后续补充字段；未知允许为空，不能由MIDI推断序号填成真实小节号。

作品级事件和文章不写死录音秒数。播放器使用现有 `alignment` 和 `prepareScoreRegions()` 的运行时结果获得当前位置；区域人工校正立即反映到上下文。新文章跳转仅当定位被明确校核、时间状态为已审核、且实际区域具有人工时间校正时，才使用其运行时起点。仅有页码或机器候选一律只翻页，同时关闭自动跟谱，标注音频位置待核查。

播放位置与浏览页分别传入。HUD始终依附播放位置；手动翻页不会把浏览页伪装成已seek的位置。数据缺口清除该维度的标签；其他维度和长文不受影响。

## 条目与核查状态

事件至少有唯一ID、维度、认识层次、短标签、详解、一个或多个谱面范围、具体来源及独立 `verification.score/literature/location/timing`。文章另有标题、`reading_mode: persistent`、正文和可选关联事件。两者允许多个不连续范围与同一位置的竞争观点。

状态使用明确字符串，例如 `pending`、`disputed`、`key_pages_checked`、`relevant_sections_checked`、`page_range`、`candidate_alignment`。人工 `verified` 的谱面／定位必须记录审核者和日期。文章的编辑完成度、谱面事实、文献阅读范围与时间精度各自独立。禁止新增虚构浮点“准确率”。

实际实现：后端 `scripts/research_data.py`；纯定位逻辑 `review/research-model.mjs`；技术仪表 `structural-hud.mjs`；长文 `hermeneutics.mjs`；加载及版本隔离 `research.mjs`；共用安全DOM呈现 `research-ui.mjs`。`app.mjs`只接线到统一媒体上下文，`analysis.mjs`只扩充第四个标签。没有重写框架，也没有重跑对齐或OMR。
