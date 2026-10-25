"""Inspect the Git index before publishing: no videos or oversized blobs.

Checks staged blob contents, not just the current working-tree filenames.
Original performance media remain local; this script never stages files.
"""
from pathlib import PurePosixPath
import subprocess
import sys

VIDEO_SUFFIXES={'.mp4','.mkv','.mov','.m4v','.avi','.webm','.wmv','.mpg','.mpeg',
                '.m2ts','.mts','.flv','.vob','.3gp','.3g2','.ogv'}
MAX_BLOB=100*1024*1024


def is_video(path,header):
    suffix=PurePosixPath(path).suffix.lower()
    if suffix in VIDEO_SUFFIXES or (suffix=='.ts' and path.startswith('resource/')):return True
    if header[:4]==b'\x1aE\xdf\xa3':return True  # Matroska/WebM
    if header[:4]==b'RIFF' and header[8:12]==b'AVI ':return True
    if header[4:8]==b'ftyp' and header[8:12] not in {b'M4A ',b'M4B ',b'M4P '}:return True
    return header[:4] in {b'\x00\x00\x01\xba',b'\x00\x00\x01\xb3'}


def main():
    entries=subprocess.check_output(['git','ls-files','--stage','-z']).split(b'\0')
    files=[];errors=[]
    for entry in entries:
        if not entry:continue
        metadata,raw_path=entry.split(b'\t',1);mode,oid,stage=metadata.split()
        path=raw_path.decode('utf-8')
        if stage!=b'0':errors.append(f'Unresolved merge: {path}');continue
        if mode==b'160000':continue
        files.append((oid,path))
    process=subprocess.Popen(['git','cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    total=0
    try:
        for oid,path in files:
            process.stdin.write(oid+b'\n');process.stdin.flush()
            line=process.stdout.readline().split()
            if len(line)!=3 or line[1]!=b'blob':raise RuntimeError('Cannot read staged blob: '+path)
            size=int(line[2]);total+=size
            header=process.stdout.read(min(64,size));remaining=size-len(header)
            while remaining:
                chunk=process.stdout.read(min(65536,remaining))
                if not chunk:raise RuntimeError('Truncated staged blob: '+path)
                remaining-=len(chunk)
            process.stdout.read(1)
            if is_video(path,header):errors.append('Video excluded from publication: '+path)
            if size>=MAX_BLOB:errors.append(f'Blob exceeds 100 MiB: {path}')
    finally:
        process.stdin.close();process.stdout.close();process.wait()
    if errors:
        print('\n'.join(errors),file=sys.stderr);return 1
    print(f'Publication check passed: {len(files)} indexed files, {total/1024/1024:.1f} MiB; no video blobs.')
    return 0


if __name__=='__main__':sys.exit(main())
