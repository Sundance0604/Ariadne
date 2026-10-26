import argparse
from pathlib import Path
from .common import read,write,digest


def main():
    parser=argparse.ArgumentParser(description='Independent, fingerprint-bound score-analysis pilot; no audio alignment changes.')
    sub=parser.add_subparsers(dest='command',required=True)
    build=sub.add_parser('build');build.add_argument('--profile',required=True);build.add_argument('--output',required=True);build.add_argument('--activate',action='store_true')
    validate=sub.add_parser('validate');validate.add_argument('run')
    compare=sub.add_parser('compare');compare.add_argument('--run',required=True);compare.add_argument('--input',required=True);compare.add_argument('--output',required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[2]
    if args.command=='build':
        from .pipeline import build
        run=build(root,root/args.profile,root/args.output,args.activate)
        print(run.relative_to(root).as_posix())
    elif args.command=='compare':
        from .comparison import record_comparison
        path=record_comparison(root,root/args.run,root/args.input,root/args.output)
        print(path.relative_to(root).as_posix())
    else:
        from .store import validate_run
        validate_run(root/args.run,root);print('Structure and source validation passed; not expert musical verification.')


if __name__=='__main__':main()
