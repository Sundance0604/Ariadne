"""Map the supplied Lark vector engraving, retaining shared cadenza regions."""
from pathlib import Path
from collections import Counter, defaultdict
import hashlib
import json
import pdfplumber
from map_pdf import merged

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'works/lark-ascending'
PDF = ROOT / 'resource/Lark Ascending/lark-ascending.pdf'


def extract_page(page, number):
    horizontal = [l for l in page.lines if l['height'] < .05 and l['width'] > 30]
    stroke = Counter(round(l.get('linewidth', 0), 3) for l in horizontal).most_common(1)[0][0]
    horizontal = [l for l in horizontal if abs(l['linewidth'] - stroke) < .002]
    vertical = [l for l in page.lines if l['width'] < .05 and l['height'] > 10
                and .6 <= l.get('linewidth', 0) <= 3]
    words = page.extract_words()
    labels = []
    for w in words:
        if not (w['text'].isdigit() and w['x0'] < 90 and w['top'] < 780): continue
        near = [l for l in horizontal if 8 < l['top']-w['top'] < 18
                and -15 < w['x0']-l['x0'] < 6]
        if near: labels.append((w,min(l['top'] for l in near)))
    if number == 1: labels = [(dict(text='1'),min(l['top'] for l in horizontal))]
    labels.sort(key=lambda x:x[1])
    result = []
    for index, (label,top) in enumerate(labels):
        cutoff = labels[index+1][0]['top'] if index+1 < len(labels) else 780
        staff = [l for l in horizontal if top-1 <= l['top'] < cutoff]
        if not staff: continue
        bottom = max(l['top'] for l in staff)
        left = min(l['x0'] for l in staff)
        right = max(l['x1'] for l in page.lines if l['height']<.05 and
                    abs(l['linewidth']-stroke)<.002 and top-1<=l['top']<=bottom+1)
        groups = defaultdict(list)
        for line in vertical:
            if line['top'] >= top-1 and line['bottom'] <= bottom+1:
                groups[round(line['x0'],1)].append((line['top'],line['bottom']))
        candidates = [x for x, spans in groups.items()
                      if sum(b-t for t,b in merged(spans)) > (bottom-top)*.35]
        boundaries = []
        for x in sorted(candidates):
            if boundaries and x-boundaries[-1][-1] < 5: boundaries[-1].append(x)
            else: boundaries.append([x])
        xs = [sum(g)/len(g) for g in boundaries]
        start = int(label['text'])
        result.append(dict(page_number=number,system_index=index,top=top,bottom=bottom,
                           left=left,right=right,page_width=page.width,page_height=page.height,
                           printed_start_measure=start,boundaries=xs,
                           label_candidates=[label['text']]))
    return result


def main():
    systems = []
    with pdfplumber.open(PDF) as document:
        for i,p in enumerate(document.pages): systems.extend(extract_page(p,i+1))
        actual_page_count = len(document.pages)
    DATA.joinpath('reports').mkdir(parents=True,exist_ok=True)
    DATA.joinpath('reports/pdf-systems-probe.json').write_text(json.dumps(systems,indent=2),encoding='utf8')
    # Independently matched solo-note contours locate the regular sections at
    # MIDI +4, +7 and +11 offsets. Unbarred cadenzas retain shared rectangles.
    # These are region candidates, never an equal-width subdivision of cadenzas.
    grouped={
        (1,0):(1,9),(2,0):(10,12),(2,1):(13,15),
        (3,0):(16,18),(3,1):(19,25),(3,2):(26,33),
        (10,1):(95,100),(11,0):(101,106),
        (27,0):(215,228),(28,0):(229,239),
        (34,1):(285,289),(35,0):(290,292),(35,1):(293,295),
        (35,2):(296,299),(35,3):(300,301),(35,4):(302,304),(35,5):(305,309),
    }
    measures=[]
    issues=[]
    for s in systems:
        key=(s['page_number'],s['system_index'])
        if key in grouped:
            first,last=grouped[key]
            resolution='system_candidate' if s['page_number'] in {27,28,34} else 'cadenza_region'
            if key==(1,0):
                regions=[(1,1,s['boundaries'][0],s['boundaries'][1],'bar','1'),
                         (2,2,s['boundaries'][1],s['boundaries'][2],'bar','2'),
                         (3,9,s['boundaries'][2],s['right'],'cadenza_region',None)]
            else:
                regions=[(first,last,s['left'],s['right'],resolution,None)]
            issues.append(dict(page=s['page_number'],system=s['system_index'],
                               reason='shared_region_not_note_verified',midi_candidates=[first,last]))
        else:
            offset=4 if s['printed_start_measure']<91 else 7 if s['printed_start_measure']<208 else 11
            first=s['printed_start_measure']+offset
            nexts=next((t for t in systems if t['printed_start_measure']>s['printed_start_measure']),None)
            count=nexts['printed_start_measure']-s['printed_start_measure'] if nexts else len(s['boundaries'])-1
            if len(s['boundaries'])!=count+1:
                raise ValueError(f'Unexpected barline count on page {s["page_number"]}: {len(s["boundaries"])-1} != {count}')
            regions=[(first+i,first+i,x0,x1,'bar',str(s['printed_start_measure']+i))
                     for i,(x0,x1) in enumerate(zip(s['boundaries'],s['boundaries'][1:]))]
        for first,last,x0,x1,resolution,printed in regions:
            x0=max(0,x0);x1=min(s['page_width'],x1)
            for candidate in range(first,last+1):
                measures.append(dict(measure_id=f'midi-m{candidate:04d}',
                    printed_measure_number=printed,candidate_sequence_number=candidate,
                    page_number=s['page_number'],system_index=s['system_index'],
                    rect_pt=[x0,s['top'],x1-x0,s['bottom']-s['top']],
                    page_width_pt=s['page_width'],page_height_pt=s['page_height'],
                    coordinate_origin='top_left',review_status='needs_review' if resolution!='bar' else 'unreviewed',
                    resolution=resolution,method='vector_barlines_printed_labels_and_solo_diatonic_correspondence',
                    score_event_correspondence='candidate_contour_and_meter_mapping_not_fully_note_verified'))
    measures.sort(key=lambda m:m['candidate_sequence_number'])
    assert [m['candidate_sequence_number'] for m in measures]==list(range(1,310))
    result=dict(format_version='1.0.0',pdf_path=PDF.relative_to(ROOT).as_posix(),
                pdf_sha256=hashlib.sha256(PDF.read_bytes()).hexdigest(),page_count=actual_page_count,
                is_omr=False,systems=systems,measures=measures,issues=issues,
                note_correspondence_report='works/lark-ascending/reports/pdf-note-correspondence.json',
                limitations=['Mapping uses supplied MIDI and vector geometry, not full PDF OMR.',
                    'MIDI candidate numbers and PDF printed numbers differ in unbarred passages.',
                    'Shared cadenza/system regions are candidates requiring human score/listening review.',
                    'Pages 27–28 contain additional MIDI segmentation; page boundary remains a contour-derived candidate.',
                    'No claim of note-level, beat-level or human-verified synchronization.'])
    (DATA/'measure-map.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    alignment_path=DATA/'alignment.json'
    alignment=json.loads(alignment_path.read_text())
    by_id={m['measure_id']:m for m in measures}
    for m in alignment['measures']:
        mapping=by_id[m['measure_id']]
        m['pdf_mapping_status']='candidate_ready'
        m['printed_measure_number']=mapping['printed_measure_number']
        if mapping['resolution']!='bar':
            if 'shared_pdf_region_requires_review' not in m['flags']:m['flags'].append('shared_pdf_region_requires_review')
            m['review_status']='needs_review'
        if mapping['page_number'] in {27,28}:
            if 'pdf_region_boundary_candidate' not in m['flags']:m['flags'].append('pdf_region_boundary_candidate')
            m['review_status']='needs_review'
    alignment['quality']['flag_counts']=dict(Counter(f for m in alignment['measures'] for f in m['flags']))
    alignment_path.write_text(json.dumps(alignment,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(f'{len(systems)} systems; {len(measures)} candidate regions; 35 pages')


if __name__ == '__main__': main()
