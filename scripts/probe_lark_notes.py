"""Extract solo staff diatonic contours for note/PDF correspondence diagnostics."""
from pathlib import Path
import json
import pdfplumber
from map_lark_pdf import extract_page, PDF, DATA


def main():
    all_notes = []
    with pdfplumber.open(PDF) as document:
        for number,page in enumerate(document.pages,1):
            systems = extract_page(page,number)
            brackets = sorted([c for c in page.chars if c['text']=='\ue003'],key=lambda c:c['top'])
            rows=sorted(set(round(l['top'],2) for l in page.lines
                            if l['height']<.05 and l['width']>30 and abs(l['linewidth']-.309337)<.002))
            groups=[]
            for y in rows:
                if groups and y-groups[-1][-1]<4.5: groups[-1].append(y)
                else:groups.append([y])
            staves=[(g[0],g[-1]) for g in groups if len(g)==5]
            for sys,bracket in zip(systems,brackets):
                stafftop = bracket['top']-12.47
                chars = [c for c in page.chars if c['text'] in {'\ue0a3','\ue0a4'}
                         and stafftop-23 < c['top'] < stafftop+48]
                def distance(head,staff): return max(staff[0]-head,head-staff[1],0)
                chars = [c for c in chars if abs(min(staves,key=lambda st:distance(c['top']-13.5,st))[0]-stafftop)<1]
                chars.sort(key=lambda c:(c['x0'],c['top']))
                for c in chars:
                    diatonic = 38-round((c['top']-stafftop-13.5)/(15.4669/8))
                    all_notes.append(dict(page_number=number,system_index=sys['system_index'],
                                          x=c['x0'],y=c['top'],diatonic=diatonic,
                                          printed_system_start=sys['printed_start_measure']))
    DATA.joinpath('reports/pdf-solo-notes.json').write_text(json.dumps(all_notes,indent=2),encoding='utf8')
    print(len(all_notes),'solo notehead glyphs')


if __name__=='__main__':main()
