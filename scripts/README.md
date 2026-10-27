# 工具脚本索引

所有示例命令从项目根目录执行。视频制作脚本已集中到 `scripts/video_export/`；原 `scripts/export_video.py` 保留为兼容入口。

| 工作 | 主要入口 |
|---|---|
| 启动播放器 | `start.py`、`scripts/launch_local.py`、`scripts/serve_review.py` |
| 媒体准备与对齐 | `prepare_video.py`、`align_recording.py`、`build_ravel_video.py`、`build_mahler4_video.py` |
| PDF几何与编号 | `map_pdf.py`、`map_lark_pdf.py`、`map_mahler4_pdf.py`、`number_mahler4_pdf.py` |
| 分析与研究资料 | `analysis_data.py`、`research_data.py`、`build_ravel_module_development.py`、`export_musicxml_research.py` |
| 鹅妈妈谱面研究 | `build_mother_goose_research.py`、`compare_mother_goose_sources.py`、`render_mother_goose_research.py`；独立于录音时钟 |
| 鹅妈妈可选GNN试验 | `probe_chordgnn.py`检查输入，`probe_analysisgnn.py`运行后继候选，`summarize_chordgnn_probe.py`导出对照；见[实测及环境限制](../reports/mother-goose-chordgnn-20261027.md)，不激活播放器 |
| 普罗第二钢协分析 | `build_prokofiev2_research.py`建立旧方法的局部符号证据；`package_prokofiev2_analysis.py`整理正文分段与出处；不生成录音同步 |
| 普罗第二钢协网页同步 | `prokofiev2_sync.py`建立同视频音轨候选及原扫描谱几何；`build_prokofiev2_playback.py`映射并发布独立网页快照；`check_prokofiev2_app.mjs`检查实际HTTP模块与模拟媒体联调；见[同步报告](../reports/prokofiev2-sync-20261027.md) |
| 普罗第二钢协实时与音流样片 | `build_prokofiev2_live.py`接入原DTW下的逐时点音集及配器；`video_export/build_prokofiev2_flow_sample.py`生成独立45秒样片，使用`review/harmonic-flow.mjs`共享绘图计划，不插入PDF、不修改现有字幕包 |
| 声部配器可视化与整体大小 | `video_export/edit_video_captions.py --panels`为同一批处理编辑器的设置入口；`export_visual_panels_plan.mjs`复用`harmonic-flow.mjs`、`orchestration-activity.mjs`生成两面板共享时钟绘图计划；[使用指南](../docs/guides/visual-panels.md) |
| 普二完整版准备 | `video_export/prepare_prokofiev2_full.py editorial`生成初始字幕；`package`准备原PDF与动态层，均拒绝覆盖既有文稿／包且不编码视频。后续通过原编辑器`--project prokofiev2-full`编辑与生成；[使用指南](../docs/guides/prokofiev2-full-video.md) |
| 普二十段空白的接续分析 | `video_export/fill_prokofiev2_gaps.py`复用`gap-fill-plan.json`的谱面入口与完整文案，检查阅读时间、聆听间隔和覆盖；本次已应用，脚本拒绝重复覆盖后续用户文稿，不编码视频。日常仍用原字幕编辑器；[报告](../reports/prokofiev2-gap-fill-20261027.md) |
| 鹅妈妈完整芭蕾同步与视频 | `mother_goose_video.py`、`build_mother_goose_playback.py`、`video_export/build_mother_goose_export.py`；独立指纹与七章节连续视频 |
| 字幕编辑、位置、字体与滚动 | 唯一编辑器 `video_export/edit_video_captions.py`；根目录 `编辑视频字幕.bat` 选择项目，命令行用 `--project mother-goose`、`--project ravel-full` 或 `--project ravel-sample` |
| 视频与资源包 | `video_export/export_video.py`、`video_export/build_ravel_full_video.py` |
| 编辑后成片验证 | `video_export/verify_edited_video.py --package 资源包目录 --revision 本轮edits目录` |
| 字幕来源、同步及润色 | `video_export/export_web_captions.mjs`、`video_export/sync_ravel_module_captions.py`、`video_export/polish_ravel_caption_text.py` |
| 乐谱视频计划 | `video_export/export_score_plan.mjs`，调用原播放器模块 |
| 性能试验 | `video_export/benchmark_video_export.py`，仅在需要比较时运行 |
| 发布检查 | `check_publish.py`，只检查索引，不暂存或推送 |

`video_export/build_ravel_export_sample.py`、`video_export/revise_ravel_video_text.py`记录既有样片制作步骤，日常改字幕请使用编辑器。不要为了改几个字重新导入全部网页研究或重算录音。

`check_*`和`validate_*`是检查脚本，不是新的分析来源。OMR处理入口在 `backend/score_processing/`；主要XML分析入口在 `backend/musicxml_analysis/`。详见[分析流程](../docs/workflows/analysis-writing.md)及[视频流程](../docs/workflows/video-production.md)。
