import assert from 'node:assert/strict';
import {test} from 'node:test';
import fs from 'node:fs';
import {movementChapters,chapterAtTime} from '../review/movements.mjs';

test('Mahler chapter jumps use real movement identities and score pages',()=>{
  const read=path=>JSON.parse(fs.readFileSync(new URL(path,import.meta.url)));
  const alignment=read('../works/mahler-4/alignment.json');
  const mapping=read('../works/mahler-4/measure-map.json');
  const chapters=movementChapters(alignment,mapping);
  assert.deepEqual(chapters.map(c=>c.first_pdf_page),[5,49,78,102]);
  for(const chapter of chapters){
    assert.equal(chapter.start_seconds,alignment.measures.find(m=>m.movement===chapter.movement).start_seconds);
    assert.equal(chapterAtTime(chapters,chapter.start_seconds).movement,chapter.movement);
  }
  assert.equal(chapterAtTime(chapters,chapters[1].start_seconds-.001).movement,1);
  assert.equal(chapterAtTime(chapters,3770).movement,4);
});

test('single movement works have no redundant chapter navigation',()=>{
  assert.deepEqual(movementChapters({measures:[{movement:1,start_seconds:0}]},{movements:[]}),[]);
  assert.deepEqual(movementChapters({measures:[{start_seconds:0}]},{}),[]);
});
