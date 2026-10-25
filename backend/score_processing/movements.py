"""Native multi-page Audiveris books, one independent job per movement.

No concatenation of independently inferred part IDs. Audiveris itself connects
pages; fragmented exports and missing pages remain explicit review failures.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from contextlib import closing

from .musicxml import inspect_musicxml, extract_musicxml
from .pipeline import ROOT, digest, find_audiveris, run_command, write_json


def load_manifest(path):
    manifest = json.loads(Path(path).read_text(encoding='utf8'))
    covered = []
    for movement in manifest['movements']:
        start, end = movement['start_page'], movement['end_page']
        if start > end or movement['page_count'] != end - start + 1:
            raise ValueError('Invalid movement page range')
        covered.extend(range(start, end + 1))
    if covered != list(range(1, manifest['pdf_pages'] + 1)):
        raise ValueError('Movement ranges must cover the PDF once, in order')
    if len({m['number'] for m in manifest['movements']}) != len(manifest['movements']):
        raise ValueError('Duplicate movement number')
    return manifest


def book_progress(path, start, end, sheet_page_offset=0):
    with zipfile.ZipFile(path) as archive:
        book = ET.fromstring(archive.read('book.xml'))
        done, incomplete, invalid = [], [], []
        for sheet in book.findall('sheet'):
            sheet_number = int(sheet.get('number'))
            number = sheet_number + sheet_page_offset
            if not start <= number <= end:
                continue
            if sheet.get('invalid', 'false') == 'true':
                invalid.append(number)
            elif 'PAGE' in (sheet.findtext('steps') or '').split():
                # A step in book.xml alone cannot prove sheet data was retained.
                if f'sheet#{sheet_number}/sheet#{sheet_number}.xml' in archive.namelist():
                    done.append(number)
                else:
                    incomplete.append(number)
            else:
                incomplete.append(number)
        missing = sorted(set(range(start, end + 1)) - set(done) - set(invalid))
        return {'completed_pages': sorted(done), 'invalid_pages': sorted(invalid),
                'pending_pages': missing, 'book_source': book.get('path'),
                'software_version': book.get('software-version')}


def prepare_image_book(pdf, movement, folder, dpi, pdf_sha256):
    """Stream grayscale TIFF frames, keeping one raster page in memory at a time."""
    import pypdfium2 as pdfium
    from PIL.TiffImagePlugin import AppendingTiffWriter

    source = folder / 'input'
    source.mkdir(exist_ok=True)
    image_book, metadata = source / 'score.tif', source / 'input.json'
    identity = {'pdf_sha256': pdf_sha256, 'start_page': movement['start_page'],
                'end_page': movement['end_page'], 'dpi': dpi, 'rasterizer': 'pdfium-gray-tiff-v1'}
    if metadata.is_file() and image_book.is_file():
        cached = json.loads(metadata.read_text(encoding='utf8'))
        if cached.get('identity') == identity and cached.get('tiff_sha256') == digest(image_book):
            return image_book
    pending = source / 'score.pending.tif'
    # AppendingTiffWriter appends to an existing path, so always begin with a
    # fresh pending file after an interrupted preparation.
    pending.unlink(missing_ok=True)
    with pdfium.PdfDocument(str(pdf)) as document, AppendingTiffWriter(str(pending), True) as writer:
        for number in range(movement['start_page'], movement['end_page'] + 1):
            with closing(document[number - 1]) as page, closing(page.render(scale=dpi / 72)) as bitmap:
                with bitmap.to_pil().convert('L') as image:
                    image.save(writer, format='TIFF', compression='tiff_deflate', dpi=(dpi, dpi))
                    writer.newFrame()
            write_json(source / 'preparation.json', {'status': 'preparing_images',
                       'rasterized_pages': number - movement['start_page'] + 1,
                       'total_pages': movement['page_count']})
    pending.replace(image_book)
    write_json(metadata, {'identity': identity, 'tiff_sha256': digest(image_book)})
    write_json(source / 'preparation.json', {'status': 'prepared',
               'rasterized_pages': movement['page_count'], 'total_pages': movement['page_count']})
    return image_book


def read_status(folder, movement):
    path = folder / 'movement-report.json'
    report = json.loads(path.read_text(encoding='utf8')) if path.is_file() else {
        'status': 'not_started', 'movement': movement, 'completed_pages': []}
    # During processing the .omr is a live checkpoint. A ZIP read can briefly
    # fail while the engine replaces it; keep the last published snapshot then.
    active = folder / 'active-run.json'
    if active.is_file():
        run = json.loads(active.read_text(encoding='utf8'))
        books = list(Path(run['folder']).glob('*.omr'))
        if books:
            try:
                report.update(book_progress(books[0], movement['start_page'], movement['end_page'],
                                            run.get('sheet_page_offset', 0)))
            except (OSError, zipfile.BadZipFile, ET.ParseError):
                pass
        report['active_run'] = run
    results = sorted((folder / 'runs').glob('run-*/result.json'), reverse=True)
    if results:
        previous = json.loads(results[0].read_text(encoding='utf8'))
        report['last_successful_export'] = {
            key: previous[key] for key in ('source_pages_in_export', 'exports', 'omr') if key in previous}
    return report


def transcribe_movement(manifest, movement, output, through_page=None, batch_size=4,
                        retries=1, audiveris=None, resume_book=None, dpi=450, native_pdf=False):
    pdf = (ROOT / manifest['pdf']).resolve()
    if digest(pdf) != manifest['pdf_sha256']:
        raise ValueError('Input PDF fingerprint differs from the movement manifest')
    start, end = movement['start_page'], movement['end_page']
    target = end if through_page is None else through_page
    if not start <= target <= end or batch_size < 1 or retries < 0 or not 72 <= dpi <= 600:
        raise ValueError('Invalid target page, batch size or retries')
    engine = find_audiveris(audiveris)
    folder = Path(output).resolve() / f'movement-{movement["number"]:02d}'
    runs = folder / 'runs'
    runs.mkdir(parents=True, exist_ok=True)
    identity = {'pdf_sha256': manifest['pdf_sha256'], 'movement': movement,
                'audiveris_executable_sha256': digest(engine),
                'mode': 'native_pdf_book_v1' if native_pdf else 'raster_tiff_book_v1', 'dpi': dpi}
    identity_path = folder / 'identity.json'
    if identity_path.exists() and json.loads(identity_path.read_text(encoding='utf8')) != identity:
        raise ValueError('Output belongs to another input or engine; use another output directory')
    lock = folder / 'processing.lock'
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    active = folder / 'active-run.json'
    try:
        os.write(descriptor, str(os.getpid()).encode())
        write_json(identity_path, identity)
        write_json(folder / 'movement-report.json', {'status': 'preparing_images', 'movement': movement,
                   'completed_pages': [], 'musical_accuracy_verified': False})
        input_book = pdf if native_pdf else prepare_image_book(pdf, movement, folder, dpi,
                                                              manifest['pdf_sha256'])
        offset = 0 if native_pdf else start - 1
        env = os.environ.copy()
        state, temp, cache = ROOT / '.tools/audiveris-data', ROOT / 'tmp/java', ROOT / '.tools/javacpp'
        for path in (state / 'local', temp, cache):
            path.mkdir(parents=True, exist_ok=True)
        env.update(APPDATA=str(state), LOCALAPPDATA=str(state / 'local'))
        env['JAVA_TOOL_OPTIONS'] = (f'-Djava.io.tmpdir="{temp}" '
                                   f'-Dorg.bytedeco.javacpp.cachedir="{cache}"')
        snapshots = sorted(runs.glob('run-*'))
        last = Path(resume_book).resolve() if resume_book else None
        for snapshot in ([] if resume_book else snapshots):
            books = list(snapshot.glob('*.omr'))
            if books:
                try:
                    book_progress(books[0], start, end, offset)
                    last = books[0]
                except (OSError, zipfile.BadZipFile, ET.ParseError):
                    pass
        if last:
            progress = book_progress(last, start, end, offset)
            if Path(progress['book_source']).resolve() != input_book:
                raise ValueError('Resume book belongs to another PDF or normalized image book')
        else:
            progress = {'completed_pages': [], 'invalid_pages': []}
        pending = [n for n in range(start, target + 1) if n not in progress['completed_pages']]
        # Even an already processed book must be exported for this cumulative
        # selection; a prior limited export may contain only the earlier subset.
        stops = list(range((pending[0] if pending else target) + batch_size - 1,
                           target, batch_size)) + [target]
        sequence = max((int(p.name.split('-')[1]) for p in snapshots), default=0)
        for stop in stops:
            for retry in range(retries + 1):
                sequence += 1
                attempt = runs / f'run-{sequence:04d}'
                attempt.mkdir()
                input_path = input_book
                if last:
                    input_path = attempt / last.name
                    shutil.copy2(last, input_path)
                log = attempt / 'audiveris.log'
                run = {'folder': str(attempt), 'pid': os.getpid(), 'pages': [start, stop],
                       'sheet_page_offset': offset,
                       'started_utc': datetime.now(timezone.utc).isoformat()}
                write_json(active, run)
                report = {'status': 'running', 'movement': movement, 'target_page': target,
                          'completed_pages': progress['completed_pages'], 'run': run,
                          'musical_accuracy_verified': False}
                write_json(folder / 'movement-report.json', report)
                print(f'Movement {movement["number"]}: cumulative pages {start}-{stop}', flush=True)
                try:
                    selection = ['-sheets', f'{start-offset}-{stop-offset}', '-output', attempt]
                    # Stop before CHORDS so malformed leading empty measures
                    # can be repaired without touching recognized musical data.
                    run_command([engine, '-batch', '-step', 'MEASURES', '-save', '-swap',
                                 '-constant', f'org.audiveris.omr.image.ImageLoading.pdfResolution={dpi}',
                                 *selection, '--', input_path], attempt / 'prepare.log', env,
                                max(900, (stop - start + 1) * 300))
                    prepared = list(attempt.glob('*.omr'))
                    if len(prepared) != 1:
                        raise RuntimeError('Expected one prepared OMR book')
                    input_path = prepared[0]
                    from .omr_repair import repair_book
                    repaired = attempt / 'repairs' / input_path.name
                    correction = repair_book(input_path, repaired)
                    if correction:
                        backup = attempt / 'unrepaired'
                        backup.mkdir(exist_ok=True)
                        shutil.copy2(input_path, backup / input_path.name)
                        shutil.copy2(repaired, input_path)
                        report['structural_repairs'] = correction
                    run_command([engine, '-batch', '-transcribe', '-export', '-save', '-swap',
                                 '-constant', f'org.audiveris.omr.image.ImageLoading.pdfResolution={dpi}',
                                 *selection, '--', input_path],
                                log, env, max(900, (stop - start + 1) * 300))
                    books = list(attempt.glob('*.omr'))
                    if len(books) != 1:
                        raise RuntimeError('Expected one native OMR book')
                    last = books[0]
                    progress = book_progress(last, start, end, offset)
                    required = set(range(start, stop + 1))
                    if not required.issubset(progress['completed_pages']):
                        raise RuntimeError('One or more selected pages did not reach PAGE; see book/log')
                    mxls = sorted(attempt.glob('*.mxl'))
                    if not mxls:
                        raise RuntimeError('Native book produced no MusicXML export')
                    outputs = []
                    for mxl in mxls:
                        xml = mxl.with_suffix('.musicxml')
                        extract_musicxml(mxl, xml)
                        quality = inspect_musicxml(xml)
                        if not quality['structurally_valid']:
                            raise RuntimeError(f'Invalid MusicXML: {quality["errors"]}')
                        outputs.append({'mxl': str(mxl), 'musicxml': str(xml),
                                        'sha256': digest(mxl),
                                        'validation': quality})
                    log_text = log.read_text(encoding='utf8', errors='replace').splitlines()
                    status = 'partial_needs_review' if stop < end else (
                        'converted_needs_review' if len(outputs) == 1 else 'fragmented_needs_review')
                    report.update(status=status, **progress, omr=str(last), exports=outputs,
                                  source_pages_in_export=list(range(start, stop + 1)),
                                  export_fragment_count=len(outputs),
                                  engine_diagnostics=[line for line in log_text if any(s in line for s in
                                                      ('WARN ', 'ERROR ', 'no correct rhythm', 'No timeOffset'))])
                    write_json(attempt / 'result.json', report)
                    write_json(folder / 'movement-report.json', report)
                    active.unlink(missing_ok=True)
                    break
                except (OSError, ValueError, RuntimeError, KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
                    # Save the latest complete ZIP even after a failed export.
                    books = list(attempt.glob('*.omr'))
                    if books:
                        try:
                            progress = book_progress(books[0], start, end, offset)
                            last = books[0]
                        except (OSError, zipfile.BadZipFile, ET.ParseError):
                            pass
                    report.update(status='failed', error=str(exc), completed_pages=progress['completed_pages'])
                    write_json(attempt / 'failure.json', report)
                    write_json(folder / 'movement-report.json', report)
                    if retry == retries:
                        return report
        return report
    finally:
        os.close(descriptor)
        lock.unlink(missing_ok=True)
        active.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Transcribe or inspect a movement-native Audiveris book')
    parser.add_argument('--manifest', default=str(ROOT / 'works/mahler-7/movements.json'))
    parser.add_argument('--movement', type=int, default=1)
    parser.add_argument('--output', default=str(ROOT / 'output/omr/mahler7-by-movement'))
    parser.add_argument('--through-page', type=int, help='Optional staged target, physical PDF page')
    parser.add_argument('--batch-size', type=int, default=4)
    parser.add_argument('--retries', type=int, default=1)
    parser.add_argument('--audiveris')
    parser.add_argument('--dpi', type=int, default=450)
    parser.add_argument('--native-pdf', action='store_true', help='Debug: bypass TIFF normalization')
    parser.add_argument('--resume-book')
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        movement = next((m for m in manifest['movements'] if m['number'] == args.movement), None)
        if movement is None:
            raise ValueError('Unknown movement')
        if args.status:
            report = read_status(Path(args.output) / f'movement-{args.movement:02d}', movement)
        else:
            report = transcribe_movement(manifest, movement, args.output, args.through_page,
                                         args.batch_size, args.retries, args.audiveris, args.resume_book,
                                         args.dpi, args.native_pdf)
        print(json.dumps({'movement': args.movement, 'status': report['status'],
                          'completed_pages': len(report['completed_pages']),
                          'total_pages': movement['page_count'],
                          'export_fragment_count': report.get('export_fragment_count'),
                          'report': str(Path(args.output) / f'movement-{args.movement:02d}/movement-report.json')},
                         ensure_ascii=False))
        return 1 if report['status'] == 'failed' else 0
    except (OSError, ValueError, RuntimeError, KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        print(f'Movement conversion failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
