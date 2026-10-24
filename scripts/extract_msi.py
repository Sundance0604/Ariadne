"""Read/extract a trusted MSI payload into a local folder without installing it."""
import argparse
import ctypes as c
from pathlib import Path
import shutil
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('msi',type=Path)
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    dll=c.WinDLL('msi')
    u=c.c_uint
    dll.MsiOpenDatabaseW.argtypes=[c.c_wchar_p,c.c_wchar_p,c.POINTER(u)]
    dll.MsiDatabaseOpenViewW.argtypes=[u,c.c_wchar_p,c.POINTER(u)]
    dll.MsiRecordGetStringW.argtypes=[u,u,c.c_wchar_p,c.POINTER(u)]
    dll.MsiRecordReadStream.argtypes=[u,u,c.c_void_p,c.POINTER(u)]
    handles=[]
    def check(code):
        if code: raise OSError(f'MSI API returned {code}')
    def string(record,index):
        size=u(32767); buffer=c.create_unicode_buffer(size.value+1)
        check(dll.MsiRecordGetStringW(record,index,buffer,c.byref(size)))
        return buffer.value
    database=u()
    check(dll.MsiOpenDatabaseW(str(args.msi.resolve()),None,c.byref(database)))
    handles.append(database)
    def rows(query,fields):
        view=u(); check(dll.MsiDatabaseOpenViewW(database,query,c.byref(view)))
        check(dll.MsiViewExecute(view,0))
        while True:
            record=u(); result=dll.MsiViewFetch(view,c.byref(record))
            if result==259: break
            check(result)
            yield record,[string(record,i) for i in range(1,fields+1)]
            dll.MsiCloseHandle(record)
        dll.MsiCloseHandle(view)
    args.destination.mkdir(parents=True,exist_ok=True)
    staging=args.destination/'_cabinet'
    staging.mkdir(exist_ok=True)
    for record,values in rows('SELECT `Name`,`Data` FROM `_Streams`',1):
        name=values[0]
        if not name.lower().endswith('.cab'): continue
        # Stream names come from the trusted MSI, still require a single basename.
        if Path(name).name!=name: raise ValueError('Unexpected cabinet name')
        cabinet=staging/name
        with cabinet.open('wb') as target:
            while True:
                size=u(1<<20); buffer=c.create_string_buffer(size.value)
                check(dll.MsiRecordReadStream(record,2,buffer,c.byref(size)))
                if not size.value: break
                target.write(buffer.raw[:size.value])
        subprocess.run(['expand.exe','-F:*',str(cabinet),str(staging)],check=True,
                       stdout=subprocess.DEVNULL)
    directories={values[0]:(values[1],values[2]) for _,values in
                 rows('SELECT `Directory`,`Directory_Parent`,`DefaultDir` FROM `Directory`',3)}
    components={values[0]:values[1] for _,values in
                rows('SELECT `Component`,`Directory_` FROM `Component`',2)}
    def folder(identifier):
        if identifier not in directories: return args.destination
        parent,name=directories[identifier]
        if not parent: return args.destination
        name=name.split(':')[0].split('|')[-1]
        return folder(parent) if name=='.' else folder(parent)/name
    copied=0
    for _,values in rows('SELECT `File`,`Component_`,`FileName` FROM `File`',3):
        file_id,component,name=values
        source=staging/file_id
        target=folder(components[component])/name.split('|')[-1]
        if not target.resolve().is_relative_to(args.destination.resolve()):
            raise ValueError('MSI path escapes extraction directory')
        if source.exists():
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target)
            copied+=1
    for handle in handles: dll.MsiCloseHandle(handle)
    print(f'Extracted {copied} files into {args.destination}')


if __name__=='__main__':
    main()
