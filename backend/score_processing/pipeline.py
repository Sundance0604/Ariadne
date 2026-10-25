"""Page-isolated Audiveris conversion with persistent, verified output caching."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

from .musicxml import inspect_musicxml, read_musicxml
from .process import run_external

ROOT = Path(__file__).resolve().parents[2]
PIPELINE_VERSION = 1


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def write_json(path, value):
    pending = path.with_suffix('.pending.json')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    pending.replace(path)


def select_pages(spec, total):
    if spec is None:
        return list(range(1, total + 1))
    pages = set()
    for token in spec.split(','):
        ends = token.strip().split('-')
        if len(ends) == 1:
            start = end = int(ends[0])
        elif len(ends) == 2:
            start, end = map(int, ends)
        else:
            raise ValueError('Pages must look like 1,3-5')
        if not 1 <= start <= end <= total:
            raise ValueError(f'Page range {token!r} is outside 1-{total}')
        pages.update(range(start, end + 1))
    if not pages:
        raise ValueError('No pages selected')
    return sorted(pages)


def find_audiveris(explicit=None):
    candidate = explicit or os.environ.get('AUDIVERIS_PATH')
    if candidate:
        path = Path(candidate).expanduser().resolve()
    else:
        portable = ROOT / '.tools/audiveris-portable/Audiveris/Audiveris.exe'
        found = shutil.which('Audiveris') or shutil.which('audiveris')
        path = portable if portable.is_file() else Path(found) if found else None
    if path is None or not path.is_file():
        raise FileNotFoundError('Audiveris not found; set AUDIVERIS_PATH or --audiveris')
    return path.resolve()


def run_command(command, log, env, timeout):
    # Do not interpolate paths into shell command strings.
    with log.open('wb') as stream:
        stream.write((json.dumps([str(c) for c in command], ensure_ascii=False) + '\n').encode('utf8'))
        stream.flush()
        try:
            returncode = run_external([str(c) for c in command], stream, env, timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f'Command timed out after {timeout}s; see {log}') from exc
    if returncode:
        raise RuntimeError(f'Command exited {returncode}; see {log}')


def _convert_page(document, page_number, folder, engine, env, dpi, retries, timeout,
                  force, expected_staves, expected_measures, musescore):
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / 'result.json'
    if manifest.is_file() and not force:
        try:
            cached = json.loads(manifest.read_text(encoding='utf8'))
        except (ValueError, OSError):
            cached = {}
        files = cached.get('files', {})
        if (cached.get('status') == 'converted_needs_review' and files
                and (not musescore or cached.get('render', {}).get('status') == 'rendered_needs_review')
                and all(Path(p).is_file() and digest(p) == sha for p, sha in files.items())):
            cached['validation'] = [inspect_musicxml(p, expected_staves, expected_measures)
                                    for p in cached['musicxml']]
            if all(v['structurally_valid'] for v in cached['validation']):
                cached['cache_hit'] = True
                return cached
    attempts = sorted(folder.glob('attempt-*'))
    attempt_number = max((int(p.name.split('-')[1]) for p in attempts), default=0)
    failures = []
    for _ in range(retries + 1):
        attempt_number += 1
        attempt = folder / f'attempt-{attempt_number:03d}'
        attempt.mkdir()
        result = {'page': page_number, 'attempt': str(attempt), 'cache_hit': False,
                  'status': 'failed', 'previous_failures': failures.copy()}
        try:
            image = attempt / f'page-{page_number:04d}.png'
            with closing(document[page_number - 1]) as page:
                with closing(page.render(scale=dpi / 72)) as bitmap:
                    with bitmap.to_pil() as picture:
                        picture.save(image)
            log = attempt / 'audiveris.log'
            result['input_image'], result['log'] = str(image), str(log)
            run_command([engine, '-batch', '-transcribe', '-export', '-save',
                         '-output', attempt, '--', image], log, env, timeout)
            mxls = sorted(attempt.rglob('*.mxl'))
            omrs = sorted(attempt.rglob('*.omr'))
            if not mxls or not omrs:
                raise RuntimeError('Audiveris produced no MXL or OMR project; see execution log')
            validation, xmls = [], []
            for mxl in mxls:
                data, _ = read_musicxml(mxl)
                xml = mxl.with_suffix('.musicxml')
                xml.write_bytes(data)
                xmls.append(xml)
                inspection = inspect_musicxml(mxl, expected_staves, expected_measures)
                validation.append(inspection)
                if not inspection['structurally_valid']:
                    raise RuntimeError(f'Invalid MusicXML structure: {inspection["errors"]}')
            log_lines = log.read_text(encoding='utf8', errors='replace').splitlines()
            result.update(mxl=[str(p) for p in mxls], musicxml=[str(p) for p in xmls],
                          omr=[str(p) for p in omrs], validation=validation,
                          engine_diagnostics=[line for line in log_lines
                                              if any(s in line for s in ('WARN ', 'ERROR ',
                                                                         'no correct rhythm',
                                                                         'No timeOffset'))])
            render = {'status': 'not_requested', 'images': []}
            if musescore:
                render['status'] = 'rendered_needs_review'
                for i, mxl in enumerate(mxls, 1):
                    prefix = attempt / f'rerender-{i}'
                    render_log = attempt / f'musescore-{i}.log'
                    try:
                        run_command([musescore, '-r', '150', '-o', prefix.with_suffix('.png'), mxl],
                                    render_log, env, timeout)
                        images = sorted(attempt.glob(prefix.name + '*.png'))
                        if not images:
                            raise RuntimeError('MuseScore returned without PNG output')
                        from PIL import Image
                        for path in images:
                            with Image.open(path) as picture:
                                picture.verify()
                        render['images'].extend(str(p) for p in images)
                    except (RuntimeError, OSError) as exc:
                        render.update(status='failed', error=str(exc))
                result['render'] = render
            else:
                result['render'] = render
            result['status'] = 'converted_needs_review'
            retained = [image, log, *mxls, *xmls, *omrs,
                        *(Path(p) for p in render['images'])]
            result['files'] = {str(p): digest(p) for p in retained}
            write_json(manifest, result)
            return result
        except (OSError, ValueError, RuntimeError, KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
            result['error'] = str(exc)
            write_json(attempt / 'failure.json', result)
            failures.append({'attempt': str(attempt), 'error': str(exc)})
    result['previous_failures'] = failures
    write_json(manifest, result)
    return result


def convert_pdf(pdf, output, pages=None, audiveris=None, dpi=300, retries=1, timeout=900,
                force=False, expected_staves=None, expected_measures=None, musescore=None):
    """Return a JSON-serializable report; a failed page does not discard other pages.

    Each page is an independent OMR book. No cross-page voice/part merging or
    original measure numbering is claimed. ``pages`` uses physical PDF pages (1-based).
    """
    import pypdfium2 as pdfium

    pdf, output = Path(pdf).resolve(), Path(output).resolve()
    if not pdf.is_file() or pdf.suffix.lower() != '.pdf':
        raise ValueError('Input must be an existing PDF file')
    if dpi < 72 or dpi > 600 or retries < 0 or timeout <= 0:
        raise ValueError('DPI must be 72-600; retries >= 0; timeout > 0')
    engine = find_audiveris(audiveris)
    if musescore:
        musescore = Path(musescore).resolve()
        if not musescore.is_file():
            raise FileNotFoundError(f'MuseScore not found: {musescore}')
    output.mkdir(parents=True, exist_ok=True)
    state = ROOT / '.tools/audiveris-data'
    temp = ROOT / 'tmp/java'
    cache = ROOT / '.tools/javacpp'
    for path in (state, state / 'local', temp, cache):
        path.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(APPDATA=str(state), LOCALAPPDATA=str(state / 'local'))
    env['JAVA_TOOL_OPTIONS'] = (f'-Djava.io.tmpdir="{temp}" '
                                f'-Dorg.bytedeco.javacpp.cachedir="{cache}"')
    # Version is part of the cache identity. Keep app data local to the workspace.
    version = subprocess.run([str(engine), '-version'], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, env=env, timeout=60, check=True)
    identity = {'pipeline_version': PIPELINE_VERSION, 'pdf_sha256': digest(pdf),
                'dpi': dpi, 'audiveris_path': str(engine), 'audiveris_sha256': digest(engine),
                'audiveris_version': version.stdout.decode('utf8', errors='replace')}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    job = output / f'{pdf.stem[:48]}-{key}'
    job.mkdir(exist_ok=True)
    lock = job / 'processing.lock'
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f'Conversion is already running, or stale lock needs checking: {lock}') from exc
    try:
        os.write(descriptor, str(os.getpid()).encode())
        (job / 'audiveris-version.log').write_bytes(version.stdout)
        with pdfium.PdfDocument(str(pdf)) as document:
            selected = select_pages(pages, len(document))
            results = []
            for page in selected:
                print(f'Processing PDF page {page}/{len(document)}', flush=True)
                results.append(_convert_page(document, page, job / f'page-{page:04d}', engine,
                                              env, dpi, retries, timeout, force,
                                              expected_staves, expected_measures, musescore))
        failed = any(p['status'] == 'failed' for p in results)
        render_failed = any(p.get('render', {}).get('status') == 'failed' for p in results)
        report = {'status': 'failed' if failed else 'converted_needs_review',
                  'created_utc': datetime.now(timezone.utc).isoformat(),
                  'input_pdf': str(pdf), 'identity': identity, 'selected_pages': selected,
                  'scope': 'independent_pages', 'musical_accuracy_verified': False,
                  'render_failed': render_failed, 'pages': results, 'report_path': str(job / 'report.json')}
        write_json(job / 'report.json', report)
        return report
    finally:
        os.close(descriptor)
        lock.unlink(missing_ok=True)
