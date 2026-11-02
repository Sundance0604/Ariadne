# 普三第一、第三乐章瀑布流复现资料

这里保存两次终版制作的**代码、最终逐音对齐、QA、视觉时间线与选定素材**。方法与局限见 [协奏曲瀑布流工作流](../../docs/workflows/concerto-waterfall.md)，可调用的代理 skill 在 [`../../skills/concerto-waterfall/SKILL.md`](../../skills/concerto-waterfall/SKILL.md)。两个 4K 成片、原录音和原 MusicXML 不上传仓库。

## 本地准备

用 Python 3.12 安装 `requirements-alignment.txt`，安装 Node 及渲染器 `../prokofiev2-waterfall/gpu-vfx-flow/pnpm-lock.yaml` 对应的依赖，执行该目录的 `pnpm run build`，并准备 FFmpeg。分析钢琴还需 BS-Roformer-SW 模型、分离器和 Transkun；两者可放在独立环境。模型和虚拟环境不要放入 Git。原始输入在别的目录时设置绝对路径：

```sh
export PROK3_SCORE_PATH=/absolute/path/to/movement1.mxl
export PROK3_AUDIO_PATH=/absolute/path/to/movement1.mp3
export PROK3_M3_SCORE_PATH=/absolute/path/to/full-score.mxl
export PROK3_M3_AUDIO_PATH=/absolute/path/to/movement3.wav
export PROK3_FFMPEG=/absolute/path/to/ffmpeg
export PROK3_NODE=/absolute/path/to/node
```

每部最终 JSON 都保存输入 SHA-256。若换版本，不要绕过指纹校验或复用旧音高证据缓存；在单独工作目录重建并重新试听。仓库中的 JSON 把媒体路径写为 `inputs/score.mxl`、`inputs/audio.mp3`／`inputs/audio.wav`，实际使用时以上述环境变量指向自己持有的原文件。第一乐章复现同一演出需与保存的哈希相同；第三乐章重算新源时先在独立副本中生成缓存。

## 第一乐章

在 `movement1/` 中，已有 `prokofiev3-full-alignment.json` 和 `prokofiev3-full-render.timeline.json` 可供只改视效或重导。`run_full_alignment.py` 是完整对齐入口：粗时钟、重叠片段钢琴分离／转写、管弦分声部证据、主奏分类、音尾、QA。传入 `--model-dir`、`--separator`、`--transkun` 后运行；读 [`movement1/prepare_preview.py`](movement1/prepare_preview.py) 的输入指纹，不接受另一版本。已审核的开头 180 秒时间线和局部音符修正也保存在该目录。

```sh
cd tools/prokofiev3-waterfall/movement1
python run_full_alignment.py --model-dir /path/to/model \
  --separator /path/to/mlx-audio-separator --transkun /path/to/transkun
python build_full_render.py
python prepare_full_chunks.py
python render_full.py
```

`patch_full_visuals.py` 用于沿用旧片未修改的 20 秒片段，仅在已核对时间线与原片签名后局部替换。渲染输出到此目录，属于本机视频，不提交 Git。

## 第三乐章

在 `movement3/` 中，`alignment-performance-reviewed.json` 是终版对齐，`alignment-performance-reviewed-qa.json` 记录最后一次管弦频谱入口和钢琴分离修正。完整流程为 `parse_score.py` → `sync_score.py` → `extract_orchestra.py`／`extract_piano.py` → `align_notes.py` → `refine_alignment.py` → `performance_refinement.py` → `build_render.py` → `prepare_chunks.py` → `render_full.py`。`run_pipeline.py` 封装了渲染前的步骤，不会自动启动耗时的 4K 导出。

```sh
cd tools/prokofiev3-waterfall/movement3
PROK3_M3_MODEL_DIR=/path/to/model \
PROK3_M3_SEPARATOR=/path/to/mlx-audio-separator \
PROK3_M3_TRANSKUN=/path/to/transkun \
python run_pipeline.py
python render_full.py
```

仅改画面时先设置原文件路径，再运行 `python run_pipeline.py --timeline-only`。分离器的原始输出放入系统临时目录，正常结束后移除；压缩 MIDI 与频谱证据在工作目录缓存以便续跑。当前示例采用 MLX 分离器，换 Windows 的分离后端需要对 `extract_piano.py` 的调用和结果命名做适配；不能把 `--device` 改成 CUDA 就认为 MLX 已能在 Windows 运行。

## 完成判据与清理

对齐 QA、抽样试听、角色交接和不合理重叠检查完成后再渲染。成片实际生成后检查时长、4K／60 帧、音轨及修改段接缝；然后清理 `render-parts/*.mp4`、临时 WAV、预览视频和废弃静帧。保留最终对齐 JSON、源指纹、审校选择、代码、选定背景资产和终版视频。本仓库的发布检查禁止把视频或单个超过 100 MiB 的文件暂存上传。
