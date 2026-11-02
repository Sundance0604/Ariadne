"""Export a one-row-per-measure role audit for manual score/listening review."""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main() -> None:
    roles=json.loads((HERE/'prokofiev3-full-role-review.json').read_text())
    clock=json.loads((HERE/'prokofiev3-full-global-clock.json').read_text())
    seconds={float(beat):float(time) for beat,time in clock['beat_time']}
    target=HERE/'prokofiev3-full-role-table.csv'
    with target.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.writer(stream)
        writer.writerow(('measure','start_seconds','end_seconds',
                         'piano_attacks','foreground_parts',
                         'acoustic_promotion','top_score_candidates'))
        for row in roles:
            measure=row['measure']
            promotion=row.get('acoustic_promotion',{})
            candidates='; '.join(f"{x['part']} {x['score']:.2f}"
                                 for x in row['candidates'][:3])
            writer.writerow((measure,round(seconds[(measure-1)*4],3),
                             round(seconds[measure*4],3),
                             row['piano_attacks'],
                             ','.join(row['selected_parts']),
                             promotion.get('part',''),candidates))
    print(target)


if __name__=='__main__':main()
