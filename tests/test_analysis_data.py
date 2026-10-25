import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from analysis_data import build_analysis,load_analysis,RENDER


class AnalysisImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.data=load_analysis(ROOT)

    def test_real_page_guide_covers_each_page_once(self):
        pages=[]
        for note in self.data['annotations']:
            pages.extend(range(note['start_pdf_page'],note['end_pdf_page']+1))
            self.assertEqual(note['locator_precision'],'source_pdf_page_range')
            self.assertEqual(note['review_status'],'unreviewed')
        self.assertEqual(pages,list(range(1,101)))
        self.assertEqual(len(self.data['annotations']),15)

    def test_reference_kinds_and_comparison_scope(self):
        refs=self.data['references']
        self.assertEqual(len(refs),8)
        self.assertEqual(refs[0]['doi_url'],'https://doi.org/10.30535/mto.11.3.3')
        self.assertEqual(refs[5]['kind'],'thesis')
        self.assertEqual(refs[2]['kind'],'programme_note')
        self.assertEqual(refs[7]['scope'],'comparison_other_work')
        self.assertEqual(refs[0]['reading_status'],'relevant_sections_checked')
        self.assertEqual(refs[1]['reading_status'],'relevant_sections_checked')
        self.assertEqual(refs[3]['reading_status'],'publisher_metadata_checked')
        self.assertEqual(refs[5]['reading_status'],'relevant_sections_checked')
        self.assertIn('Clare Hammond',refs[5]['citation_label'])

    def test_edited_listener_copy_has_no_research_instructions(self):
        notes=self.data['annotations']
        for note in notes:
            for phrase in ['核验任务','逐页检查','研究问题','不要未经','必须核对','建议聆听时比较']:
                self.assertNotIn(phrase,note['markdown'])
            self.assertEqual(note['editorial_status'],'finished_prose')
        by_start={n['start_pdf_page']:n for n in notes}
        self.assertIn('Allegro',by_start[33]['title'])
        self.assertEqual(by_start[91]['end_pdf_page'],94)
        self.assertEqual(by_start[100]['end_pdf_page'],100)

    def test_wrong_pdf_binding_is_rejected(self):
        metadata=json.loads((ROOT/'metadata/recording.json').read_text(encoding='utf-8'))
        mapping=json.loads((ROOT/'measure-map.json').read_text(encoding='utf-8'))
        alignment=json.loads((ROOT/'alignment.json').read_text(encoding='utf-8'))
        metadata=copy.deepcopy(metadata)
        metadata['analysis_document']['pdf_sha256']='different-score'
        with self.assertRaisesRegex(ValueError,'PDF'):
            build_analysis(ROOT/metadata['analysis_document']['path'],metadata,mapping,alignment)

    def test_rendered_markdown_escapes_raw_html_and_blocks_script_links(self):
        result=RENDER('<script>alert(1)</script>\n\n[link](javascript:alert%281%29)')
        self.assertNotIn('<script>',result)
        self.assertNotIn('href="javascript:',result)

    def test_new_work_reference_types_come_from_metadata(self):
        metadata=json.loads((ROOT/'metadata/recording.json').read_text(encoding='utf-8'))
        alignment=json.loads((ROOT/'alignment.json').read_text(encoding='utf-8'))
        metadata['work']['work_id']='a-different-work'
        metadata['analysis_document']['reference_metadata']={
            'analysis-ref-11-6':{'kind':'book','scope':'current_work'}}
        source=ROOT/'tmp/analysis-reference-fixture.md'
        source.write_text('# Different work\n\n## 9. 导聆\n### PDF 第 1 页：开头\n成稿。\n\n'
                          '## 11. 文献\n### 11.6 A book\n**Book**\n',encoding='utf-8')
        mapping={'pdf_sha256':metadata['analysis_document']['pdf_sha256'],'page_count':1,
                 'measures':[{'page_number':1,'measure_id':alignment['measures'][0]['measure_id']}]}
        result=build_analysis(source,metadata,mapping,alignment)
        self.assertEqual(result['references'][0]['kind'],'book')
        self.assertEqual(result['references'][0]['scope'],'current_work')


if __name__=='__main__': unittest.main()
