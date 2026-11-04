"""Publishing path and viewer selection contracts."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'hosts/proximal/config/3dviewer/3dviewer'
spec = spec_from_loader('viewer_cli', SourceFileLoader('viewer_cli', str(SCRIPT)))
cli = module_from_spec(spec)
spec.loader.exec_module(cli)


class ViewerPublishingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def put(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture')
        return path

    def test_folder_preserves_sidecar_paths_and_spaces(self):
        self.put('part name.obj')
        self.put('materials.mtl')
        self.put('textures/blue.png')
        files = cli.collect([str(self.root)])
        entry = cli.select_entry(files, None)
        self.assertEqual(entry, 'part name.obj')
        receipt = {'id': 'abc123', 'files': [{'path': p} for p in files]}
        links = cli.viewer_links(receipt, entry)
        self.assertIn('/part%20name.obj,', links['url'])
        self.assertIn('/textures/blue.png', links['url'])
        self.assertIn('/embed.html#model=', links['embed_url'])

    def test_multiple_models_require_selection_and_only_selected_is_loaded(self):
        paths = [str(self.put('part.stl')), str(self.put('part.step'))]
        files = cli.collect(paths)
        with self.assertRaisesRegex(ValueError, '--entry'):
            cli.select_entry(files, None)
        self.assertEqual(cli.select_entry(files, 'part.step'), 'part.step')
        links = cli.viewer_links({'id': 'abc123', 'files': [{'path': p} for p in files]}, 'part.step')
        self.assertEqual(len(links['model_urls']), 1)
        self.assertTrue(links['url'].endswith('part.step'))

    def test_rejects_symlinks_hidden_files_and_unrelated_outputs_before_upload(self):
        model = self.put('part.stl')
        link = self.root / 'linked.stl'
        link.symlink_to(model)
        for bad in [link, self.put('.private.stl'), self.put('report.html'), self.put('part,1.stl')]:
            with self.subTest(path=bad), self.assertRaises(ValueError):
                cli.collect([str(bad)])

    def test_nested_symlink_directory_is_rejected(self):
        self.put('part.stl')
        (self.root / 'linked').symlink_to('/etc', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            cli.collect([str(self.root)])

    def test_duplicate_leaf_names_are_ambiguous_to_upstream_importer(self):
        self.put('one/part.obj')
        self.put('two/PART.obj')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            cli.collect([str(self.root)])

    def test_multiple_inputs_retain_folder_basename(self):
        model = self.put('part.obj')
        texture = self.put('textures/blue.png')
        files = cli.collect([str(model), str(texture.parent)])
        self.assertEqual(set(files), {'part.obj', 'textures/blue.png'})

    def test_missing_or_non_model_entry_fails(self):
        texture = self.put('blue.png')
        files = cli.collect([str(texture)])
        for entry in [None, 'missing.stl', 'blue.png']:
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                cli.select_entry(files, entry)

    def test_snapshot_excludes_new_files_and_rejects_replaced_symlink(self):
        model = self.put('part.stl')
        files = cli.collect([str(self.root)])
        self.put('private.txt')
        with tempfile.TemporaryDirectory() as target:
            cli.snapshot(files, Path(target))
            self.assertEqual([p.name for p in Path(target).iterdir()], ['part.stl'])
            self.assertEqual((Path(target) / 'part.stl').read_text(), 'fixture')
        model.unlink()
        model.symlink_to(self.root / 'private.txt')
        with tempfile.TemporaryDirectory() as target, self.assertRaises(OSError):
            cli.snapshot(files, Path(target))
