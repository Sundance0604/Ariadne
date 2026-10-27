# 拉威尔鹅妈妈研究

当前先研究五曲管弦乐组曲，没有演出音频。入口为[完整分析初稿](analysis/full-analysis.md)，包含全曲叙述、38段四维分析及文献定位。

| 内容 | 路径 |
|---|---|
| 可读分析 | [full-analysis.md](analysis/full-analysis.md) |
| 可编辑段落资料 | [guide.json](analysis/guide.json) |
| 书目与实际阅读范围 | [sources.json](analysis/sources.json) |
| 另源版本与分歧 | [alternate-source-audit.json](analysis/alternate-source-audit.json) |
| 当前独立快照 | [current.json](analysis/current.json) |
| 输入指纹及乐章表 | [project.json](project.json) |
| 本轮范围与核查结果 | [研究报告](../../reports/mother-goose-research-20261026.md) |

`analysis/current.json`只指向本作品的研究快照，没有修改根目录拉威尔左手协奏曲的激活指针，也没有注册一个缺少媒体的播放曲目。

本作品的主候选XML为531小节、40个源分部。另源`resource/mother goose/new/`带有芭蕾版场景、附加段落及不同编制拆分，仅作参照。书内谱例、原扫描谱和XML分歧要分别保留，不能用文件较新或三份文件互相对应来代替校勘。

处理环境安装`requirements-analysis.txt`后，可从根目录另建快照：

```powershell
python scripts/compare_mother_goose_sources.py
python scripts/build_mother_goose_research.py --output works/ravel-mother-goose/analysis/musicxml/新的目录
python scripts/render_mother_goose_research.py --output works/ravel-mother-goose/analysis/新的分析稿.md
```

新快照拒绝覆盖已有目录；长文生成也拒绝覆盖已有文件。`guide.json`和`overview.md`是当前写作底稿，生成后的长文还可单独编辑。两个研究构建脚本都是本作品适配器，不是通用全谱分析器。预计算文件的检查不需要music21：

```powershell
python -m unittest discover -s tests -p test_mother_goose_research.py -v
```

之后接入演出时，先核对是否五曲组曲或完整芭蕾、乐章次序及删节，再建立独立媒体指纹、原谱几何和录音映射。现有小节、段落和源音符ID可复用；不得把MIDI演奏秒数当作实际演出秒数。
