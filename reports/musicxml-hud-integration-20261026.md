# 统一谱面技术HUD：实施与检查（2026-10-26）

## 工作区与基线

已读取 `AGENTS.md`、`docs/design/musicxml-hud-integration.md`，随后采用用户新粘贴的修订说明：唯一四维入口，桌面优先单排、窄屏两列，详情侧栏，四维各自更新。

实际执行 `git fetch origin main`。本地HEAD与远端main均为 `361cb9f4e2d8d5e2b6a30aceafcdc827f2f7df71`，双方提交差异0。工作区已有未提交的拉威尔艾马尔视频版、共享谱面读取、独立视频投影、测试及文档；这些改动保留，没有回退到GitHub版本。本轮没有暂存、提交或推送。

实施前实际运行基线：Python158项，156通过、2跳过；前端38项全部通过。后续数量均来自本轮运行日志，不沿用旧README统计。

## 界面与组件

- PDF上方只有 `#structural-hud` 的四张卡：和声、配器与织体、对位、曲式。`#musicxml-live` 重复面板移除，其模块保留为单一只读数据提供者。位置栏区分播放与浏览。
- 宽度足够时单排四卡，不足时两列；移动端可折叠。长内容受摘要行数约束，完整内容在点击后查看。真实像素高度尚未测量。
- `#hud-detail` 与默认折叠的535小节 `#musicxml-reader` 统一移到右侧“技术证据”。不会在PDF前长期展开长表格。证据与诠释文章有各自的滚动容器。
- 卡片点击固定打开时点的证据快照，播放继续；“完整小节数据”按需取源音符。音符ID可点开编码音、记谱音、实音、声部／谱表、instrument_ref和起止信息。独立选择小节及查看PDF不seek。
- “返回乐谱”关闭技术阅读面板、恢复当前播放谱页的跟随，不改变录音时间。打开技术证据不替换 `#essay-body`。

结构：`research.mjs → 单一MusicXML数据提供者 → score-analysis-model.mjs → 四维HUD`。原研究、直接读谱、XML小节索引、可选PDF/MIDI候选按不同问题关联，不以来源优先级选赢家。XML逐小节四个同名事件保留在原始接口与数据中，作为证据索引，不再重复成为主HUD按钮。

## 认识层次与更新

**和声**：当前全体记谱音响与全体最低音，和所选层的根音、最低音、转位分开。背景区间独立；示范仅发布源证据支持的m.11 E1持续低音，其余没有可靠跨时归约的地方显示背景待分析。瞬时和弦不自动延续为背景。

**配器**：显示同一记谱时点真实活跃的XML分部。分部数不等于乐器种类、演奏员或独立旋律条数。时值／音域启发的职责明确称候选；已关联的低弦加倍、分次进入与独奏内部声部另列证据，不按左／右手虚构分工。非定音打击乐只进入配器。

**对位**：保留具体音程与声部见证、原逐谱解释及完整小节运动数据；未获得严格模仿／独立性结论时不填造。

**曲式**：复用既有段落层级与两个竞争模型；声部／动机／乐句证据仍可向下查阅，不把每个小节等同于乐句。卡片按结构ID变化更新，不随每个音符重建。

四维签名分别更新。和声卡的表层与背景也使用独立DOM槽位；只有乐器变化时不重写背景。技术详情固定用户打开时的快照，不随播放刷新。诠释文章保持原节点、专题选择与非零滚动位置。

## 四组音乐案例及附加检查

案例文案不是按小节号替换实时结果。展示仍来自原和声窗口与激活帧；小型案例记录绑定确切窗口、源音符ID、起止与快照指纹，并在生成时检查下列实际内容。

| 案例 | 源证据与实际检查 | 状态 |
|---|---|---|
| m.11，小节内1 | `xml-h-000197`：全体最低E1；除E音级层外为G–B♭–D–F，层内最低D2、第二转位。弦乐层E半减七为不同分析对象；两项均保留。E1背景仅采用源音符`P9-xml-m0011-n0001`的XML全曲区间[30,33)。 | 源数据、视图模型及HTTP／模块检查通过；非人工签核 |
| m.58，小节内13/8，PDF12 | `xml-h-001097`：G♭1、G♭2、D♭4、G♭4，只有两个音级，显示开放五度、不补三音或I/V。背景待分析。同一钢琴分部存在不同voice／staff，不能推出单线织体。 | 同上 |
| m.63末弱起→m.64，PDF15 | `xml-h-001206`的D/A窗口，与m.64内0、3/4、1三个时点分开；全体最低依次A3、A3、A1、D1。E大三和弦上层与持续低音分别查，不把整小节做并集。 | 同上 |
| m.520，PDF95 | 小节内2：P23／P30／P32／P35；11/4：P7低音单簧管D2加入。中提琴B3/D4与大提琴B2/D3的八度关系、G1支撑与钢琴多声部均有源音符记录。 | 同上 |

附加：m.7保留E1／F♭1的同实音不同拼写，非定音事件不进入和声音集；m.34独立选阅打开物理PDF11而不seek。最后未覆盖的0.4个XML四分音符继续不外推。视频片头和谢幕也不激活谱面音符状态。

### 罗马数字兼容性

没有重算和声引擎或覆盖旧读法。仅在既有“指定调性＋级数＋所选层音集”上，用可选music21重建音集检查。6746项条件输出对应946个去重组合；5698项兼容，1048项暂缓作为有效级数展示。

例如m.520所选G大三和弦音集为[2,7,11]；原B小调`bVI`重建为[1,6,10]，因此显示“条件性级数待审查”，而不是静默当成自然调内和弦。原字段保留在冻结读法及`functions_original`中。此检查不是功能和声认证、作曲错误计数或准确率。

新核查层为 `analysis/hud/current.json → analysis/hud/ravel-20261026-v2`：8个小型示范窗口、1个持续层区间、946个去重兼容性记录。没有复制几千条和声事件为新数据库。第一份本轮开发稿移到忽略的`.tools/hud-history/`；原引擎／XML冻结历史不动。

## 修改文件

本轮整合代码与数据：

- `review/index.html`：四卡及右侧技术证据布局、独立滚动与响应式样式。
- `review/research.mjs`、`musicxml-live.mjs`、`score-analysis-model.mjs`：单一数据提供者、视图模型及协调。
- `review/structural-hud.mjs`：独立摘要槽位、并列解释、来源及按需证据导航。
- `review/musicxml-evidence.mjs`：当前窗口、源音符点击、声部／奏法查阅、仅翻页、条件性级数提示。
- `review/analysis.mjs`、`app.mjs`：技术证据标签与返回当前谱页；沿用媒体控制及原校正接口。
- `backend/musicxml_analysis/hud.py`、`analysis/hud/`：绑定原快照的小型适配／核查层，播放阶段仅标准库。
- `scripts/serve_review.py`：复用现有API，提供紧凑实时事实和按需小节证据；HTTP导入白名单包含新视图模型。
- `tests/test_unified_hud.py`、`test_score_analysis_model.mjs`：四组内容、等音／打击乐、更新周期及DOM保护测试。
- `tests/test_structural_hud.mjs`、`test_engine_hud.mjs`、`test_musicxml_live.mjs`、`test_musicxml_reader.mjs`、`test_musicxml_live.py`、`research-dom.mjs`：适配单一入口、候选并列、数据提供者、陈旧响应和实际模块依赖图。
- `scripts/check_research_app.mjs`、`check_ravel_video_app.mjs`、`check_unified_hud_app.mjs`：实际HTTP及模块联调。
- `README.md`、`AGENTS.md`、`docs/WORK_SUMMARY.md`、本报告与 `output/research/hud-integration/acceptance.json`。

以上文件中部分已有视频版未提交改动；本轮在其基础上融合，未覆盖相关作品数据。`docs/design/musicxml-hud-integration.md` 原任务书保持原样。

## 实际运行的验证

处理环境使用synctoolbox；播放环境使用原`.venv`，未为播放安装music21或mido。

```powershell
# synctoolbox 环境的 Python
python -m unittest discover -s tests -v

# 最小播放环境
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_unified_hud.py -v

node --test --test-isolation=none tests/test_video_playback.mjs tests/test_score_follow.mjs tests/test_analysis_playback.mjs tests/test_movements.mjs tests/test_measure_numbers.mjs tests/test_structural_hud.mjs tests/test_engine_hud.mjs tests/test_musicxml_live.mjs tests/test_musicxml_reader.mjs tests/test_hermeneutic_navigation.mjs tests/test_music_coverage.mjs tests/test_score_analysis_model.mjs

$env:ARIADNE_REVIEW_URL='http://127.0.0.1:8765'
node scripts/check_unified_hud_app.mjs
git diff --check
```

结果：

- Python165项：163通过、2跳过（M4A保持悬置）。包含真实HTTP的模块导入图、保存校正的隔离夹具及原媒体功能测试。
- 前端46项：全部通过。
- 最小播放环境新增7项：全部通过。
- 实际HTTP＋模拟DOM／媒体联调：通过。四个主入口、无第二套实时面板、四组内容的细时点、音符ID→原始底稿、独立m.34/PDF11、返回播放谱页、文章选择／标题及213的非零scrollTop保持、视频时钟／播放控制连接、旧曲目清理均检查。
- 实际HTTP依赖图包含`score-analysis-model.mjs`；不是仅依赖本地文件导入。当前视频实时数据响应约15.25MB，源音符明细按需读取，没有初始加载全量47,907条事件。该次本机响应约0.68秒，只是一次观测，不作性能保证。
- 112份受保护文件的前后SHA-256全部一致，覆盖原音频／视频同步、几何、原研究正文／索引、人工校正（存在者）、XML／直接读谱／旧引擎冻结数据。清单见机器记录。
- `git diff --check`通过。

## 未运行与仍未完成

浏览器控制工具本轮实际返回“Local browser use is disabled in Work settings”。没有改变设置，也没有改用其他浏览器自动化绕过。因此**新版桌面／窄屏真实布局、HUD实际像素高度、真实解码实播、音画与谱面试听均未运行**；没有新版浏览器截图。历史截图不作此次布局证明。模拟DOM／媒体通过仅说明模块连接及状态行为成立。

全曲背景和声／和弦外音、精细对位与隐伏声部、最终曲式裁定、逐音录音校准，以及人类或专家签核仍未完成。背景未知保持待分析，职责启发保持候选，竞争模型继续并列。本轮不将这些未完成项隐藏在“界面整合完成”的说法中。

播放器服务在本地8765运行。刷新 `/?track=ravel-left-hand-video` 或原音频版即可加载新版界面；后续浏览器可用时，需重点检查宽屏／窄屏总谱面积、技术侧栏滚动与实际播放。代码和自动／模块检查已完成，本轮没有提交或推送GitHub。

## 后续显示空间调整（2026-10-26）

用户认可四维组织形式，并要求给技术分析更多空间。本次将HUD默认高度调整为约240–360 CSS像素，允许拖动右下角继续调整；标题和四个入口保留，各卡片独立滚动。移除两行／一行文本截断和活跃分部前四项限制，完整列出和弦转位、并列层读法、全部活跃分部及进入退出；曲式补充已有段落范围和两个候选模型的全文说明。仍使用原数据，不新增音乐理论结论。

本次仅修改前端呈现、相应文档和完整摘要的组件检查；前端47项全部通过，实际HTTP＋模拟DOM／媒体联调亦通过。112份受保护文件指纹仍一致。浏览器控制再次返回Work设置禁用，因此未测真实像素、拖动手感及新版实际布局；未将这些项目写成通过。原同步、文章、校正和已冻结的分析快照不改动。
