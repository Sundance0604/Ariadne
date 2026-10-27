"""Selecting an export must preserve the matching project's editable draft."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from argparse import Namespace

from backend.video_export import paths
from scripts.video_export.edit_video_captions import resolve_target


class CaptionProjectTests(unittest.TestCase):
    def args(self,**overrides):
        return Namespace(**{'project':None,'full':False,'package':None,'document':None,**overrides})

    def test_registered_projects_keep_distinct_documents(self):
        projects=paths.editor_projects()
        self.assertEqual(len({p['document'] for p in projects}),len(projects))
        for project in projects:
            with self.subTest(project=project['id']):
                self.assertEqual(resolve_target(self.args(project=project['id'])),
                                 (project['package'],project['document']))

    def test_custom_package_does_not_overwrite_sample_draft(self):
        package=paths.ROOT/'tmp/custom-export'
        self.assertEqual(resolve_target(self.args(package=package)),
                         (package.resolve(),package.resolve()/'captions-editable.json'))
        document=paths.ROOT/'tmp/edited-caption.json'
        self.assertEqual(resolve_target(self.args(package=package,document=document)),
                         (package.resolve(),document.resolve()))

    def test_full_cli_remains_compatible(self):
        self.assertEqual(resolve_target(self.args(full=True)),paths.full_paths())

    def test_unknown_project_fails_without_creating_a_draft(self):
        with self.assertRaisesRegex(ValueError,'未知字幕项目'):
            resolve_target(self.args(project='missing-project'))

    def test_project_paths_cannot_escape_repository(self):
        project={'id':'test','title':'Test','package':'../outside','document':'tmp/draft.json'}
        with patch.object(paths,'settings',return_value={'editor_projects':[project]}):
            with self.assertRaisesRegex(ValueError,'项目内路径'):paths.editor_projects()

    def test_full_builder_updates_project_target_together(self):
        values=copy.deepcopy(paths.settings())
        package=paths.ROOT/'output/video-export/new-full'
        document=package/'captions-editable.json'
        with patch.object(paths,'settings',return_value=values),patch.object(Path,'write_text') as write:
            paths.remember_full(package,document)
        import json
        stored=json.loads(write.call_args.args[0])
        full=next(p for p in stored['editor_projects'] if p['id']=='ravel-full')
        self.assertEqual(full['package'],stored['full_package'])
        self.assertEqual(full['document'],stored['full_document'])


if __name__=='__main__':unittest.main()
