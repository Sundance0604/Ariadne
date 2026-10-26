"""Record a second-round comparison without modifying an independent snapshot."""
from .common import read,write,digest
from .store import validate_run


def record_comparison(root,run,input_path,output):
    root=root.resolve();run=run.resolve();output=output.resolve()
    if not run.is_relative_to(root) or not output.is_relative_to(root):
        raise ValueError('Comparison paths must stay inside the project')
    if output.is_relative_to(run):raise ValueError('Comparison cannot modify the independent round')
    if output.exists():raise ValueError('Preserve existing comparison; choose a new output')
    manifest=validate_run(run,root);document=read(input_path)
    categories={'agreement','disagreement','independent_unvalidated','unresolved'}
    if not categories<=document.keys():raise ValueError('Four comparison categories required')
    if not document.get('prior_exposure_statement'):raise ValueError('Disclose prior literature exposure')
    evidence_ids=set()
    for name in manifest['files']:
        data=read(run/name)
        for rows in data.values():
            if isinstance(rows,list):evidence_ids.update(r['id'] for r in rows if isinstance(r,dict) and 'id' in r)
    for category in categories:
        for claim in document[category]:
            if not claim.get('claim') or not set(claim.get('evidence_ids',[]))<=evidence_ids:
                raise ValueError('Comparison claim missing or cites unknown evidence')
    write(output,{'independent_run':run.relative_to(root).as_posix(),
        'independent_manifest_sha256':digest(run/'manifest.json'),
        'independent_run_id':manifest['run_id'],'comparison':document})
    return output
