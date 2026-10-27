# 工具脚本索引

所有示例命令从项目根目录执行。视频制作脚本已集中到 `scripts/video_export/`；原 `scripts/export_video.py` 保留为兼容入口。

| 工作 | 主要入口 |
|---|---|
| 启动播放器 | `start.py`、`scripts/launch_local.py`、`scripts/serve_review.py` |
| 媒体准备与对齐 | `prepare_video.py`、`align_recording.py`、`build_ravel_video.py`、`build_mahler4_video.py` |
| PDF几何与编号 | `map_pdf.py`、`map_lark_pdf.py`、`map_mahler4_pdf.py`、`number_mahler4_pdf.py` |
| 分析与研究资料 | `analysis_data.py`、`research_data.py`、`build_ravel_module_development.py`、`export_musicxml_research.py` |
| 鹅妈妈谱面研究 | `build_mother_goose_research.py`、`compare_mother_goose_sources.py`、`render_mother_goose_research.py`；独立于录音时钟 |
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
