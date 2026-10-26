"""MusicXML/PDF layout links; note containment is not notehead recognition."""
from collections import Counter
from fractions import Fraction as F
from .ingest import xml_root


def build_mapping(data, mapping, xml_sha, pdf_sha, studies, root=None):
    by_number={str(m['printed_measure_number']):m for m in mapping['measures'] if m.get('printed_measure_number') is not None}
    links=[];differences=[];adjustments=[]
    # Single-staff cadenza systems were deliberately not split by the older
    # MIDI navigation adapter. Extract their actual PDF lines independently.
    extra={}
    if root is not None:
        import pdfplumber
        from pathlib import Path
        missing=[m for m in data['measures'] if m['number'] not in by_number]
        with pdfplumber.open(Path(root)/mapping['pdf_path']) as document:
            for page_number in {m['page'] for m in missing}:
                page=document.pages[page_number-1];words=page.extract_words()
                horizontal=[l for l in page.lines if l['height']<.05 and l['width']>100]
                stroke=Counter(round(l.get('linewidth',0),3) for l in horizontal).most_common(1)[0][0]
                horizontal=[l for l in horizontal if abs(l.get('linewidth',0)-stroke)<.002]
                starts=[m for m in data['measures'] if m['page']==page_number and
                    (m['sequence']==1 or data['measures'][m['sequence']-2]['system_index']!=m['system_index'] or data['measures'][m['sequence']-2]['page']!=page_number)]
                for start in starts:
                    members=[m for m in data['measures'] if m['page']==page_number and m['system_index']==start['system_index']]
                    if not any(m in missing for m in members):continue
                    labels=[w for w in words if w['text']==start['number'] and w['x0']<150]
                    if len(labels)!=1:continue
                    label=labels[0]
                    next_labels=[w for w in words if w['text'].isdigit() and w['x0']<150 and float(w['top'])>float(label['top'])+30 and w['text'] in {s['number'] for s in starts}]
                    bottom_limit=min((w['top'] for w in next_labels),default=page.height)
                    staff=[l for l in horizontal if label['bottom']<l['top']<bottom_limit-4]
                    if not staff:continue
                    top=min(l['top'] for l in staff);bottom=max(l['bottom'] for l in staff)
                    left=min(l['x0'] for l in staff);right=max(l['x1'] for l in staff)
                    xs=[left,right]+[l['x0'] for l in page.lines if l['width']<.05 and l['height']>(bottom-top)*.7
                        and l['top']>=top-1 and l['bottom']<=bottom+1]
                    groups=[]
                    for x in sorted(xs):
                        if groups and x-groups[-1][-1]<5:groups[-1].append(x)
                        else:groups.append([x])
                    xs=[sum(g)/len(g) for g in groups]
                    exact=len(xs)==len(members)+1
                    for j,m in enumerate(members):
                        x0,x1=(xs[j],xs[j+1]) if exact else (left,right)
                        extra[m['measure_id']]={'page_number':page_number,'system_index':m['system_index'],
                            'rect_pt':[x0,top,x1-x0,bottom-top],'page_width_pt':page.width,'page_height_pt':page.height,
                            'measure_id':None,'resolution':'bar' if exact else 'shared_unbarred_system',
                            'observed_printed_system_start':start['number']}
    for measure in data['measures']:
        region=by_number.get(measure['number'])
        if region is None:
            region=extra.get(measure['measure_id'])
            if region is None:
                # Page 10's single unbarred source region is still valid for
                # XML m33; never reuse it for m34–36 on the following page.
                region=next((r for r in mapping['measures'] if r.get('candidate_sequence_number')==measure['sequence'] and r['page_number']==measure['page']),None)
        agrees=region and region['page_number']==measure['page']
        if region and (region.get('measure_id') is None or region['system_index']!=measure['system_index']):
            adjustments.append({'measure_id':measure['measure_id'],'xml_system':measure['system_index'],
                'legacy_system':region['system_index'],'basis':'source PDF printed system number and single-staff cadenza lines',
                'new_geometry':region.get('measure_id') is None})
        if not agrees:differences.append({'measure_id':measure['measure_id'],'xml_page':measure['page'],
            'xml_system':measure['system_index'],'pdf_region':region})
        links.append({'measure_id':measure['measure_id'],'xml_number':measure['number'],
            'region_id':f'xml-pdf-{measure["measure_id"]}',
            'page_number':region['page_number'] if region else None,'system_index':measure['system_index'],
            'rect_pt':region['rect_pt'] if region else None,
            'page_width_pt':region['page_width_pt'] if region else None,'page_height_pt':region['page_height_pt'] if region else None,
            'status':'layout_agrees_note_contents_sampled' if agrees else 'unresolved',
            'basis':'XML measure number + XML page/system breaks + PDF printed numbering and vector geometry; no MIDI note matching',
            'precision':'shared_unbarred_system' if region and region.get('resolution')=='shared_unbarred_system' else 'measure_region_not_notehead',
            'legacy_geometry_id':region['measure_id'] if region else None})
    events=data['events'];sample_checks=[]
    tests=[('opening-cello-D','P32',1,F(0),'D2'),('opening-cello-G','P32',1,F(0),'G2'),
        ('opening-bass-E','P36',1,F(0),'E1'),('opening-bass-A','P36',1,F(0),'A1'),
        ('horn-upper-10','P10',10,F(0),'A3'),('horn-upper-11','P10',11,F(0),'E4'),
        ('bassoon-11','P8',11,F(1),'Bb2'),('contra-E-pedal','P9',11,F(0),'E1'),
        ('violin-return-64','P27',64,F(0),'G#4')]
    for label,part,seq,onset,pitch in tests:
        found=[e for e in events if e['part_id']==part and e['measure_sequence']==seq and F(e['onset_q'])==onset
               and e['analysis_eligible'] and e['concert_pitch']['name']==pitch]
        sample_checks.append({'id':label,'status':'agrees' if found else 'disagrees','expected':{'part':part,'sequence':seq,
            'onset_q':str(onset),'concert_pitch':pitch},'event_ids':[e['id'] for e in found],
            'evidence':'agent-transcribed score windows in analysis/score-studies/ravel-study-20261026.json; not human signoff'})
    by_mid={x['measure_id']:x for x in links}
    note_links=[{'event_id':e['id'],'measure_id':e['measure_id'],'region_id':by_mid[e['measure_id']]['region_id'],
        'precision':'measure_containment_not_individual_notehead'} for e in events]
    return {'xml_sha256':xml_sha,'pdf_sha256':pdf_sha,'coordinate_origin':'top_left','measures':links,
        'note_links':note_links,'edition_audit':{'xml_measures':len(data['measures']),
            'xml_pages':max(m['page'] for m in data['measures']), 'pdf_pages':max(m['page_number'] for m in mapping['measures']),
            'xml_systems':len({(m['page'],m['system_index']) for m in data['measures']}),
            'layout_difference_count':len(differences),'layout_differences':differences,'geometry_adjustments':adjustments,'score_window_checks':sample_checks,
            'checked_pdf_pages':[1,3,15,33,51,95,100],
            'status':'compatible_layout_with_local_content_checks_not_critical_edition_equivalence',
            'limitations':['Full note-by-note PDF collation not performed.','MuseScore source is a transcription, not a critical edition.',
                'Invisible notehead events are quarantined, retained in the raw event table and excluded from analysis.',
                'XML note default-x/y remain original engraving coordinates; no fabricated PDF notehead rectangles.']}}
