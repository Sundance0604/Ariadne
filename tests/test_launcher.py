"""The launcher reuses only this workspace and avoids occupied ports."""
from pathlib import Path
import sys
import threading
import unittest
import json
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import serve_review
from launch_local import bind_available,find_running,choose_playable_track


class LocalLauncherTests(unittest.TestCase):
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
