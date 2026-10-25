# 马勒第四分析稿：文献与导入修订

日期：2026-10-25。

## 本轮改动

原稿保存在 `resource/mahler No.4/analysis/Mahler_Symphony_No4_Full_Analysis.original-20261025.md`，修订同目录的 `Mahler_Symphony_No4_Full_Analysis.md`。原有四乐章正文、动机关系及 32 个听点清单保留；修订陈旧的“尚未提供 PDF / 录音”说明，删除正文中的示例目录、JSON 与工程验收模板，改为面向读者的版本、页码和证据说明。新增三种研究路径的比较，保留解释的开放性。

原稿第 12 节已有书目线索，但页面尚未接入，也缺少逐项可验证的阅读记录。本轮将文献扩为 9 项，补作者、题名、年份、出版信息、稳定链接／DOI、适用章节及阅读边界。没有用书目数量代替论证，也没有把出版社摘要当成阅读全文。

## 文献核验

| 编号 | 来源 | 本轮实际范围 |
| --- | --- | --- |
| 1 | [SGM / de La Grange](https://societemahler-france.org/en/gustav-mahler-pieces/symphony-no-4/) | 官方创作史、首演、评论与分析正文；其中历史引语仍属二手转引 |
| 2 | [Berntstorff / 柏林爱乐](https://www.berliner-philharmoniker.de/en/programme-notes/gustav-mahler-symphony-no-4-in-g-major/) | 官方短文正文；没有沿用网页异常的乐章列表次序 |
| 3 | [Basinger / USUO](https://usuo.org/explore/2015/05/mahler-4-listening-guide/) | 创作史、配器与四乐章导赏正文 |
| 4 | [Mahler Foundation](https://mahlerfoundation.org/mahler/compositions/symphony-no-4/) | 主页面；没有声称所有分章子页已读 |
| 5 | [IMSLP](https://imslp.org/wiki/Symphony_No.4_(Mahler,_Gustav)) | #70999 的页数与出版链目录记录；未等同全部音符校勘 |
| 6 | [Monahan 2015](https://doi.org/10.1093/acprof:oso/9780199303465.003.0006) | OUP 第 5 章书目信息及摘要，未读全文 |
| 7 | [Denslinger 2021](https://wagner.radford.edu/719/) | 大学官方索引的题名页和摘要；实际页面和 PDF 请求 502，未读全文；导师不列为合著者 |
| 8 | [Kangas 2011](https://doi.org/10.1017/S1479409811000267) | Cambridge 书目信息及摘要，未读全文 |
| 9 | [Batstone 2020](https://doi.org/10.1017/rma.2020.14) | Cambridge 书目信息及摘要，未读全文 |

这些状态同时保存在 `works/mahler-4/metadata/recording.json`，并在播放器的“参考文献”中逐项显示。

## 播放器接入

后续更新：当前导聆已进一步拆为 38 段，最长 5 页，支持同页多段切换及底部四乐章跳转。原四章与下述 32 个未定位事件保留，详见 [短段赏析与乐章跳转](mahler4-paragraph-guide.md)。

`scripts/import_mahler4_analysis.py` 绑定原稿与当前 PDF、视频指纹；`scripts/analysis_data.py` 在刷新时实时重读源文件。四个乐章正文使用当前对齐文件的真实 movement 标记关联。32 个细分事件没有可靠位置，因此保持 `unlocated`，不按时长均分，也不提供虚构的跳转点。

全文与当前乐章可分别阅读。分析区切到新乐章时从顶部显示，读者正在浏览文献时不强制滚回导聆。原有拉威尔与云雀高飞的按页导聆继续使用原有入口。

## 检查

新增四项真实数据导入测试与两项前端定位测试，覆盖文件指纹、四章关联、32 个事件未定位状态、来源类型及旧按页逻辑兼容；修订稿导出确认 4 章、32 事件、9 文献。浏览器实查参考文献面板显示 9 项，并展示官方正文／摘要／官方索引的不同读取状态。

未完成的逐音／和声核验、直接原典引语版本页码、论文全文阅读及本次独唱者身份，均继续在文稿中明确保留。
