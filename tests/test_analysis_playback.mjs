import assert from 'node:assert/strict';
import {test} from 'node:test';
import {annotationForPlayback,annotationRangeLabel} from '../review/analysis.mjs';
import fs from 'node:fs';

test('movement guide follows playback sequence even while another PDF page is browsed',()=>{
  const notes=[{annotation_id:'one',start_sequence_index:1,end_sequence_index:355,start_pdf_page:5,end_pdf_page:48},
    {annotation_id:'two',start_sequence_index:356,end_sequence_index:737,start_pdf_page:49,end_pdf_page:77}];
  assert.equal(annotationForPlayback(notes,60,25).annotation_id,'one');
  assert.equal(annotationForPlayback(notes,5,400).annotation_id,'two');
  assert.equal(annotationForPlayback(notes,null,400).annotation_id,'two');
  assert.equal(annotationForPlayback(notes,5,null),undefined);
});

test('short Mahler guides follow the visible score with separate paragraphs on the same page',()=>{
  const {annotations:notes}=JSON.parse(fs.readFileSync(new URL('../works/mahler-4/analysis/annotations.json',import.meta.url)));
  assert.match(annotationForPlayback(notes,5,900,{system_index:0,x_pt:300}).title,/铃声/);
  assert.match(annotationForPlayback(notes,5,900,{system_index:0,x_pt:550}).title,/主部/);
  assert.match(annotationForPlayback(notes,80,1,{system_index:0,x_pt:400}).title,/安宁/);
  assert.match(annotationForPlayback(notes,80,1,{system_index:0,x_pt:450}).title,/哀诉/);
  assert.match(annotationForPlayback(notes,80,1,{system_index:1,x_pt:100}).title,/哀诉/);
  assert.match(annotationForPlayback(notes,112,1,{system_index:0,x_pt:300}).title,/铃声/);
  assert.match(annotationForPlayback(notes,112,1,{system_index:0,x_pt:340}).title,/羔羊/);
  assert.match(annotationForPlayback(notes,115,1,{system_index:0,x_pt:200}).title,/间奏/);
  assert.match(annotationForPlayback(notes,115,1,{system_index:0,x_pt:300}).title,/花园/);
  assert.equal(annotationForPlayback(notes,4,1),undefined);
  assert.equal(annotationForPlayback(notes,128,1),undefined);
});
test('existing page-based guides stay compatible and movement labels disclose granularity',()=>{
  const notes=[{start_pdf_page:1,end_pdf_page:3,title:'opening'}];
  assert.equal(annotationForPlayback(notes,2,25).title,'opening');
  assert.equal(annotationForPlayback(notes,null,25),undefined);
  assert.match(annotationRangeLabel({...notes[0],locator_precision:'movement_range'}),/整乐章导聆/);
  assert.equal(annotationRangeLabel(notes[0]),'谱面第 1–3 页');
});
