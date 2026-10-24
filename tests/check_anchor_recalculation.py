"""Real-input integration check with a synthetic constraint, never human truth."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime

ROOT=Path(__file__).resolve().parents[1]
project=json.loads((ROOT/'alignment.json').read_text(encoding='utf-8'))
measure=project['measures'][36]
fixture={'format_version':'1.0.0','audio_sha256':project['audio']['sha256'],
    'score_sha256':project['symbolic_reference']['sha256'],
    'anchors':[{'measure_id':measure['measure_id'],'midi_seconds':measure['midi_start_seconds'],
        'audio_seconds':measure['start_seconds']+.1,'source':'automated_test_fixture',
        'reason':'Synthetic constraint for software testing; not listening ground truth'}],
    'history':[{'source':'automated_test_fixture','reason':'Synthetic constraint only'}]}
anchor_file=ROOT/'tmp/test-anchors.json'
anchor_file.write_text(json.dumps(fixture),encoding='utf-8')
output=Path('tmp')/('alignment-anchor-test-'+datetime.now().strftime('%H%M%S')+'.json')
command=[sys.executable,str(ROOT/'scripts/align_recording.py'),
         '--anchors',str(anchor_file),'--output',str(output)]
with (ROOT/'reports/anchor-recalculation-test.log').open('w',encoding='utf-8') as log:
    run=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
assert run.returncode==0,'Alignment run failed; inspect reports/anchor-recalculation-test.log'
output=ROOT/output
result=json.loads(output.read_text(encoding='utf-8'))
assert abs(result['measures'][36]['start_seconds']-fixture['anchors'][0]['audio_seconds'])<1e-8
assert result['measures'][36]['review_status']=='corrected'
assert result['correction_history']==fixture['history']
assert result['quality']['monotone_path']
before=hashlib.sha256(output.read_bytes()).hexdigest()
retry=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
assert retry.returncode!=0 and hashlib.sha256(output.read_bytes()).hexdigest()==before
report={'synthetic_constraint_not_human_ground_truth':True,'real_inputs_used':True,
    'exact_anchor_preserved':True,'history_preserved':True,'monotone_path':True,
    'overwrite_protection':True,'relative_output_path_supported':True,
    'output':output.relative_to(ROOT).as_posix(),'runtime_seconds':result['runtime']['elapsed_seconds']}
(ROOT/'reports/anchor-recalculation-test.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
