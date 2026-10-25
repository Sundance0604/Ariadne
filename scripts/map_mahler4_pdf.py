"""Map observed Mahler 4 scan regions to the supplied MIDI note reference.

These are automatic candidates, not confirmed printed measure identities.
Geometry is measured from the original scan; reference times come from pitch
matching with variable metric lengths, never equal page/time subdivision.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'works/mahler-4'
os.environ.setdefault('NUMBA_CACHE_DIR',str(ROOT/'.tools/numba-cache'))


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_suffix(path.suffix+'.tmp')
    pending.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    pending.replace(path)


def publish(candidates,inputs):
    import pypdfium2 as pdfium
    mapping=json.loads((DATA/'measure-map.json').read_text(encoding='utf-8'))
    alignment=json.loads((DATA/'alignment.json').read_text(encoding='utf-8'))
    if mapping['pdf_sha256']!=inputs['pdf_sha256']:raise ValueError('PDF 指纹不匹配')
    offsets=[];offset=0
    for movement in json.loads((DATA/'midi-movements.json').read_text(encoding='utf-8')):
        offsets.append(offset);offset+=movement['duration_seconds']
    system_regions=[];bar_regions=[]
    with pdfium.PdfDocument(ROOT/mapping['pdf_path']) as pdf:
        for system in candidates:
            width,height=pdf[system['page']-1].get_size()
            left,right=system['boundaries'][0]/2,system['boundaries'][-1]/2
            top=max(0,system['top']/2-4);bottom=min(height,system['bottom']/2+4)
            start=system['match']['start']+offsets[system['movement']-1]
            end=system['match']['end']+offsets[system['movement']-1]
            spread=system['variant_disagreement_seconds']
            stable=system['match']['similarity']>=.5 and spread<=5
            region={'region_id':f"pdf-{system['page']:03d}-system-{system['system']}",
                'page_number':system['page'],'system_index':system['system'],
                'movement':system['movement'],'page_width_pt':width,'page_height_pt':height,
                'rect_pt':[left,top,right-left,bottom-top],
                'midi_start_seconds':start,'midi_end_seconds':end,'resolution':'system_candidate',
                'review_status':'unreviewed' if stable else 'needs_review','stable_candidate':stable,
                'printed_measure_number':None,
                'quality_metrics':{'diatonic_histogram_cosine':system['match']['similarity'],
                    'reference_boundary_variant_spread_seconds':spread},
                'evidence':{'method':'observed_staff_barlines_and_joint_string_noteheads_metric_dp',
                    'observed_bar_spans':len(system['match']['bars']),
                    'notehead_clusters':sum(b['heads'] for b in system['match']['bars'])}}
            system_regions.append(region)
            for i,bar in enumerate(system['match']['bars']):
                delta=max(abs(bar[k]-system[variant]['bars'][i][k])
                          for variant in ['comparison','prior_comparison'] for k in ['start','end'])
                # Finer rectangles are used only with stricter pitch support
                # and agreement. These remain inferred bar candidates.
                if bar['similarity']<.65 or delta>1 or bar['heads']<2:continue
                bar_regions.append({**region,'region_id':region['region_id']+f'-bar-{i}',
                    'parent_region_id':region['region_id'],'image_bar_index':i,
                    'rect_pt':[bar['x0']/2,top,(bar['x1']-bar['x0'])/2,bottom-top],
                    'midi_start_seconds':bar['start']+offsets[system['movement']-1],
                    'midi_end_seconds':bar['end']+offsets[system['movement']-1],
                    'resolution':'bar_candidate','stable_candidate':True,'review_status':'unreviewed',
                    'quality_metrics':{'diatonic_histogram_cosine':bar['similarity'],
                        'reference_boundary_variant_spread_seconds':delta},
                    'evidence':{'method':'observed_bar_rectangle_with_metric_notehead_match',
                        'notehead_clusters':bar['heads'],'meter_length_is_inferred':True}})
    mapping.update(format_version='1.1.0',status='algorithmic_score_region_candidates',
        symbolic_reference_sha256=alignment['symbolic_reference']['sha256'],
        score_regions=system_regions,bar_regions=bar_regions,
        algorithm={'name':'scan notehead / variable-metric pitch-histogram DP',
            'render_scale':2,'notehead_thresholds':[.60,.64],'metric_penalties':[.25,.4],
            'system_stability_rule':'cosine >= .5, reference boundary variants <= 5s',
            'bar_stability_rule':'cosine >= .65, variants <= 1s, >= 2 notehead clusters',
            'metric_lengths':'inferred from joint note evidence with meter prior and total MIDI quarter duration',
            'human_verified_regions':0},
        limitations=['全部位置均为自动候选，未完成人工逐音验收。',
            'MIDI 固定拍号不能当作原谱小节号；不显示未经核实的印刷编号。',
            '只识别音符头的音级轮廓，调号、临时变音、谱号歧义与长休止会造成偏差。',
            '总参考时值是算法边界约束；局部拍号长度来自推断，并非全部已由图像读出。',
            '稳定表示本轮几种参数下边界较一致，不是准确率或人工确认。'])
    save(DATA/'measure-map.json',mapping)
    for measure in alignment['measures']:
        if measure.get('review_status') in {'verified','corrected'}:continue
        measure['pdf_mapping_status']='reference_time_score_region_candidate'
        measure['flags']=[f for f in measure['flags'] if f!='pdf_coordinate_missing']
        if 'pdf_region_boundary_candidate' not in measure['flags']:measure['flags'].append('pdf_region_boundary_candidate')
    alignment['quality']['flag_counts']=dict(Counter(f for m in alignment['measures'] for f in m['flags']))
    alignment['limitations']=[v for v in alignment.get('limitations',[]) if not v.startswith('No per-measure PDF coordinates')]
    alignment['limitations']=list(dict.fromkeys(alignment['limitations']+mapping['limitations']))
    save(DATA/'alignment.json',alignment)
    report={'inputs':inputs,'systems':len(system_regions),'finer_bar_candidates':len(bar_regions),
        'stable_system_candidates':sum(r['stable_candidate'] for r in system_regions),
        'needs_review_system_candidates':sum(not r['stable_candidate'] for r in system_regions),
        'mapped_pdf_pages':len({r['page_number'] for r in system_regions}),
        'human_verified_regions':0,'movement_counts':dict(Counter(r['movement'] for r in system_regions)),
        'limitations':mapping['limitations']}
    save(DATA/'reports/score-region-validation.json',report)
    project_path=DATA/'project.json'
    if project_path.exists():
        project=json.loads(project_path.read_text(encoding='utf-8'))
        project.setdefault('processing_status',{})['pdf_bar_coordinates']='algorithmic_system_and_selected_bar_candidates'
        project['score_region_counts']={k:report[k] for k in ['systems','finer_bar_candidates','stable_system_candidates','needs_review_system_candidates','human_verified_regions']}
        save(project_path,project)
    print(json.dumps(report,ensure_ascii=True))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adopt-experiment-cache',type=Path,help='Reuse this session\'s local feature experiments')
    args=parser.parse_args()
    pdf=next((ROOT/'resource/mahler No.4').glob('*.pdf'))
    midis=sorted((ROOT/'resource/mahler No.4').glob('*.mid'))
    inputs={'pdf_sha256':digest(pdf),'midis':[{'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p)} for p in midis]}
    key=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:20]
    cache=ROOT/'.tools/mahler4-score'/key;cache.mkdir(parents=True,exist_ok=True)
    os.environ['MAHLER4_SCORE_CACHE']=str(cache)
    if args.adopt_experiment_cache:
        source=args.adopt_experiment_cache.resolve()
        if not source.is_relative_to(ROOT/'tmp'):raise ValueError('仅能复用本项目 tmp 内的实验缓存')
        for filename in ['note-tokens.json','poly-tokens.json']:
            shutil.copyfile(source/filename,cache/filename)
    save(cache/'inputs.json',inputs)
    from mahler4_score import geometry,notes,features,metric
    if not (cache/'note-tokens.json').exists():
        import numpy as np
        import pypdfium2 as pdfium
        records=[]
        with pdfium.PdfDocument(pdf) as document:
            for number in range(5,len(document)+1):
                page=document[number-1];array=np.asarray(page.render(scale=2).to_pil().convert('L'))
                for index,system in enumerate(geometry.extract(page)):
                    heads,staff=notes.noteheads(array,system)
                    records.append({'page':number,'system':index,**system,'notes':heads,'staff':staff})
                print('Geometry / bass noteheads',number,flush=True)
        save(cache/'note-tokens.json',records)
    if not (cache/'poly-tokens.json').exists():features.extract_all()
    metric.main()
    candidates=json.loads((cache/'metric-alignment.json').read_text(encoding='utf-8'))
    publish(candidates,inputs)


if __name__=='__main__':main()
