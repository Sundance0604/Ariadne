# 独立启动模块路径修复（2026-10-26）

用户报告一键启动后 `/api/project` 抛出 `ModuleNotFoundError: No module named 'backend'`，页面出现 `Failed to fetch`。此前验收的进程已具有仓库模块路径，未覆盖独立脚本启动的环境差异。

`scripts/serve_review.py` 现按自身路径添加仓库根目录，使直接脚本、根目录 `start.py`、一键启动器的 Handler 均能加载 backend；无需安装 music21，也不依赖当前工作目录或 PYTHONPATH。原有录音、同步结果、谱面映射与分析数据未修改。

验证结果：

- 最小播放环境运行启动器测试 4 项全部通过；新增测试创建独立 Python 进程，在其他目录运行，忽略 Python 环境变量，分别覆盖直接服务脚本、start.py 及 launch_local 导入路径。每个进程请求三首曲目的 project API 和拉威尔 live API，检查有效结果及无异常堆栈。
- MusicXML live 相关 6 项测试全部通过，包括实际 HTTP 模块导入图。
- 使用实际 `launch_local.py --track ravel-left-hand --no-browser` 启动本地 8765 服务；真实浏览器确认拉威尔谱图加载、1096 秒音源时长、播放按钮启用及多个活跃分部；切换马四后谱图和当前小节成功加载，再返回拉威尔。
- 本轮未重新试听、未复核音乐内容、未进行全套测试。favicon 的 404 与曲目数据加载故障无关，未作为本轮修复目标。

实际页面截图：`output/research/ravel-acceptance/launcher-fix.jpg`。
