"""Local guide-video exporter. Run --help; the original media is never modified."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.video_export.pipeline import make_package,prepare_score,compose,regenerate_ass,verify_video,review_caption,import_ass_text


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--track',required=True);p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--annotations',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    for name in ['ass','score','render','verify','all']:
        p=sub.add_parser(name);p.add_argument('--package',type=Path,required=True)
    for name in ['review-caption','import-ass-text']:
        p=sub.add_parser(name);p.add_argument('--package',type=Path,required=True)
        p.add_argument('--reviewer',required=True);p.add_argument('--scope',required=True)
        if name=='review-caption':p.add_argument('--id',required=True)
        else:p.add_argument('--source',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='prepare':
        print(make_package(ROOT,args.track,args.profile,args.annotations,args.output));return
    if args.command=='review-caption':print(review_caption(args.package,args.id,args.reviewer,args.scope));return
    if args.command=='import-ass-text':print(import_ass_text(args.package,args.source,args.reviewer,args.scope));return
    if args.command in {'ass','all'}:print('Approved captions:',regenerate_ass(args.package))
    if args.command in {'score','all'}:print(prepare_score(ROOT,args.package))
    if args.command in {'render','all'}:print(compose(ROOT,args.package))
    if args.command in {'verify','all'}:print(verify_video(ROOT,args.package))


if __name__=='__main__':main()
