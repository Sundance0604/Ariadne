"""Render the editable Mother Goose guide and bibliography as a local document."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'works/ravel-mother-goose/analysis'


def render(output):
    if output.exists():
        raise ValueError('Preserve existing writing; choose a new output path')
    guide = json.loads((BASE / 'guide.json').read_text(encoding='utf-8'))
    sources = json.loads((BASE / 'sources.json').read_text(encoding='utf-8'))
    titles = {1:'睡美人的帕凡舞',2:'小拇指',3:'丑姑娘，宝塔女皇',4:'美女与野兽的对话',5:'仙境花园'}
    text = [(BASE / 'overview.md').read_text(encoding='utf-8')]
    previous = None
    for section in guide['sections']:
        movement = section['movement']
        if movement != previous:
            text.append(f"\n## 第{movement}曲 {titles[movement]}\n")
            previous = movement
        lo, hi = section['local_measures']
        text.append(f"\n### {lo}–{hi}小节 {section['title']}\n")
        for key, label in [('harmony','和声'),('orchestration','配器与织体'),
                           ('counterpoint','声部关系与复调'),('form','曲式与主题发展')]:
            text.append(f"\n**{label}。** {section[key]}\n")
        text.append(f"\n**聆听线索。** {section['listening']}\n")
        text.append('\n出处定位：'+'；'.join(section['sources'])+'。\n')
    text.append('\n## 来源编号与实际阅读范围\n\n“PDF”均为物理页；“印刷”指文献印刷页号，不能互换。\n')
    for source in sources['sources']:
        url = source.get('url')
        title = f"[{source['title']}]({url})" if url else source['title']
        text.append(f"\n- **{source['id']}**：{source['author']}，{title}。{source.get('publication', source.get('edition_observed',''))}。实际范围：{source['read_status']}。用途：{source['use']}。\n")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(''.join(text), encoding='utf-8')
    print(output.relative_to(ROOT).as_posix())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='works/ravel-mother-goose/analysis/full-analysis.md')
    args = parser.parse_args()
    render(ROOT / args.output)
