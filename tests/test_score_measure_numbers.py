"""Physical score numbering, provenance and reversible user corrections."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import threading
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from score_measure_data import apply_numbering,geometry_digest,load_score_measures,update_numbering
import serve_review


def fixture():
    measures=[{'region_id':f'r{i}','movement':1 if i<4 else 2,'page_number':5+i,
        'system_index':0,'rect_pt':[10,10,100,100]} for i in range(6)]
    return {'pdf_sha256':'pdf','geometry_sha256':geometry_digest(measures),'measures':measures}


class NumberingTests(unittest.TestCase):
    def request(self,doc,**kwargs):
        return {'pdf_sha256':doc['pdf_sha256'],'geometry_sha256':doc['geometry_sha256'],
            'region_id':'r1','start_number':10,'count_span':1,'reason':'Fixture only, checked source',
            'confirmed':True,**kwargs}

    def test_counting_resets_per_movement_and_manual_anchor_propagates(self):
        doc=fixture();self.assertEqual([m['score_measure_number'] for m in apply_numbering(doc)['measures']],[1,2,3,4,1,2])
        old=update_numbering(doc,None,self.request(doc))
        result=apply_numbering(doc,old)
        self.assertEqual([m['score_measure_number'] for m in result['measures']],[1,10,11,12,1,2])
        self.assertEqual(result['measures'][1]['numbering_status'],'corrected')
        self.assertEqual(result['measures'][2]['numbering_status'],'inferred')
        self.assertEqual(doc,fixture())

    def test_pickup_continuation_multibar_rest_and_later_anchor(self):
        doc=fixture();old=update_numbering(doc,None,self.request(doc,region_id='r0',start_number=0))
        self.assertEqual([m['score_measure_number'] for m in apply_numbering(doc,old)['measures']][:4],[0,1,2,3])
        old=update_numbering(doc,old,self.request(doc,region_id='r1',start_number=1,count_span=0))
        old=update_numbering(doc,old,self.request(doc,region_id='r2',start_number=1,count_span=3))
        self.assertEqual([m['score_measure_number'] for m in apply_numbering(doc,old)['measures']][:4],[0,1,1,4])
        old=update_numbering(doc,old,self.request(doc,region_id='r3',start_number=8))
        self.assertEqual(apply_numbering(doc,old)['measures'][3]['score_measure_number'],8)

    def test_invalid_and_stale_edits_are_rejected_without_mutating_history(self):
        doc=fixture();old=update_numbering(doc,None,self.request(doc));before=deepcopy(old)
        for changes in [{'pdf_sha256':'other'},{'geometry_sha256':'other'},{'region_id':'missing'},
                        {'start_number':True},{'start_number':-1},{'start_number':1.5},{'count_span':101},
                        {'count_span':float('nan')},{'confirmed':False},{'reason':''},
                        {'region_id':'r3','start_number':9},{'region_id':'r3','start_number':11}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):update_numbering(doc,old,self.request(doc,**changes))
        self.assertEqual(old,before)
        saved=update_numbering(doc,old,self.request(doc,start_number=11))
        self.assertEqual(saved['history'][-1]['old_anchor']['start_number'],10)

    def test_real_index_covers_score_and_does_not_turn_rehearsal_figures_into_bars(self):
        mapping=json.loads((ROOT/'works/mahler-4/measure-map.json').read_text(encoding='utf-8'))
        data=load_score_measures(ROOT/'works/mahler-4',mapping)
        self.assertEqual({m['page_number'] for m in data['measures']},set(range(5,128)))
        self.assertGreater(len(data['measures']),1000)
        self.assertEqual(len({m['region_id'] for m in data['measures']}),len(data['measures']))
        self.assertFalse(any(m['page_number']==124 and m['system_index']==2 for m in data['measures']))
        self.assertTrue(all(m['printed_measure_number'] is None for m in data['measures']))
        self.assertTrue(all(not m['is_measure_number_anchor'] for m in data['landmarks']))
        for movement in range(1,5):
            self.assertEqual(next(m for m in data['measures'] if m['movement']==movement)['score_measure_number'],1)
        for m in data['measures']:
            x,y,w,h=m['rect_pt'];self.assertTrue(0<=x<x+w<=m['page_width_pt']+1)
            self.assertTrue(0<=y<y+h<=m['page_height_pt']+1)
            self.assertEqual(m['label_ink_density'],0)
        stale=deepcopy(mapping);stale['score_regions'][0]['midi_start_seconds']+=1
        with self.assertRaisesRegex(ValueError,'匹配已更新'):load_score_measures(ROOT/'works/mahler-4',stale)

    def test_http_corrections_are_persistent_bound_and_support_numbered_region_times(self):
        directory=ROOT/'tmp'/('numbering-test-'+uuid.uuid4().hex);directory.mkdir(parents=True)
        doc=fixture()
        for filename,value in {
            'library.json':{'default_track':'fixture','tracks':[{'id':'fixture','title':'Fixture','data_root':'.'}]},
            'alignment.json':{'audio':{'sha256':'audio','duration_seconds':30}},
            'measure-map.json':{'pdf_sha256':'pdf','page_count':10,'score_regions':[],'bar_regions':[]},
            'score-measures.json':doc}.items():
            (directory/filename).write_text(json.dumps(value),encoding='utf-8')
        previous=serve_review.ROOT;serve_review.ROOT=directory
        server=serve_review.ReviewServer(('127.0.0.1',0),serve_review.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_port}'
        def post(body,route='/api/score-measure-number',origin=None):
            headers={'Content-Type':'application/json'}
            if origin:headers['Origin']=origin
            return urlopen(Request(base+route+'?track=fixture',data=json.dumps(body).encode(),headers=headers,method='POST'))
        request={**self.request(doc),'track_id':'fixture'}
        try:
            with post(request) as response:payload=json.load(response)
            self.assertEqual(payload['score_measures']['measures'][2]['score_measure_number'],11)
            with post({**request,'start_number':12}) as response:json.load(response)
            path=directory/'score-measure-corrections.json';saved=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(len(saved['history']),2);before=path.read_bytes()
            for change in [{'track_id':'other'},{'pdf_sha256':'other'},{'geometry_sha256':'other'},
                           {'confirmed':False},{'count_span':-1},{'region_id':'missing'}]:
                with self.subTest(change=change),self.assertRaises(HTTPError) as error:post({**request,**change})
                self.assertEqual(error.exception.code,400);error.exception.close();self.assertEqual(path.read_bytes(),before)
            with self.assertRaises(HTTPError) as error:post(request,origin='https://other.example')
            self.assertEqual(error.exception.code,403);error.exception.close()
            timing={'track_id':'fixture','audio_sha256':'audio','pdf_sha256':'pdf','region_id':'r1',
                    'start_seconds':5,'end_seconds':9,'reason':'Fixture only','confirmed':True}
            with post(timing,'/api/score-region-anchor') as response:self.assertTrue(json.load(response)['saved'])
            with urlopen(base+'/api/project?track=fixture') as response:payload=json.load(response)
            self.assertEqual(payload['score_measures']['measures'][1]['score_measure_number'],12)
            self.assertEqual(payload['score_region_anchors']['anchors'][0]['region_id'],'r1')
        finally:
            server.shutdown();server.server_close();worker.join();serve_review.ROOT=previous


if __name__=='__main__':unittest.main()
