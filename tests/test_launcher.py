"""The launcher reuses only this workspace and avoids occupied ports."""
from pathlib import Path
import sys
import threading
import unittest
import json
import os
import socket
import subprocess
import time
import uuid
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import serve_review
from launch_local import bind_available,find_running,choose_playable_track


class LocalLauncherTests(unittest.TestCase):
    def test_script_launches_load_tracks_without_repository_in_pythonpath(self):
        # In-process tests inherit the repository path from unittest. Exercise
        # fresh interpreters from elsewhere, like the Windows launcher does.
        env=os.environ.copy();env.pop('PYTHONPATH',None)
        cwd=ROOT/'tmp'/('launcher-process-'+uuid.uuid4().hex)
        cwd.mkdir(parents=True)
        for entry in ('scripts/serve_review.py','start.py','scripts/launch_local.py'):
            with self.subTest(entry=entry), socket.socket() as reservation:
                reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
                reservation.close()
                if entry.endswith('launch_local.py'):
                    # Use the exact one-click import path without reusing an
                    # existing server, which would mask missing imports.
                    code=(f'import sys;sys.path.insert(0,{str(ROOT/"scripts")!r});'
                          'import launch_local as launcher;'
                          f'launcher.ReviewServer(("127.0.0.1",{port}),launcher.Handler).serve_forever()')
                    command=[sys.executable,'-E','-c',code]
                else:
                    command=[sys.executable,'-E',str(ROOT/entry),'--port',str(port)]
                with (cwd/'server.log').open('w+b') as log:
                    process=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=log)
                    base=f'http://127.0.0.1:{port}'
                    try:
                        deadline=time.monotonic()+15
                        while True:
                            try:
                                with urlopen(base+'/api/health',timeout=.5) as response:
                                    self.assertEqual(json.load(response)['app'],'Ariadne')
                                break
                            except OSError:
                                if process.poll() is not None or time.monotonic()>deadline:
                                    log.seek(0);self.fail(log.read().decode(errors='replace'))
                                time.sleep(.05)
                        for track in ('mahler-4','lark-ascending','ravel-left-hand'):
                            with urlopen(base+'/api/project?track='+track,timeout=60) as response:
                                project=json.load(response)
                            self.assertEqual(project['track']['id'],track)
                            self.assertTrue(project['alignment']['measures'])
                            self.assertIsNone(project['xml_navigation_error'])
                        with urlopen(base+'/api/musicxml-live?track=ravel-left-hand',timeout=60) as response:
                            live=json.load(response)
                        self.assertTrue(live['available']);self.assertTrue(live['frames'])
                    finally:
                        process.terminate();process.wait(timeout=10)
                    log.seek(0)
                    errors=log.read().decode(errors='replace')
                    # A readiness probe can close its socket during cold
                    # startup on Windows; successful API responses above are
                    # the functional check. Reject the import failure itself.
                    self.assertNotIn('ModuleNotFoundError',errors)
                    self.assertNotIn('ImportError',errors)

    def test_clean_clone_falls_back_from_missing_video_and_prefers_it_after_restore(self):
        root=ROOT/'tmp'/('launcher-media-'+uuid.uuid4().hex);root.mkdir(parents=True)
        catalog={'default_track':'audio','tracks':[{'id':'video','data_root':'video'},{'id':'audio','data_root':'audio'}]}
        for name,media in [('video','local.mp4'),('audio','included.mp3')]:
            folder=root/name;folder.mkdir()
            (folder/'alignment.json').write_text(json.dumps({'audio':{'path':media}}),encoding='utf-8')
        with self.assertRaises(RuntimeError):choose_playable_track(root,catalog,'video')
        (root/'included.mp3').write_bytes(b'fixture')
        self.assertEqual(choose_playable_track(root,catalog,'video'),'audio')
        (root/'local.mp4').write_bytes(b'fixture')
        self.assertEqual(choose_playable_track(root,catalog,'video'),'video')

    def test_reuses_matching_workspace_and_rejects_other_workspace(self):
        server=serve_review.ReviewServer(('127.0.0.1',0),serve_review.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            self.assertEqual(find_running(ROOT,[server.server_port]),server.server_port)
            self.assertIsNone(find_running(ROOT/'another-project',[server.server_port]))
        finally:server.shutdown();server.server_close();worker.join()

    def test_falls_back_when_the_first_port_is_occupied(self):
        occupied=serve_review.ReviewServer(('127.0.0.1',0),serve_review.Handler)
        try:
            fallback=bind_available([occupied.server_port,0])
            try:self.assertNotEqual(fallback.server_port,occupied.server_port)
            finally:fallback.server_close()
        finally:occupied.server_close()


if __name__=='__main__':unittest.main()
