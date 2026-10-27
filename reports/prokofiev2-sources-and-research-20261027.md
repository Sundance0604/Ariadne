# 普罗科菲耶夫第二钢琴协奏曲 XML 核查与研究资料

日期：2026年10月27日。核查者：代理；人类签核、专家逐音校勘均未完成。

材料对应《第二钢琴协奏曲》Op.16，四个乐章及抽查的主要音型能与扫描总谱对应。但 XML 有局部节奏编码疑点，不能据此认定全曲音符、时值和声部已经校勘正确。现阶段可开展文献与直接读谱研究；精细的自动和声、对位或时点配器分析须先处理相关窗口。

## 材料与结构

原件位于 `resource/PROKOFIEV PIANO CONCERTO 2/`。源文件未修改。完整指纹、分部计数及逐项异常保存于 [结构核查 JSON](../works/prokofiev-piano-concerto-2/reports/source-audit-20261027.json)。本轮没有注册播放器曲目、生成录音同步或改动现有作品的激活数据。

| 材料 | 观测 |
|---|---|
| `piano-concerto-no2-op16-s-prokofiev.mxl` | ZIP CRC 检查通过，包含 MusicXML 3.1 `score.xml`，标注 MuseScore 3.6.2、2022-01-19 |
| XML 自报来源 | https://musescore.com/user/11523441/scores/7433963 ，仅为源文件内声明，本轮未独立核实上传者或校勘质量 |
| 同名重排 PDF | 168 物理页，第一页 612 × 792 PDF 点 |
| `IMSLP66128-PMLP04521-Prokofiev_-_Piano_Concerto_No._2,_Op._16_(orch._score).pdf` | 168 物理页，第一页 619.2 × 800.64 PDF 点，扫描谱 |
| XML 结构 | 20 个分部，各含 864 个 measure 元素；其中包括独立 Ossia 分部 |

| 乐章 | XML 全局序列 | 乐章内编号 | 两份 PDF 的物理页范围 |
|---|---|---|---|
| I Andantino | 1–200 | 1–200 | 1–37 |
| II Scherzo Vivace | 201–387 | 1–187 | 38–69 |
| III Intermezzo Allegro moderato | 388–546 | 1–159 | 70–108 |
| IV Finale Allegro tempestoso | 547–864 | 1–317，另有隐含 X1 | 109–168 |

这些范围来自 XML 换页标记和谱页的交叉核查。仅同页数、同源重排或文件可以打开，都不是独立的逐音正确性证据。

## 谱面抽查

扫描原谱是独立的视觉参照；重排 PDF 用于检查与 XML 的排版对应。视觉核查覆盖下列窗口，未扩大为全曲通过结论。

| 物理页 | 扫描谱印刷页 | 核查内容与结果 |
|---|---|---|
| 1 | 99 | 开头单簧管与弦乐的短引子、钢琴第3小节左手三连音伴奏、第4小节右手入口的位置与主要音型对应；单簧管应将 XML 编码音显式移调后与实音总谱比较 |
| 2 | 100 | 第5–10小节弦乐分奏及12/8与钢琴4/4并置可见；这一复合拍与声部交叠区域也是 XML 内部时值疑点所在，不能将谱面对应提升为时值通过 |
| 23 | 121 | 第116小节附近由三谱表钢琴转向后续双谱表写法的位置相符；未逐音签核整页华彩 |
| 38 | 136 | II 开头钢琴双手八度十六分音符持续运动及木管材料对应 |
| 70 | 168 | III 开头大管重音线条、弦乐低音与定音鼓织体及钢琴休止对应；隐藏音符不应被当成钢琴实际入口 |
| 109 | 207 | IV 开头钢琴八度与木管、弦乐的节奏和主要下行动势对应；八度线须与编码音区区别处理 |
| 153 | 251 | 排练号126至 Andante 的段落顺序、长音背景及钢琴无常规小节线的持续片段对应；XML X1 是此类延续编码的一部分 |
| 168 | 266 | 末页三小节及终止位置对应；钢琴末音为 G，XML 分别保留右手 G3 与左手 G1/G2；没有据此认证此前全部和声 |

## XML 的主要疑点

1. **第一乐章第6、7、8、10、11、12小节的弦乐时轴需复核。** P16、P17、P18 分别为第一小提琴、第二小提琴、中提琴。按 XML `divisions`、`duration`、`backup`、`forward` 直接读取，第6小节 P16 第一声部的非和弦事件合计2640单位，而随后的 backup 为1920单位；其余声部因此不能简单回到小节起点。原谱此处同时使用12/8与4/4，须核对实际等时关系和每个声部，不能靠整小节机械缩放修复。
2. **37个音符或休止符的 duration 与 type、附点、显式连音比例不一致，超出1个源单位的容差。** 均集中于上述三个弦乐分部的第一乐章第6、8、10、12小节。比如第6小节的附点四分休止记谱对应3/2个四分音符，duration 却是1个。这里先记为编码不一致，不能等同37个独立的原谱错误。
3. **57个全局小节序列出现分部时间跨度不一致。** 其中6个是上述较大偏差区域，其余51个偏差很小，多见于复杂连音的整数取整。两类需分开处理；跨分部长度检测也不是曲谱准确率。
4. **隐藏有音高事件639个。** 一些乐章开头原谱整小节休止的分部仍带隐藏音符，精细和声及活跃乐器分析必须隔离它们。不能据此推定实际录音发声。
5. **Ossia分部有588个可见有音高事件。** 属替代写法，不能默认与主钢琴同时发声。后续须按对应谱例建立选择关系。
6. **可疑文字标记398条。** 本轮规则只检出 `.1`至`.9`、`lel` 和含替代字符的文本，尚未逐条判定用途；不应当成曲式或速度边界。
7. **IV 的隐含 X1 与移调要单独处理。** 第四乐章在265与266之间有 `number="X1" implicit="yes"`，所以318个XML小节元素不能宣称为318个印刷编号小节。单簧管、小号、圆号及低音提琴有显式移调；必须应用一次，不能把实音总谱与XML记谱音直接比较。

现阶段建议保留原 MXL，在独立工作副本中先校核第一乐章第6–12小节，再处理隐藏事件、Ossia、跨谱表和华彩。修复范围之外的音高、临时记号、连线、踏板与演奏法仍需有选择地回原谱核查。

## 直接研究第二钢琴协奏曲的资料

以下中文题名是便于阅读的译名。目录或摘要访问不等于读过全文。

### Anna Dmytrenko 2025

*Prokofiev Piano Concerto No. 2: An In-Depth Look from the Pianist’s Bench.* Doctor of Musical Arts, Manhattan School of Music, May 2025。

- [学校馆藏题名页](https://digitalcollections.msmnyc.edu/digital/api/collection/theses/id/2414/download)
- [图表目录](https://digitalcollections.msmnyc.edu/digital/api/collection/theses/id/2419/download)
- [创作史正文第34页](https://digitalcollections.msmnyc.edu/digital/api/collection/theses/id/2456/download)
- 已查阅题名页、图表目录及部分创作史／结论正文；没有通读全篇。目录明确包含第一乐章华彩结构、第二乐章练习方法、第三乐章结构等，可优先服务钢琴织体、华彩组织与演奏比较。
- 文中对施密特霍夫之死与创作因果、以及“完全凭记忆重写”的通俗叙述提出质疑。后续引用须注明作者观点，并回查日记和书信，不能将故事直接套成每段音乐的含义。

### Katarzyna Marzec 2013

*Prokofiev’s Second Piano Concerto: Its Genesis, Form, and Narrative Structure.* DMA dissertation, Temple University。

- [原馆藏入口](https://digital.library.temple.edu/digital/collection/p245801coll10/id/238190)
- [Temple 馆藏另一篇论文的参考书目第44页](https://digital.library.temple.edu/digital/api/collection/p245801coll10/id/540539/download)核实作者、题名、学校与年份。
- 本轮原馆藏入口访问失败，仅核实书目；未读取该论文全文。题名直接涉及创作史、曲式与叙事结构，适合作为优先取得原文的核心资料，不能把二手转述标为原文结论。

### Hanna Horobets 2019

*Другий фортепіанний концерт Сергія Прокоф’єва: проблема образно-смислової багатозначності тексту*，中文可译《普罗科菲耶夫第二钢琴协奏曲的形象与意义多义性》。*Київське музикознавство* 59，112–128。DOI：[10.33643/kmus.2019.59.09](https://doi.org/10.33643/kmus.2019.59.09)。

- [期刊原始页面与全文入口](https://kyivmusicology.com/index.php/journal/article/view/101)
- 已读期刊摘要及PDF中演奏版本选择、创作史、曲式讨论的相关段落，主要为印刷页115–118；未逐页通读全文。
- 直接比较彼得罗夫、阿什肯纳齐、王羽佳、吉尔特堡的诠释，适合建立多种读法并列的导聆。文中王羽佳版本为2017年雅尔维／柏林爱乐；不能仅凭用户视频文件名认定为同次演出。

### Özgür Deniz Akalın 2023

*Sergey Prokofiev'in Op.16 2 Numaralı Piyano Konçertosu'nun formsal ve yapısal bakımdan incelenmesi*，英文目录题名 *Formal and structural analysis on Sergei Prokofiev's Piano Concerto No.2 Op.16*。Anadolu Üniversitesi 硕士论文，论文号831267，土耳其语，导师 Gökhan Aybulus。

- [目录与摘要线索](https://tezara.org/theses/831267)
- 搜索索引展示了题名、作者、年份及摘要；直接页面返回403。本轮未在学校或国家学位库取得原文，保留为待取原文的补充线索，不作为已读分析依据。

## 和声与结构分析的补充学术资料

下列三项提供分析方法或风格背景，并非第二协奏曲逐小节专论。

### Deborah Rifkin 2004

*A Theory of Motives for Prokofiev’s Music.* *Music Theory Spectrum* 26(2)，265–289。DOI：[10.1525/mts.2004.26.2.265](https://doi.org/10.1525/mts.2004.26.2.265)。

[出版社摘要](https://academic.oup.com/mts/article-abstract/26/2/265/1120119)。已核实期刊元数据并阅读摘要，未取得付费正文。文章结合申克与新里曼思路讨论动机和半音语言，可用于设计主题材料与和声联系的研究方法，不能据摘要声称论文已分析本协奏曲的具体段落。

### Jacy R Pedersen 2019

*A Theory of Closure in the Works of Sergei Prokofiev.* Texas Christian University，硕士论文。

[大学馆藏与全文入口](https://repository.tcu.edu/entities/publication/8c3b3c41-1488-40cd-905b-ecd644271f05)。已读馆藏摘要，未通读正文。其终止研究强调半音线条、对位运动、织体与低音共同形成结束感，可用来研究不能只凭属主和弦判断的乐句边界；对本曲的应用仍须读谱论证。

### Christina Guillaumier 2010

*From piano to stage: a genealogy of musical ideas in the piano works of Sergei Prokofiev (1900–c.1920).* PhD thesis, University of St Andrews。DOI：[10.17630/10023-6451](https://doi.org/10.17630/10023-6451)。

[大学馆藏与公开删节版全文](https://research-repository.st-andrews.ac.uk/handle/10023/6451)。已读摘要、目录与引言相关段落；未通读全篇。研究钢琴演奏技术与作曲思维的联系、姿态和主题材料的谱系，可为钢琴与乐队之间的材料转移提供背景。公开版删除了附录D，不称作无删节全文。

## 后续使用顺序

先取 Dmytrenko 与 Marzec 的核心章节，核对华彩和曲式模型；Horobets 用于演奏诠释比较。和声与乐句边界再参考 Rifkin、Pedersen，始终将文献判断落回明确的谱页与声部。Akalın 保留为待取得原文的线索。XML 局部编码问题不妨碍这一步文献与直接读谱研究，但不应进入自动化精细分析后再被误认为音乐事实。

视频、本地素材与原XML均未上传；没有提交或推送Git。

## 同日补充：用户取得的两份 PDF

原先“只读摘要／未取得原文”的记录描述初次检索范围。用户随后提供了以下本地文件，原件保留；不再需要为这两项取得原文而使用大学网络。本次补充没有把它们标为全文已通读，也没有将出版商页数与本地 PDF 物理页数混用。

| 文件 | 本地状态与实际阅读范围 |
|---|---|
| `resource/PROKOFIEV PIANO CONCERTO 2/research/Prokofiev’s Second Piano Concerto Its Genesis, Form, and Narrative Structure.pdf` | 149物理页，文字可提取；已读题名页、摘要、目录与谱例目录（物理1–9页），正文分析未通读。目录中第五至八章分别讨论四个乐章，可先将其作为本协奏曲的主要研究文献。SHA-256：`1086aca27e800b72a1adc836fff20d5025937f1f2b28862d9c8d3719d5392364`。 |
| `resource/PROKOFIEV PIANO CONCERTO 2/research/A_Theory_of_Motives_for_Prokof.pdf` | 27物理页，文字可提取；已检查前3物理页，尚未通读全文。可先作为动机及半音语言的方法参照，不能据此宣称它逐小节研究了第二协奏曲。SHA-256：`69a31a383725a7a84b2c637f1d5145ad068835e0a89d0815cbb83b2e59fa8659`。 |

这两份材料足以启动下一步章节阅读与谱例核查，其余五项仍作为补充来源；不以凑齐所有PDF作为研究门槛。新增的本地论文文件未提交或上传。

### 同日继续的章节阅读与分析

随后已选读Marzec的四章分析、总结与相关历史段落，以及Rifkin的方法和结论，并完成[四乐章分析正文](../works/prokofiev-piano-concerto-2/analysis/full-analysis.md)。上面的摘要／开头阅读状态保留为初次检索与收件时记录；本轮最新物理页范围、实际用途和限制见[分析来源台账](../works/prokofiev-piano-concerto-2/analysis/sources.json)。仍未将两篇文献标为全篇通读，也未把作者的叙事判断变成作曲家指定的情节。
