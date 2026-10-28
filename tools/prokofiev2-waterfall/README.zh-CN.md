# 普罗科菲耶夫第二钢琴协奏曲第一乐章：录音对齐与瀑布流

这是李云迪／小泽征尔／柏林爱乐录音的**独立瀑布流项目**。它与 Ariadne 已有的普二导聆、PDF、字幕视频并列，使用不同的录音与时间轴；不要把两套 `alignment.json` 或媒体指纹互换。

## 可复用文件

| 文件 | 用途 |
| --- | --- |
| `run_alignment.py` | 检查录音指纹，调用钢琴分离、Transkun、末段补扫，再生成最终逐音时间轴；已有分离声或 MIDI 可以直接传入，跳过大模型计算。 |
| `align_audio_piano.py` | 核心逐音合并、音尾修正、双手可达性检查；钢琴触键与释放时间来自录音转录，不回退到 XML 时值。 |
| `data/orchestra-reference-v8.timeline.json` | 已对齐的管弦参考轨，同时保存供音高核对的原谱钢琴事件。 |
| `data/aligned-timeline-v9.json` | 最终视频采用的 10,331 条音符事件，可不运行模型直接渲染。 |
| `score-reference/` | MusicXML 解析事件、共享小节时钟、跨小节延音线修复脚本和本次处理结果。 |
| `render-plan.json`、`build_render_plan.py` | 段落色彩、主奏管弦、音符材质、粒子、火焰、日蚀与标题的单一配置及场景编译。 |
| `gpu-vfx-flow/` | PixiJS/WebGL 逐帧渲染器、版本 A 的 88 键琴盘、可调参数、粒子风场、曲线光迹、音符表面和实拍火焰合成。 |
| `render_movement.py` | 4K/60 fps 分段导出、逐段校验、原录音一次性封装；PNG 帧直接送入 FFmpeg，不落盘。 |
| `rerender_full_suffix.py` | 只改末段时验证前段画面相同，再局部导出和无损视频拼接。 |
| `data/final-video.json` | 用户确认的 v21 成片 SHA-256、大小、时长与原始制作指纹。 |

## 本次最终对齐的关键事实

1. 原 MusicXML 先按多数分部的小节长度修复溢出小节、计算实音音高，剔除打击乐／ossia 与延音线续接的重复音头。全局 chroma + 起音 DTW 只负责建立管弦参考时钟，随后局部音高证据和人工复核修正；跨小节延音线另行延长。冻结的结果是 `data/orchestra-reference-v8.timeline.json`。早期使用 XML 时值推算钢琴音尾的方法不属于最终钢琴方法。
2. 混合录音用 **MLX Audio Separator 0.1.20 / BS-Roformer-SW** 分离钢琴，随后用 **Transkun 2.0.1** 转录每个钢琴音的音高、起点和终点。结尾 620–670 秒从原录音另行截取、分离与转录，用同音高和局部谱面核对补回 3 个漏音。模型权重和约 113 MB 的分离 WAV 不在 Git 仓库。
3. `align_audio_piano.py` 用 0.8 秒窗口把识别音与谱面同音高事件关联，用于声部身份和检查，**关联不会移动识别音的音头或音尾**。由此保留演奏者的琶音、左右手错位、rubato 以及实际按键长度。最终钢琴 5,698 音，谱面时间回退为 0。
4. 同一琴键再次触键之前，前一个音的可见终点截到新触键之前 6 ms，并保证至少 35 ms 的可见长度。本曲发生 7 次。然后对同时发声集合检查是否能分为两手、每手至多五键且跨度不超过 18 半音；最终违规为 0。踏板、混响与分离伪影仍会影响模型音尾，所以这一检查是物理合理性约束，不是假称所有释放点经过人工逐音认证。
5. 管弦音继续使用谱面引导的 v8 参考轨。弱伴奏和主奏的视觉角色由分部、音高、谱面小节及人工听辨的段落位置决定；没有把管弦声称为同样精度的音频转录。

## 从已保存的转录结果重建对齐

在仓库根目录执行。安装 Python 3.11+，单独环境安装 `tools/prokofiev2-waterfall/requirements-alignment.txt`。将**同一录音**放到 `local/prokofiev2-waterfall/performance.wav`；脚本校验 SHA-256 `36371069...a99f96b67`。仓库已保存精简的两份转录 MIDI，因此无需再次下载模型即可核对最终对齐：

```sh
python tools/prokofiev2-waterfall/run_alignment.py \
  --audio local/prokofiev2-waterfall/performance.wav \
  --work-dir local/prokofiev2-waterfall/rebuild \
  --full-midi tools/prokofiev2-waterfall/data/movement1-transkun.mid \
  --supplement-midi tools/prokofiev2-waterfall/data/ending-50s-transkun.mid
```

生成 `local/prokofiev2-waterfall/rebuild/aligned-timeline.json` 与 `alignment-qa.json`。用本仓库内的 MIDI 运行时，它们的 `notes` 与已提交最终时间轴逐条相同。Windows 可以执行这一步和后续渲染；若要重新分离钢琴，可在 Mac 上运行 MLX，或在其他机器用同等分离器制作钢琴 WAV，再用 `--piano-stem` 交给 Transkun。另行重新运行模型得到的 MIDI 可能与保存结果有微差，应重新审核而非宣称完全相同。

对齐回归检查：`python -m unittest discover -s tools/prokofiev2-waterfall/alignment_tests`。渲染运动与材质检查：在 `gpu-vfx-flow/` 运行 `node --test tests/*.test.mjs`。

## 从原录音重新运行模型

在 Mac Apple Silicon 上另建 Python 3.12 环境安装 `mlx-audio-separator==0.1.20`，另建环境安装 `transkun==2.0.1` 与本目录的对齐依赖。把 `BS-Roformer-SW.ckpt` 和相应 `BS-Roformer-SW.yaml` 放入本机模型目录。示例：

```sh
python tools/prokofiev2-waterfall/run_alignment.py \
  --audio local/prokofiev2-waterfall/performance.wav \
  --work-dir local/prokofiev2-waterfall/model-run \
  --model-dir local/prokofiev2-waterfall/models \
  --separator mlx-audio-separator --transkun transkun --device mps
```

这一步自动缓存全段钢琴分离声和末 50 秒补扫声；重复运行会复用已完成文件。默认工作目录、模型和录音均在 Git 忽略的 `local/` 下。若模型 CLI 更新，应先核对其 `--help`；保存的 MIDI 可作为稳定复现起点。

## 导出最终样式

准备 Node.js 20+、pnpm、Chrome/Chromium 与 FFmpeg。`gpu-vfx-flow/` 中运行 `pnpm install --frozen-lockfile`。最终样式需要两个本机素材：SeeMusic 黑键图 `assets/seemusic/BlackKeyUp.png` 与 FX Elements 火焰衍生图 `assets/real-fire/flame-smooth-{a,b,c}.png`。仓库不分发它们；各目录的 README 说明来源。其余 Kenney CC0 纹理和美国国家公园管理局日蚀照片随源码提供。

```sh
python tools/prokofiev2-waterfall/render_movement.py \
  --plan tools/prokofiev2-waterfall/render-plan.json \
  --scene opening-title \
  --output-dir local/prokofiev2-waterfall/previews \
  --node node --ffmpeg ffmpeg
```

检查后将 `--scene opening-title` 改为 `--scene full`、输出目录改为本地目标目录即可导出全片。默认 3840×2160、60 fps、片头 5 秒，成片约 11 分 17 秒。可以先用 `--width 1920 --height 1080 --fps 30` 快速检查；最终仍须使用原分辨率和帧率。系统不会自动下载原录音、模型权重或商业素材。

`render-plan.json` 是情绪段落、渐变、突变、主奏声部和尾声特效的可调入口；`gpu-vfx-flow/visual-style.json` 管音符宽度、圆角、表面和光晕，`visual-preset.json` 管全局粒子运动。主音黑白键同为圆角形；背景音保持细形。`gpu-vfx-flow/PARAMETERS.zh-CN.md` 列出细项。Mac 使用 Metal，Windows 采用 Chrome 当前可用的 WebGL 后端。分段导出降低峰值内存与临时磁盘占用；视频编码仍会持续占用 CPU/GPU。

Windows 运行导出前，把 `CHROME_BINARY` 环境变量设为本机 Chrome 或 Chromium 的完整可执行文件路径；macOS 默认查找 `/Applications/Google Chrome.app`。`--node` 与 `--ffmpeg` 可传任意机器上的实际可执行文件路径，不能照搬他人的本机位置。

仅调整尾段日蚀或 `tail_particle_bloom` 时，先复制 `render-plan.json` 并修改新副本，再用 `rerender_full_suffix.py` 指定原 v21 视频和新计划。`--first-changed-segment 21` 表示保留成片前 630 秒；改日蚀渐入时应选更早的分段。脚本核对原视频指纹、计划变更范围和拼接边界；若变更影响前段，它会拒绝局部拼接。原 v21 视频没有依赖已经删除的草稿视频，指纹由 `data/final-video.json` 提供。

## 边界与发布

本目录是**本次录音的可复现作品包**，不是对任意录音或任意 MusicXML 自动精确对齐的保证。更换演出需要重新建立管弦参考时钟与声部选择、分离和转录钢琴，并复核指纹。最终 4K MP4 大约 1.24 GB，留在用户本机；Git 只保存代码、参数、小型对齐结果和指纹，不推送录音、视频、模型、SeeMusic 图或实拍火焰文件。Ariadne 既有的播放器与普二研究视频不受此目录影响。
