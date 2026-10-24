# Ariadne 独立安装检查

日期：2026-10-25。

为公开仓库增加 `requirements.txt`、`start.py` 与不依赖系统 Poppler 的 PDFium 谱页渲染。Windows、macOS 和 Linux 的安装命令见 README；当前实际验证平台为 Windows / Python 3.12。

在全新虚拟环境中只安装 `requirements.txt`，得到 Mistune 3.3.3、pypdfium2 5.14.0、Pillow 13.0.0。对实际提交建立本地克隆，未复制 `.tools`、原项目缓存或虚拟环境，再使用上述轻量环境运行 `test_playback_install.py`：两首作品的项目与导聆接口、音频分段读取、首末页重新渲染及谱页 HTTP 返回均通过；`start.py --help` 正常。未重新计算同步结果。

现有同步处理环境执行全部测试：20 项中 18 项通过，2 项 M4A 实验按要求跳过。可选 `requirements-processing.txt` 在干净 Python 3.12 环境执行 pip 安装解析检查成功；此处未将全部可选依赖重新安装后运行耗时对齐。

PDFium 渲染后的末页已查看，谱面内容正常；本次没有新增浏览器播放、变速或红线视觉验收，相关候选同步精度仍遵循原报告的复核状态。

参考：实现按 [pypdfium2 官方使用说明](https://pypdfium2.readthedocs.io/en/stable/readme.html) 的页面渲染与 PIL 图像转换接口编写。
