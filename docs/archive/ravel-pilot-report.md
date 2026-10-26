# 拉威尔双阅读路径 MVP 实测

> 本文保存首轮MVP的8事件／2文章及当时的验证快照。后续已扩充为35事件、5文章和8份结构化和声记录；现状以[拉威尔谱面技术研究更新](../../reports/ravel-score-research-update.md)为准，以下历史数量不代表当前数据。

日期：2026-10-25。任务依据：`ARIADNE_CODEX_RESEARCH_PARADIGM.md`。本轮只实施本地研究呈现、数据校验和测试；未重跑OMR或DTW，未上传、推送或部署媒体。

## 1. 实际完成

- 中间谱面区新增可折叠的技术仪表：和声、对位、曲式、配器分别更新。缺数据清空当前维度，不沿用上一和弦；页级条目标明“本页／本段背景”“仅页级定位”“待复核”。
- 点击事件查看详解、出处、四项核查状态，并可打开关联文章。多条竞争观点能并列呈现，相关演示数据仅在测试夹具中。
- 右侧新增“诠释研究”：默认固定长文及其独立滚动位置；可选自动跟随只切换相关专题。跨页或非连续证据的按钮可以打开相关PDF。当前全部生产研究范围仅为页级，因此不会自动seek到未经核查的音头。
- 新增只读 `/api/research`，校验作品、版次、实际PDF指纹、条目结构、来源、正文路径和演奏专属绑定。无研究文件返回空结果；错误不破坏原播放器。
- 保留原短导聆、录音信息、文献、音视频控制、A/B循环、谱页、编号与三种人工校正流程。新增层不写这些旧数据。

## 2. 修改／新增文件及职责

| 文件 | 职责 |
| --- | --- |
| `scripts/research_data.py` | 研究数据验证、安全Markdown渲染、来源复用和指纹绑定 |
| `scripts/serve_review.py` | 研究API及5个新原生模块的白名单静态路由 |
| `review/research-model.mjs` | 各维度索引、区间匹配、非连续范围、保守导航纯函数 |
| `review/structural-hud.mjs` | 仪表、独立维度DOM更新、事件详情与文章链接 |
| `review/hermeneutics.mjs` | 固定文章、滚动保持、目录、可选跟随和谱面按钮 |
| `review/research.mjs`、`research-ui.mjs` | 版本化异步加载、切曲隔离、共享安全呈现 |
| `review/app.mjs`、`analysis.mjs`、`index.html` | 统一媒体上下文接线、第四标签、可折叠和窄屏布局 |
| `analysis/structural-events.json`、`hermeneutic-essays.json`、`sources.json` | 8条事件、2篇文章索引及目标谱来源 |
| `analysis/essays/ravel-tonal-emergence.md`、`ravel-timbre-perspectives.md` | 独立的诠释正文 |
| `tests/test_research_data.py` | 真实样板、结构、路径、来源、指纹、HTTP和认识论边界 |
| `tests/test_structural_hud.mjs`、`test_hermeneutic_navigation.mjs`、`research-dom.mjs` | 区间、冲突、文章保持、导航及异步隔离夹具 |
| `scripts/check_research_app.mjs` | 实际模块＋HTTP＋内存DOM联调，复用原马四检查 |
| `docs/design/research-paradigm.md` | 已实现的数据规范与接口 |
| `README.md`、`docs/WORK_SUMMARY.md` | 新功能、入口和本轮限制 |
| `reports/research-*.log/json`、`output/research/` | 运行日志、结果与真实浏览器截图 |

原任务书保留，未修改其要求。没有新增播放依赖或框架。

## 3. 拉威尔试验实况

当前定位版次：`ravel-reengraving-100p`，PDF SHA-256为 `67aa60cc89160ea7e475fd7fa45352ec6e0c45f6cd3557421d8caafc18531083`。这是用户提供的100页重排谱，不认定其为权威校订版，不与99页扫描谱混用。

| 事件ID | 维度／范围 | 证据与状态 |
| --- | --- | --- |
| `opening-low-strings` | 配器，1页 | 目标谱图像；关键页已查看，非逐音确认 |
| `horn-contrast` | 配器，3页 | 目标谱图像；不直接断言两种轮廓是同一主题 |
| `tonal-perspective` | 和声，1–3页相关背景 | Leong & Korevaar §34–35；作者理论，当前谱本逐音待核查 |
| `single-hand-layers` | 对位，10–14页 | Leong & Korevaar §24–28；单手多层问题，精细声部对应待核查 |
| `opening-cadenza` | 曲式，10–14页 | 当前第10页与原导聆粗范围；论文§29–33仅作功能解释 |
| `allegro-region` | 曲式，33–48页 | 第33页Allegro文字；页级范围不充当严格终止点 |
| `closing-cadenza` | 曲式，91–94页 | 第91页Cadenza文字与原导聆范围 |
| `orchestra-return` | 配器，95页 | 同页前部独奏、后部乐队进入；不是全页恒定编制 |

所有事件的时间状态仍为 `candidate_alignment`。没有生产用逐拍和声、没有“verified”音乐学结论，也没有虚构置信度。

第一篇《调性的逐步确立：从E，经A，至D》关联1–3、10–14、15–23页，区分谱面观察、论文框架与本项目尚未完成的对应。第二篇《同一架钢琴中的不同声音：开头与末段的比较》关联1–3、91–94、95页，支持另一条非连续阅读路径。两篇均为待音乐学审阅的研究正文，编辑成稿不等于论证已由专家核准。

本轮读取 [Leong & Korevaar 2005](https://mtosmt.org/issues/mto.05.11.3/mto.05.11.3.leong_korevaar.html) 的§24–35，重点§29–35；读取 [Beavers 2021](https://mtosmt.org/issues/mto.21.27.1/mto.21.27.1.beavers.html) 与本曲有关的§4.12及§5.1–5.5。没有声称两篇全文、全部谱例与媒体均已校核，也未把论文对其他录音或G大调协奏曲的说明移植到本录音。

目标PDF本轮生成并查看1、3、10、33、91、95页联系图；未宣称逐页逐音校勘。第15–23页等粗范围沿用原导聆，明确保留定位限制。

## 4. 测试矩阵与实际命令

基线：Python 76项中74通过、2跳过；前端17项通过。最终完整结果与实际执行日志见 `reports/research-validation.json`。使用Conda `synctoolbox` 的Python执行全量测试，省略机器相关的解释器绝对路径后命令如下：

```powershell
python -m unittest discover -s tests -v
node --test --test-isolation=none tests/test_structural_hud.mjs tests/test_hermeneutic_navigation.mjs tests/test_analysis_playback.mjs tests/test_score_follow.mjs tests/test_video_playback.mjs tests/test_movements.mjs tests/test_measure_numbers.mjs
python start.py --port 8766
node scripts/check_research_app.mjs
```

前端环境Node v24.18.0。内存DOM联调与真实浏览器是两组独立证据；编号保存的UI模拟不写真实校正，实际写入仍由隔离Python夹具验证。

| 编号 | 状态 | 本轮证据及范围 |
| --- | --- | --- |
| T01 | PASS | 真实浏览器播放拉威尔MP3，观察时间推进、谱页高亮与红线；不是全曲听辨 |
| T02 | PASS | 浏览器seek到1、10、33、91页对应候选；不同维度变化；单测检查未变维度不重建DOM |
| T03 | PASS | 生产页级背景和空状态；夹具另测细段、候选区域与边界 |
| T04 | PASS | 浏览器正文scrollTop=720，跨页seek后仍为720；实际播放跨页未换文；单测检查节点不重建 |
| T05 | PASS | 浏览器开启跟随后91页切到第二篇，关闭后返回开头仍保留第二篇 |
| T06 | PASS | 文章多个谱页按钮只翻页，暂停时录音时间保持0；夹具验证非连续范围和人工校正的严格seek门槛 |
| T07 | PASS | 播放定位33页、手动浏览34页，HUD分别标识两者 |
| T08 | PASS | 浏览器1.2倍速、A/B循环回到52.18秒附近及第3页，文章保持；音视频主时钟另有回归测试 |
| T09 | PASS | 浏览器《云雀高飞》音频、马四本地视频均实际开始播放；研究空状态不串曲，返回拉威尔恢复资料 |
| T10 | PASS | 隔离夹具验证作品、版次、实际PDF内容、演奏绑定与实际音频内容错误；HTTP422；未改真实素材 |
| T11 | PASS | 测试夹具同时显示两个理论观点与争议状态；生产未为演示编造争议 |
| T12 | PASS | 实际窗口1265×712及748×856、移动390×844；研读／观演／专注切换保持研究状态，窄屏技术栏折叠 |
| T13 | PASS | 模拟和声、人工核查状态只在tests夹具，生产仅8条有出处的页级事件 |
| T14 | PASS | 文章、来源与UI保留实际阅读范围；自动测试拒绝将摘要／章节阅读升级为全文核查 |

**NOT_RUN：** 全曲逐音／逐小节人工听辨、专家理论审稿；完整论文及全部谱例/媒体通读；真实双源音画切换（当前曲目不提供合适的双源组合）；移动端各模式与全屏／浮窗的全部排列组合。双源逻辑有自动回归，但不能写成真实双源实播。

## 5. 真实浏览器检查

通过本轮可用的应用内浏览器操作实际界面；不是截图mockup或仅内存DOM。拉威尔从0播放至约90.77秒，随后检查跳转、手动翻页、长文和自动跟随；《云雀高飞》音频开始播放；马四视频readyState=4、paused=false且时间推进，能看到实际视频画面。上述均未被当作音乐内容准确性的证明。

截图：`output/research/ravel-desktop.jpg`、`mobile-score.jpg`、`mobile-essay.jpg`。未另保存或发布马勒视频画面。截图反映有限视口的检查，不替代全部设备验收。

## 6. 保留数据与剩余限制

根目录 `alignment.json`、`measure-map.json`、`analysis/annotations.json`、`metadata/recording.json` 均与本轮开始的SHA-256一致。原15段短导聆、旧版本说明和人工校正没有被新研究初始化覆盖。没有重跑DTW、没有修改535个参考段的音乐学含义。

所有生产事件仍只有页级精度。不同维度已可独立切换，但本轮没有宣称已有真实逐拍事件；更细边界只用隔离夹具验证架构。原谱小节、MIDI候选和PDF区域持续区分，页范围关联仍需校勘。

## 7. 运行与复核

```powershell
python -m pip install -r requirements.txt
python start.py --port 8765
```

打开 `http://127.0.0.1:8765/?track=ravel-left-hand`，选择“诠释研究”，保持默认关闭自动跟随，再播放或跳到第32个MIDI候选附近（本版第10页）。研究页按钮只打开PDF；重新勾选“跟随播放翻页”可恢复自动跟谱。完整测试需要处理依赖，播放不增加依赖。

## 8. 下一步

1. 对少量已选谱例进行专家逐音／声部审阅，记录真实小节及拍位，使部分事件从页级背景进入精确区间。
2. 为这些区域完成独立的录音时间人工校正，再开放可信音频跳转；保留旧候选与审阅记录。
3. 在第二份谱本或第二场录音上验证版次／时间投影隔离；扩展文献阅读范围时同步更新出处状态。
