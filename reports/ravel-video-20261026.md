# 拉威尔左手协奏曲：独立视频版（2026-10-26）

新增曲目 `ravel-left-hand-video`，与现有齐默尔曼／布列兹／LSO音频版并存。入口：`http://127.0.0.1:8765/?track=ravel-left-hand-video`。

## 输入与阵容

- 视频：用户本地文件，412,017,810字节，约1197.85秒；H.264画面、AAC立体声音轨。精细媒体信息来自FFmpeg诊断回退，本机未配置ffprobe。
- 视频SHA-256：`f73028a0e26be3347fa11875a74df8f2ee12919bbb2c45fcd11d22db00b0e3d8`。
- 视频内嵌说明：钢琴Pierre-Laurent Aimard，指挥Marko Letonja，Strasbourg Philharmonic Orchestra；演出日期未独立核验。不会沿用齐默尔曼版阵容。
- PDF、MIDI及MusicXML继续采用原文件。视频与齐默尔曼录音为不同演出，不启用双媒体同次演出映射。

## 同步与首尾

先保存完整视频的DTW草稿 `alignment.raw.json`。检查视频0、8、16、24、32秒及结束段画面，并检查开头低频持续音与结尾频谱，确认全文件包含片头／谢幕掌声；全文件端点约束不能视作音乐入口证据。

当前采用27.5–1162.5秒的音乐分析窗口，截取视频自身解码音轨后，以同一MIDI重新运行chroma＋DLNCO／MrMsDTW。此窗口为代理画面与频谱估计，未代填人类试听锚点。图像依据另见 `output/research/ravel-video/opening-spectrum.png` 与 `ending-spectrum.png`。

有效结果为 `alignment.music.raw.json`；正式 `alignment.json` 将DTW的音轨秒数加27.5秒，投影回原视频时钟，没有拉伸录音、均分小节或使用原唱片时间。原始路径、源WAV指纹、时间偏移和草稿指纹均保留。全视频及解码缓存留在本机。

| XML对应参考小节 | 视频候选起点（秒） |
|---|---:|
| 1 | 27.500 |
| 33 | 185.140 |
| 34 | 198.248 |
| 64 | 334.468 |
| 126 | 555.492 |
| 251 | 674.888 |
| 480 | 942.085 |
| 520 | 1117.632 |
| 535 | 1160.530 |

所有时间仍是估计位置。535个参考小节与XML起点一致，534个完整时值一致，最后0.4个XML四分音符继续不外推。共享录音投影保留原先1046.5秒的保守MIDI端点；本次MIDI解析总时长约1046.5435秒的差异不用于扩大XML覆盖。

`score_time_coverage` 以外仍可观看视频，关闭当前和声／活跃分部、播放线及高亮。不会把片头掌声当作第一小节，或让最终和弦在谢幕期间一直保持激活。

## 复用与保护

曲库通过 `score_source: ravel-left-hand` 引用同版谱面研究。原总谱与原几何继续使用，视频目录保留一份相同的几何数据；研究文章、文献、直接读谱窗口、XML音符和并列解释快照直接从原来源读取，不复制第二套正文或重新生成音符。

视频专用的 `musicxml-recording-projection.json` 绑定本视频指纹、独立alignment与原XML快照。原MIDI仅桥接结构时钟，不恢复MIDI–PDF逐音匹配的前置要求。若alignment、媒体或XML快照变更，旧投影拒绝载入。

`works/ravel-left-hand-video/reports/source-preservation.json` 保存原音频版alignment、几何、阵容、project、研究索引和XML指针的前后指纹，全部一致。原版功能、数据与文章不被覆盖。

## 检查范围

- Python完整测试158项：156通过、2跳过（M4A保持悬置）。新增测试覆盖共享来源与PDF／MIDI／作品错配拒绝、独立视频时钟、原文件保护、文章复用及实际视频字节范围响应。后续补充的原始时钟偏移／陈旧投影断言另在同7项视频测试中通过。
- 前端38项全部通过，包括覆盖区间外不激活谱面状态。
- `ARIADNE_REVIEW_URL=http://127.0.0.1:8765 node scripts/check_ravel_video_app.mjs`：实际模块＋实际HTTP，模拟DOM与媒体元素；视频音源选择、播放／暂停／变速控制连接、跳转、34小节定位第11页、文章滚动保留、独立翻页、谢幕清理、切回原音频版均通过。媒体时钟由测试夹具推进，不冒充真实解码实播。
- 本轮应用内浏览器控制返回“Local browser use is disabled in Work settings”，未改变该设置，也未声称完成真实浏览器实播、主观试听或逐音专家校对。实际视频解码、音画与谱面对应的试听仍待用户或后续可用浏览器核查。
- 视频受现有忽略规则保护，不提交Git；没有上传媒体。预计算播放仍只需最小播放依赖。

## 重建入口

先使用 `scripts/prepare_video.py` 提取本视频音轨，将已核查的27.5–1162.5秒区间保存为独立WAV，再使用 `scripts/align_recording.py --audio <区间WAV> --midi <原MIDI> --output <新目录>/alignment.music.raw.json`。

封装命令：

```powershell
python scripts/build_ravel_video.py --raw works/ravel-left-hand-video/alignment.music.raw.json --music-start 27.5 --music-end 1162.5
```

已生成的视频版受保护，命令不会覆盖。本素材重算时使用新目录、新的 `--track-id` 及复核记录；此封装器的阵容适配仅限当前艾马尔视频，更换演出需另行适配阵容及输入，不能改hash或直接复用本版时间。克隆仓库后恢复同一视频，按 `media-sync.json` 的路径、字节数和SHA-256核对；不存在视频时，一键启动选择其他材料齐全的曲目。
