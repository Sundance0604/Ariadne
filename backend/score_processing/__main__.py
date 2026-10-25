import argparse
import json
import subprocess
import sys

from .pipeline import convert_pdf


def main():
    parser = argparse.ArgumentParser(description='PDF -> per-page MusicXML using local Audiveris')
    parser.add_argument('pdf', help='Input PDF (never modified)')
    parser.add_argument('--output', default='output/omr', help='Output/cache directory')
    parser.add_argument('--pages', help='Physical PDF pages, e.g. 1,3-5; omit for all pages')
    parser.add_argument('--audiveris', help='Audiveris executable or launcher')
    parser.add_argument('--musescore', help='Optional MuseScore executable for PNG verification')
    parser.add_argument('--dpi', type=int, default=300)
    parser.add_argument('--retries', type=int, default=1, help='Additional attempts per failed page')
    parser.add_argument('--timeout', type=int, default=900, help='Seconds per external command')
    parser.add_argument('--force', action='store_true', help='New attempt; preserve existing outputs')
    parser.add_argument('--expected-staves', type=int, help='Optional per-page reference staff count')
    parser.add_argument('--expected-measures', type=int, help='Optional reference measures per part')
    args = parser.parse_args()
    try:
        report = convert_pdf(**vars(args))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'Conversion failed: {exc}', file=sys.stderr)
        return 1
    print(json.dumps({'status': report['status'], 'report': report['report_path'],
                      'cache_hits': sum(p['cache_hit'] for p in report['pages']),
                      'pages': len(report['pages'])}, ensure_ascii=False))
    return 1 if report['status'] == 'failed' or report['render_failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
