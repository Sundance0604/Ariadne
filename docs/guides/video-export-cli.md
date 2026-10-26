# 事件驱动导聆视频导出

此入口生成独立 MP4 和可编辑资源包，不改变播放器布局、原 MP4、原对齐或 XML 快照。视频始终为底层；文字来自一个 ASS 轨道，烧录后普通播放器不需要外部字体或字幕。完整 PDF 页面作为固定视窗中的图层，动态高亮和播放线单独合成。

## 安装与依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-export.txt
```

还需 Node.js 执行已有原生 JS 模块，以及支持 libass/libx264 的 FFmpeg。FFmpeg 可通过 `FFMPEG_BINARY` 指定；也识别 PATH、现有 `.tools/media-runtime/` 和 imageio-ffmpeg。`FFPROBE_BINARY` 可选：没有 ffprobe 时，使用 FFmpeg 实际解码的 showinfo 时间戳，不按固定 25 FPS 推算。导出不需要 React、Remotion、浏览器录屏或 Playwright。播放依赖不增加。

## 最小样片

样片采用已存在的 `ravel-left-hand-video`，原视频 0–95 秒：音乐在 27.5 秒进入，用户已确认；片头最晚 24.5 秒结束，最后三秒只有原演奏画面。59–69 秒显示演奏中的诠释；乐谱内部状态继续推进，69 秒恢复当前谱页。谱页切换约在 45.10、81.12 秒。

片头清空点按实际源帧向前对齐。本素材在 24.5 秒之前的最后一个呈现帧是 24.48 秒，因此 ASS 于 24.48 秒结束；不能让 24.48 秒仍有字的画面持续到 24.52 秒才消失。验证同时检查实际帧和 ASS 结束时间。

样片字幕只覆盖选取的观察与导聆。审核范围是代理核对源谱研究、XML 活动记录和现有正文后的短版，不是对全曲的发布批准，也不填写人类或专家签名。

```powershell
# 配置和字幕已保存在 works/ravel-left-hand-video/video-export/。
# 仅首次生成示例输入时运行；该命令拒绝覆盖已有审核稿：
.\.venv\Scripts\python.exe scripts/video_export/build_ravel_export_sample.py

.\.venv\Scripts\python.exe scripts/video_export/export_video.py prepare --track ravel-left-hand-video --profile works/ravel-left-hand-video/video-export/sample-profile.json --annotations works/ravel-left-hand-video/video-export/sample-captions.json --output output/video-export/ravel-demo
.\.venv\Scripts\python.exe scripts/video_export/export_video.py all --package output/video-export/ravel-demo
```

`prepare` 拒绝覆盖已有包，复制本地原演出视频和 PDF，读取原播放器的实际 `/api/project`，保留其 XML→PDF 运行时适配、人工校正与文件指纹。临时 HTTP 服务仅监听回环地址，结束后关闭，不上传任何媒体。

可按阶段运行 `ass`、`score`、`render`、`verify`。`all` 依次执行这四步。初版后端支持一个连续原视频区间，可导出整部连续演出；暂不支持拼接多个区间，避免原 AAC 在剪切处的预滚和时间偏移被静默带入成片。

## 包内文件

```text
performance.mp4                 # 原视频的独立副本
guided-performance.mp4          # 烧录成片
analysis.ass                    # 所有黄色分析字幕，一个轨道
annotations.json               # 审核后的文字、时间、证据与审核绑定
alignment.json                  # 原演奏时间映射
project.json                    # 原网页实际返回的数据快照
export-config.json              # 固定布局、字体、黄色、音乐入口、输出区间
export-manifest.json            # 素材来源、相对路径、时间轴及输入指纹
review-report.json              # 排除条目、同步问题、输出检查
evidence/                      # 审核所用证据的本地快照
score/
  source.pdf                   # 原 PDF
  page-001.png                 # 完整 PDF 页缓存
  view-0000.png                # 固定尺寸视窗缓存
  blank.png                    # 全透明隐藏状态
  pages.ffconcat               # 页面、隐藏与恢复事件
  graphics.ass                 # 无文字的高亮与播放线矢量
  render-input.json
  plan.json
  renderer/                    # 实际使用的原生 JS 模块快照
source-frame-timestamps.json    # 原视频实际呈现时间戳与时值
```

包内 PDF 和缓存仅用于本机导出；不要据此扩大素材发布授权。整个 `output/video-export/` 被 Git 忽略。视频不推送 GitHub。

## 固定布局

1920×1080 样片使用黄色 `#FFDF42`、Microsoft YaHei，常规字号 32。各槽位在 `export-config.json` 中独立设置 `x/y/w/h/font_size`：和声左上，配器右上，左下三个固定槽位依次为对位、曲式、导聆，右侧完整乐谱，底部中央诠释。配器预留于谱面上方。

ASS 使用明确 `\pos`、独立样式，Outline=0、Shadow=0，无背景块。常规更新没有动画，只有片头淡入淡出。过长文本报错，要求提供重新审核的简版，不通过缩小谱面或移动其他槽位解决。

## 审核与修改文字

候选文字必须有明确的发布审核记录、源文件指纹和内容绑定。绑定覆盖 ID、槽位、文字、起止时间、片头／演奏阶段和定位精度。研究稿的 `finished_prose`、XML 解析成功、代理功能验收等不会自动成为字幕发布批准。禁止内容整条排除，保留原因；片段截取后阅读时间不足也整条隐藏。

可以修改包内 `annotations.json` 的文字。完成内容核对后，用实际审核者和实际核对范围记录本次修改，再生成 ASS：

```powershell
.\.venv\Scripts\python.exe scripts/video_export/export_video.py review-caption --package output/video-export/ravel-demo --id opening-guide --reviewer "实际审核者" --scope "本次实际核对范围"
.\.venv\Scripts\python.exe scripts/video_export/export_video.py ass --package output/video-export/ravel-demo
.\.venv\Scripts\python.exe scripts/video_export/export_video.py render --package output/video-export/ravel-demo
.\.venv\Scripts\python.exe scripts/video_export/export_video.py verify --package output/video-export/ravel-demo
```

也可用字幕编辑器独立修改 `analysis.ass` 的文字，另存为 `edited.ass`，然后导入已完成审核的文字：

```powershell
.\.venv\Scripts\python.exe scripts/video_export/export_video.py import-ass-text --package output/video-export/ravel-demo --source edited.ass --reviewer "实际审核者" --scope "本次实际核对范围"
```

此命令保持样式、坐标和时间不变，拒绝新增覆盖指令或占位文字。改动时间或事件数量请编辑 annotations 并复核，再运行 `score`。只改文字不需要重新 OMR、提取特征、DTW 或渲染 PDF。审核命令记录编辑者声明的范围，不自动代填人类或专家签名。

输入变化后旧成片不能继续通过验证；需重新合成。资源包中的证据和 JS 快照亦绑定指纹。

## 复用与时间轴

- `review/score-follow.mjs`：沿用原区域准备与区域选择。
- `review/playhead.mjs`：沿用原时间反投影、共享区域和播放线。
- `review/score-display.mjs`：从网页提取的相同矩形百分比、参考段索引与滚动显示计算；网页和导出共同调用。
- `/api/project`：沿用播放器已生效的 PDF 版本、XML 区域与人工校正。
- `scripts/pdf_render.py`：沿用现有 PDFium 完整页面渲染器。

`review/video-export.mjs` 提供确定性的 `createExportRenderer(input).renderAt(outputTime)`。输出时间为成片时间；原视频时间为源区间起点加输出时间；音乐时间为原视频时间减已确认音乐入口。随机跳转或逆序调用不改变结果。片头和诠释只改变可见性，不停止内部时间推进。

静态页面只在页码、缩放或滚动状态变化时产生新缓存。播放线在实际 DTW 时间映射的折点计算端点，由 ASS `\move` 表达连续运动。没有引入新的小节定位算法，也没有把页数或小节数均分成时间。

低置信度位置保留完整页面，隐藏该处高亮与播放线并写入报告；异常整页框不显示。页码意外回退会阻止合成。完整页面默认按视窗等比容纳；共享滚动逻辑在配置放大后继续可用。

## 验证和性能

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_video_export tests.test_video_export_media -v
node --test --test-isolation=none tests/test_video_export.mjs tests/test_score_follow.mjs tests/test_music_coverage.mjs tests/test_video_playback.mjs
.\.venv\Scripts\python.exe scripts/video_export/benchmark_video_export.py --package output/video-export/ravel-demo --frames 50
```

自动验证包括完整解码、源视频实际帧时间、AAC 可听区间的数据包内容、实际 ASS 对审核文本的绑定、禁词、片头三秒留白、隐藏图层透明性和字体缺字。真实 FFmpeg 测试使用 15/30 FPS 变化的输入及非零原片起点，覆盖末帧和 AAC 预滚处理。没有用 `-r 25` 或固定帧率滤镜重建原时间。

性能对比在真实呈现时间抽样，分别每帧重画 PDF 和复用页面缓存；记录独立进程峰值内存及帧像素一致性。它是谱面绘制模型测试，不宣称为完整 Chromium 与长篇 FFmpeg 的端到端对比。对最终 MP4 仍须检查实际抽帧；代理视觉核查、人工完整观看和音乐专家逐音审定分别记录。
