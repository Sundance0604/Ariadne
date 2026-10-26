"""Adjust existing exported captions and re-render, without re-reading music sources."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.video_export.content import read,write
from backend.video_export.paths import configured_path

SLOTS={'和弦':'harmony','配器':'orchestration','对位':'counterpoint','曲式':'form',
       '导聆':'guide','诠释':'interpretation','片头':'intro'}
DEFAULTS={'和弦':44,'配器':40,'对位':43,'曲式':41,'导聆':43,'诠释':51,'片头':63}


def load_sizes(path,interactive=False):
    from backend.video_export.editor import normalized_sizes
    values=normalized_sizes(read(path)) if path.exists() else dict(DEFAULTS)
    for label,default in DEFAULTS.items():
        value=values.get(label,default)
        if interactive:
            while True:
                answer=input(f'{label}字号 [{value}]（回车保持）：').strip()
                if not answer:break
                try:
                    candidate=int(answer)
                    if 12<=candidate<=120:value=candidate;break
                except ValueError:pass
                print('请输入 12 到 120 之间的整数。')
        if isinstance(value,bool) or not isinstance(value,int) or not 12<=value<=120:
            raise ValueError(f'“{label}”请填写 12 到 120 之间的整数。')
        values[label]=value
    if interactive or not path.exists():write(path,values)
    return values


def render(package,settings,interactive=False,ass_only=False):
    from backend.video_export.editor import load_document,export,stored_sizes,document_names
    sizes=load_sizes(settings,interactive)
    document=load_document(package=package)
    document['字号']=stored_sizes({name:sizes[name] for name in SLOTS},document_names(document))
    return export(document,package,ass_only=ass_only)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,default=ROOT/'output/video-export/ravel-demo')
    parser.add_argument('--settings',type=Path,default=configured_path('font_settings'))
    parser.add_argument('--interactive',action='store_true',help='依次输入字号，回车保持当前数值')
    parser.add_argument('--ass-only',action='store_true',help='只生成可编辑字幕，不编码 MP4')
    args=parser.parse_args()
    try:render(args.package,args.settings,args.interactive,args.ass_only)
    except (OSError,ValueError,KeyError,RuntimeError) as error:
        print(f'无法生成视频：{error}',file=sys.stderr);raise SystemExit(1)


if __name__=='__main__':main()
