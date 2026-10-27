# 拉威尔完整版视频

完整版沿用用户确认的95秒样片布局及保存的字号，使用原录像0—1197.85秒，包括演出前镜头和结尾演出画面。音乐入口仍为27.5秒，片头最迟24.48秒清空。已存同步覆盖27.5—1162.5秒，其外保留演奏画面，不外推分析或播放线。

输出在 `output/video-export/ravel-full-001/`。最终MP4在本次 `edits-XXX/导聆视频.mp4`，根目录的 `local/video-export/latest-video.txt` 记录最近成功生成的位置。`export-manifest.json` 记录本次成片的相对路径。

完成后双击项目根目录 **编辑视频字幕.bat**，选择 **拉威尔左手钢协完整版**，可修改整曲文字、出现时间、位置、字体与滚动速度，并另存新视频。完整版与95秒样片在项目选择窗口分开，文稿仍使用 `captions-editable.json`；修改后须点击“保存并生成新视频”。

目录还保存 `performance.mp4`、`analysis.ass`、`annotations.json`、`alignment.json`、`export-config-kaiti.json`、`score/`、`review-report.json`。原网页完整文字另保存在 `web-captions.json`，排除的占位文字、无信息提示及不能阅读的片段有原因记录。用户修改之后的新一轮ASS、正文快照和渲染结果保存在新建的 `edits-XXX/` 内。

乐谱使用原JavaScript模块生成页面、高亮与播放线，100页完整谱面各缓存一次。诠释使用原有成稿中的段落，在已定位的相关谱页范围内安排；期间乐谱隐藏，结束后按持续推进的同步状态恢复。新增诠释前留出导聆阅读时间，已显示的同一段导聆不会在诠释结束后重新起滚。

生成入口为：

```powershell
.\.venv\Scripts\python.exe scripts/video_export/build_ravel_full_video.py
```

每次默认创建新的完整版目录。已有目录发生合成中断时，可用 `--output output/video-export/ravel-full-001` 复用已缓存的100页谱面和源视频实际时间戳，另存新一轮视频。日常修改文字请使用编辑窗口，以保留整曲编辑文稿。

生成时不重新运行DTW、MusicXML分析、识谱、源文件指纹或测试套件。正式合成使用原视频实际帧时间戳与原AAC音轨，成片烧录黄色楷体字幕，可在普通播放器中直接观看。审核记录区分自动导出检查、已有谱面证据和人类／专家签核。
