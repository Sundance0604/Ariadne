# 瀑布流视觉参数

## 最终 v21 段落参数

全曲参数集中在上级目录 `render-plan.json`。当前 `particle_trail_density_scale=1.65`、`filament_visibility_scale=2.3575`、`filament_min_per_second=0.4025`。安静段落由 `filament_silence_intervals` 关闭光迹，粒子继续存在。尾声 640 秒后由 `tail_particle_bloom` 逐渐增加粒子数量及横向覆盖，并使光迹寿命缩短；日蚀由 `eclipse_fade` 渐入渐出。每段 `blend` 控制普通段落颜色过渡秒数。

键盘轮廓与黑键图片未改。`build_render_plan.py` 把段落材质编译为 `appearance.keyboard_crystal_amount`、`keyboard_metal_amount`、`keyboard_ember_amount` 三个可插值的弱叠层。`background_atmosphere` 控制低对比度暗色空间光，`background_tint` 随段落变色；静帧检查时可用 `appearance_overrides` 单独调节。局部管弦强调由 `build_render_plan.py` 的 `accent_for()` 指定，不改变钢琴颜色。

## 当前确认的音符与光影模板

`visual-style.json` 保存这次确认的音符外形、面层与光影参数。修改它后直接重新渲染静帧或视频，**无需重新打包 JavaScript**。导出记录其 SHA-256；更换模板会使全曲分段缓存失效，避免误用旧画面。要比较另一版，复制此文件并传给 `render_movement.py --style /绝对路径/另一版.json`；单张静帧可设置 `WATERFALL_STYLE_FILE`。

| 分组 | 主要参数 | 效果 |
| --- | --- | --- |
| `geometry` | `piano_white_width`、`piano_black_width`、`piano_corner_radius` | 白键／黑键音符宽度、共用圆角；当前为 0.70、0.81、14。 |
| `geometry` | `orchestra_support_width`、`orchestra_lead_width`、`orchestra_fire_lead_width` | 灰色伴奏、普通管弦主奏、末段红色长音宽度。 |
| `surface` | `piano_face_opacity`、`piano_face_white_mix`、`piano_inset_white_mix`、`piano_inset_strength` | 主面实度、偏白程度、内层棱面。 |
| `surface` | `piano_material_short`、`piano_material_long`、`piano_material_speed`、`piano_material_amount` | 短音／长音内部流动材质的强度、速度与纹理幅度。 |
| `surface` | `piano_bevel_light`、`piano_bevel_shadow` | 音符四周斜面的明暗对比。 |
| `light` | `piano_rim_base`、`piano_rim_pulse`、`piano_glow`、`piano_halo_base`、`piano_halo_pulse` | 清晰边缘、近光晕和均匀外晕的强度及慢速变化。 |
| `light` | `note_bloom_threshold`、`note_bloom_scale`、`note_bloom_brightness`、`note_bloom_blur` | 光晕滤镜；调亮时优先改 scale/brightness，避免把音符主体糊掉。 |
| `light` | `horizon_strength` | 琴键上方薄光层总亮度。 |

`render-plan.json` 管理**段落变化**：每个 `sections` 条目里的 `piano_low`、`piano_high`、`keyboard`、`horizon`、`density`、`speed`、`blend` 控制颜色、键盘、粒子和转场；可选的 `brightness_overrides`（如 `{"note_glow":1.15,"note_material":1.05}`）及 `appearance_overrides`（如 `{"glow_strength":1.1,"horizon_strength":0.9}`）控制该段内部亮度。顶层 `particle_trail_density_scale` 当前为 `1.65`，把细粒子、直线／弯曲光迹及小闪光发射量提高约 65%，不会加密烟雾或火焰素材。`build_render_plan.py` 编译时会合并它们，音频对齐不受影响。保持 `visual-style.json` 作为全曲固定质感，段落只改配色与强弱即可保持统一。

在仓库根目录运行 `python tools/prokofiev2-waterfall/render_movement.py --scene full --plan tools/prokofiev2-waterfall/render-plan.json --output-dir local/prokofiev2-waterfall/export`。首次检查可用 `--scene opening-title` 或其他 `clips` 场景。完整安装与媒体准备见上级 `README.zh-CN.md`。

`visual-preset.json` 是无分段时间线时的默认粒子与配色参数，也可作为另一个模板的起点。`visual-style.json` 则控制全曲固定的音符外形和面层光影。导出程序每次读取并检查这两份参数，音符时间和录音对齐不会受影响。

| 参数 | 作用 | 当前值 |
| --- | --- | ---: |
| `motion.flight_speed_scale` | 粒子实际移动速度的总比例；风仍按原节奏变化，0.5 约为上一版的一半 | 0.5 |
| `motion.launch_speed_scale` | 粒子与光迹初速度的比例；越小上升越慢 | 0.549 |
| `motion.launch_speed_pulse` | 连续喷射时，速度随时间起伏的幅度 | 0.38 |
| `motion.launch_speed_pulse_rate` | 上述起伏的快慢，弧度/秒 | 5.2 |
| `motion.airborne_speed_pulse_scale` | 粒子升空后速度变化的幅度 | 1.0 |
| `motion.launch_angle_sweep_radians` | 喷射方向左右摆动的幅度，弧度 | 0.17 |
| `motion.launch_angle_sweep_rate` | 喷射方向变化的快慢，弧度/秒 | 3.3 |
| `motion.launch_angle_jitter_radians` | 同时发射的粒子之间的角度差 | 0.05 |
| `motion.horizontal_wind_scale` | 空中横向风力 | 1.0 |
| `motion.vertical_wind_scale` | 空中纵向风力，可产生回卷 | 1.0 |
| `motion.plume_spread_pixels` | 同一束粒子后期充分展开时的横向宽度基准，像素 | 155 |
| `motion.plume_breath_rate` | 微散、聚拢、再散开的时间比例；越大变化越快 | 1.35 |
| `motion.plume_early_spread_fraction` | 初次小幅散开的宽度，相对后期宽度 | 0.2 |
| `motion.plume_gather_spread_fraction` | 中段聚拢后的宽度，相对后期宽度 | 0.025 |
| `density.ember_attack_count` | 每次触键瞬间增加的细粒子数 | 71 |
| `density.ember_per_second` | 按住琴键时每秒持续产生的细粒子数 | 197 |
| `density.filament_per_second` | 每秒产生的弯曲光迹数 | 0.8 |
| `brightness.ember` | 粒子本身亮度 | 1.0 |
| `brightness.filament` | 弯曲光迹亮度 | 1.0 |
| `brightness.note_glow` | 音符块外缘与光晕亮度 | 1.0 |
| `brightness.note_material` | 音符块内部纹理强度 | 1.0 |
| `brightness.strike_flash` | 触键处短暂亮光与持续光点的亮度 | 1.0 |

`density` 里的其余数值控制直线光迹、烟雾、火焰、光斑和闪点。`colors` 使用 `#RRGGBB` 格式，分别设置钢琴低音、高音、弦乐、木管、铜管和琴键交界线颜色。`size` 控制粒子和光迹尺寸。`schema_version` 不要修改。

同一小束粒子跟随共同的风中中心线，约在发射后 0.36 秒先小幅张开、0.82 秒收束，再于约 1.75 秒展开到最大。每一束有少量时间差，避免机械地同时收放。`flight_speed_scale` 同时缩小整体行程和束内张开的宽度，保留聚散的三个阶段。它不会改变音符触键时间，也不会改变粒子的存活时长。

要保存不同外观，可以复制这份 JSON，然后在运行导出时设置 `WATERFALL_PRESET_FILE` 为副本路径。先渲染一张静帧确认，再导出视频。

# 火焰渲染方式（v6）

场景参数 `appearance.fire_render_mode` 可设为 `sprite`（短寿命贴图粒子）、`fluid`（受风和浮力推动的密度场）、`metaball`（GPU 融合光团），或 `procedural`（旧版火焰）。只影响火焰画法，不改变音符与录音的对齐。三种对照样片均使用同一段 594.5–599.5 秒录音。

# 实拍火焰播放速度与补帧（v8）

结尾场景用 `appearance.fire_render_mode: "footage"`，只调节 `appearance.fire_playback_speed` 就能改变火焰速度；1 是原速，当前样片设为 0.76。此参数不会改变音符、粒子和录音的时间。原始火焰约 24 帧/秒，先离线生成 96 帧/秒的中间画面，再以 0.76 倍速播放并导出 60 帧/秒视频；因此不需要把同一张火焰图片连续显示好几帧。补帧可能在火苗分叉、消失的瞬间产生少量形变，正式长片前请先检查短样片。

本机图集可通过 `build-real-fire-atlas.py` 从自行取得的授权 ZIP 重新生成，不要把火焰图集上传到 GitHub。当前参数在 `profiles/crimson_real_fire_slow.json`，音符对齐仍来自原有 timeline。
