"""Focused contract tests; all building records and binary placeholders are synthetic."""
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest
import zipfile

SKILL = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('building_package', SKILL / 'scripts/package.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jVmcAAAAASUVORK5CYII=')


def glb_bytes(**extra):
    document = json.dumps({'asset': {'version': '2.0'}, 'scenes': [], **extra}).encode()
    document += b' ' * (-len(document) % 4)
    return struct.pack('<4sIIII', b'glTF', 2, 20 + len(document), len(document), 0x4E4F534A) + document


def fixture(root):
    data = json.loads((SKILL / 'assets/project.json').read_text())
    data['building'].update(name='Synthetic pavilion', location='Test fixture')
    data['summary'] = 'Synthetic records for package tests, not a reconstructed real building.'

    def add(ident, kind, path, content):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        data['artifacts'].append(dict(id=ident, kind=kind, path=path, label=ident,
                                      sha256=hashlib.sha256(content).hexdigest()))

    for row in [('source', 'research', 'research/notes.txt', b'Synthetic reference notes.'),
                ('assessment', 'research', 'research/gate-1.md', b'Synthetic assessment: all five aspects supported; no blocking gaps.'),
                ('plan', 'plan', 'plan.md', b'Synthetic pavilion: body and roof, metres.'),
                ('script', 'script', 'scripts/model.py', b'# Synthetic placeholder for package tests.\n'),
                ('raw', 'generated_image', 'textures/raw.png', PNG),
                ('map', 'texture', 'textures/color.png', PNG),
                ('render', 'render', 'renders/clay.png', PNG),
                ('comparison', 'comparison', 'renders/comparison.png', PNG),
                ('proof', 'report', 'proof/checks.txt', b'Synthetic check evidence.'),
                ('checkpoint', 'checkpoint', 'checkpoints/stage.blend', b'Synthetic binary placeholder'),
                ('blend', 'blend', 'models/final.blend', b'Synthetic binary placeholder'),
                ('glb', 'glb', 'models/final.glb', glb_bytes())]:
        add(*row)
    data['plan_artifact_id'] = 'plan'
    data['deliverables'] = dict(blend_id='blend', glb_id='glb')
    data['sources'] = [dict(id='observed', title='Synthetic reference', url='https://example.org/pavilion',
                            author='Synthetic', date='unknown', retrieved_at='2026-10-26', status='accepted',
                            artifact_ids=['source'], observations='Synthetic pavilion body and roof.',
                            uncertainties='Synthetic fixture.', rights='Synthetic test data.')]
    data['research'] = dict(max_rounds=3, assessment_artifact_id='assessment',
                            rounds=[dict(queries=['synthetic pavilion plans'], source_ids=['observed'], new_evidence='Synthetic dimensions and views.', assessment_artifact_id='assessment')],
                            coverage=[dict(aspect=a, assessment='supported', source_ids=['observed'], notes='Synthetic coverage.') for a in package.ASPECTS],
                            verdict='sufficient', rationale='Synthetic coverage accepted for tests.', gaps=[])
    data['sections'] = [dict(id=s, name=s.title(), scope='Synthetic geometry.', source_ids=['observed'], target_features=['Profile']) for s in ('body', 'roof')]
    data['textures'] = [dict(id='material', material='Stone', generator='Synthetic fixture, no generation performed',
                            prompt='Synthetic test prompt', settings={}, raw_artifact_ids=['raw'], map_artifact_ids=['map'],
                            decision='selected', rationale='Synthetic selection.', derived_maps=[])]

    def review(ident, stage, checks, **extra):
        return dict(id=ident, stage=stage, status='accepted', correction_attempts=0,
                    summary='Synthetic review, not a claim of visual fidelity.', source_ids=['observed'],
                    evidence_ids=['render', 'comparison'], checkpoint_id='blend' if stage == 'final' else 'checkpoint',
                    remaining=[], checks=[dict(name=c, status='passed', evidence_ids=['glb', 'render'] if c == 'glb_visual' else ['proof'], notes='Synthetic evidence.') for c in checks], **extra)

    data['reviews'] = [review('blockout', 'blockout', ['massing_views']), review('textures', 'textures', ['tiling_scale', 'geometry_unchanged'])]
    for iteration in (1, 2):
        for section in ('body', 'roof'):
            data['reviews'].append(review(f'{section}-{iteration}', 'refinement', ['assembly'] if section == 'roof' else [], iteration=iteration, section_id=section))
    data['reviews'].append(review('final', 'final', sorted(package.FINAL_CHECKS)))
    return data


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='building-to-3d-test-')
        self.root = Path(self.temp.name) / 'project'
        self.root.mkdir()
        self.data = fixture(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def state(self):
        return package.validate(self.root, self.data)

    def reject(self, pattern):
        with self.assertRaisesRegex(ValueError, pattern):
            self.state()

    def add_research_round(self, new_evidence='New synthetic roof detail.'):
        research = self.data['research']
        count = len(research['rounds']) + 1
        ident = f'assessment-{count}'
        path = f'research/gate-{count}.md'
        target = self.root / path
        target.write_text(f'Synthetic assessment {count}: {research["verdict"]}; gaps: {research["gaps"]}.')
        self.data['artifacts'].append(dict(id=ident, kind='research', path=path, label=ident, sha256=package.digest(target)))
        research['rounds'].append(dict(queries=[f'synthetic missing view {count}'], source_ids=['observed'],
                                       new_evidence=new_evidence, assessment_artifact_id=ident))
        research['assessment_artifact_id'] = ident

    def block_research(self):
        research = self.data['research']
        research.update(verdict='blocked', rationale='Rear elevation remains unseen.', gaps=['Rear elevation: need a rear photo or elevation drawing.'])
        research['coverage'][1].update(assessment='inferred', notes='Rear elevation remains unseen.')
        while len(research['rounds']) < research['max_rounds']:
            self.add_research_round()

    def test_complete_two_sweeps(self):
        self.assertEqual(self.state()['completed_sweeps'], 2)
        self.assertTrue(self.state()['complete'])

    def test_missing_second_sweep_is_incomplete(self):
        self.data['reviews'] = self.data['reviews'][:4]
        state = self.state()
        self.assertEqual(state['completed_sweeps'], 1)
        self.assertFalse(state['complete'])

    def test_skipped_sweep_rejected(self):
        del self.data['reviews'][3]
        self.reject('skips an incomplete prerequisite')

    def test_three_corrections_allowed_four_rejected(self):
        self.data['reviews'][-1]['correction_attempts'] = 3
        self.assertTrue(self.state()['complete'])
        self.data['reviews'][-1]['correction_attempts'] = 4
        self.reject('0..3')

    def test_counter_cannot_reset(self):
        prior = copy.deepcopy(self.data['reviews'][-1])
        prior.update(id='prior-final', correction_attempts=2, status='unresolved')
        self.data['reviews'].insert(-1, prior)
        self.reject('cumulative')

    def test_rework_invalidates_later_verdicts(self):
        row = copy.deepcopy(self.data['reviews'][0])
        row['id'] = 'blockout-reworked'
        self.data['reviews'].append(row)
        state = self.state()
        self.assertFalse(state['complete'])
        self.assertEqual(state['completed_sweeps'], 0)

    def test_failed_final_proof_cannot_complete(self):
        self.data['reviews'][-1]['checks'][0]['status'] = 'not_checked'
        self.assertFalse(self.state()['complete'])

    def test_glb_requires_its_own_visual_evidence(self):
        check = next(c for c in self.data['reviews'][-1]['checks'] if c['name'] == 'glb_visual')
        check['evidence_ids'] = ['glb']
        self.assertFalse(self.state()['complete'])

    def test_glb_cannot_depend_on_network_or_external_files(self):
        for uri in ('https://example.org/texture.png', '../texture.png'):
            content = glb_bytes(images=[{'uri': uri}])
            (self.root / 'models/final.glb').write_bytes(content)
            self.data['artifacts'][-1]['sha256'] = hashlib.sha256(content).hexdigest()
            self.reject('must embed all')

    def test_unsupported_glb_compression_is_rejected(self):
        content = glb_bytes(extensionsRequired=['KHR_draco_mesh_compression'])
        (self.root / 'models/final.glb').write_bytes(content)
        self.data['artifacts'][-1]['sha256'] = hashlib.sha256(content).hexdigest()
        self.reject('uncompressed GLB')

    def test_no_change_requires_refinement(self):
        self.data['reviews'][-1]['status'] = 'no_change'
        self.reject('refinement-only')

    def test_no_visual_evidence_is_incomplete(self):
        self.data['reviews'][-1]['evidence_ids'] = ['proof']
        self.assertFalse(self.state()['complete'])

    def test_sufficient_cannot_hide_inference(self):
        self.data['research']['coverage'][2]['assessment'] = 'inferred'
        self.reject('inferred coverage')

    def test_legacy_approximation_cannot_complete(self):
        research = self.data['research']
        del research['max_rounds']
        del research['assessment_artifact_id']
        del research['rounds'][0]['assessment_artifact_id']
        research.update(verdict='proceed_with_approximations', gaps=['Roof inferred.'])
        research['rounds'] += [dict(queries=['roof plan'], source_ids=[], new_evidence=''), dict(queries=['roof aerial archive'], source_ids=[], new_evidence='')]
        # Older projects may already exceed the new default; preserve that history.
        research['rounds'].append(dict(queries=['old roof search'], source_ids=[], new_evidence=''))
        before = copy.deepcopy(self.data)
        state = self.state()
        self.assertFalse(state['complete'])
        self.assertEqual(state['research_status'], 'blocked')
        self.assertEqual((state['research_rounds'], state['research_max_rounds']), (4, 3))
        self.assertEqual(state['completed_sweeps'], 0)
        self.assertEqual(before, self.data)
        out = Path(self.temp.name) / 'legacy-delivery'
        package.build(self.root, out, self.data, state)
        self.assertEqual(json.loads((out / 'project.json').read_text()), before)

    def test_research_can_pass_before_limit(self):
        state = self.state()
        self.assertTrue(state['complete'])
        self.assertEqual(state['research_status'], 'sufficient')
        self.assertEqual((state['research_rounds'], state['research_max_rounds']), (1, 3))

    def test_research_can_pass_on_last_allowed_round(self):
        self.add_research_round()
        self.add_research_round()
        self.assertTrue(self.state()['complete'])
        self.assertEqual(self.state()['research_rounds'], 3)

    def test_exhaustion_blocks_even_with_new_evidence(self):
        self.block_research()
        research = self.data['research']
        self.assertTrue(all(r['new_evidence'] for r in research['rounds']))
        # Even a stale pending verdict must expose exhaustion rather than permit another round.
        research['verdict'] = 'pending'
        state = self.state()
        self.assertFalse(state['complete'])
        self.assertEqual(state['research_status'], 'blocked')
        self.assertTrue(any('provide resources' in message for message in state['pending']))
        self.assertTrue(any(research['gaps'][0] in message for message in state['pending']))

    def test_research_failure_before_limit_is_pending(self):
        self.data['research']['max_rounds'] = 4
        self.block_research()
        self.data['research']['rounds'].pop()
        self.data['research']['verdict'] = 'pending'
        state = self.state()
        self.assertFalse(state['complete'])
        self.assertEqual(state['research_status'], 'pending')
        self.assertEqual(state['research_max_rounds'], 4)

    def test_custom_research_limit_is_independent_of_sweeps(self):
        self.data['research']['max_rounds'] = 1
        self.assertTrue(self.state()['complete'])
        self.block_research()
        state = self.state()
        self.assertEqual((state['research_rounds'], state['research_max_rounds']), (1, 1))
        self.assertEqual(state['requested_sweeps'], 2)
        self.assertEqual(state['research_status'], 'blocked')

    def test_invalid_research_limits_rejected(self):
        for value in (0, -1, True, 1.5, '3', None):
            with self.subTest(value=value):
                self.data['research']['max_rounds'] = value
                self.reject('max_rounds must be a positive integer')

    def test_old_sufficient_gate_needs_reassessment(self):
        before = copy.deepcopy(self.data['research'])
        for key in ('max_rounds', 'assessment_artifact_id'):
            with self.subTest(missing=key):
                self.data['research'] = copy.deepcopy(before)
                del self.data['research'][key]
                state = self.state()
                self.assertFalse(state['complete'])
                self.assertEqual(state['research_max_rounds'], 3)
                self.assertTrue(any('Reassess research' in message for message in state['pending']))

    def test_current_and_round_assessments_must_reference_research(self):
        for record in (self.data['research'], self.data['research']['rounds'][0]):
            for ident, message in (('absent', 'unknown ID'), ('raw', 'wrong artifact kind')):
                with self.subTest(record=record, ident=ident):
                    record['assessment_artifact_id'] = ident
                    self.reject(message)
            record['assessment_artifact_id'] = 'assessment'

    def test_sufficient_cannot_hide_gaps(self):
        self.data['research']['gaps'] = ['Missing rear elevation.']
        self.reject('unresolved gaps')

    def test_blocked_gate_needs_documented_gaps(self):
        self.data['research']['verdict'] = 'blocked'
        self.reject('Blocked research needs documented gaps')

    def test_supplied_resources_can_unblock_without_resetting_rounds(self):
        self.block_research()
        self.assertFalse(self.state()['complete'])
        research = self.data['research']
        rounds = copy.deepcopy(research['rounds'])
        source = copy.deepcopy(self.data['sources'][0])
        source.update(id='user-rear', title='User-provided rear elevation', url='', observations='Synthetic rear elevation inspected.')
        self.data['sources'].append(source)
        research['coverage'][1].update(assessment='supported', source_ids=['user-rear'], notes='Rear drawing inspected.')
        target = self.root / 'research/reassessment.md'
        target.write_text('All aspects now supported by inspected user-rear evidence; no blocking gaps.')
        self.data['artifacts'].append(dict(id='reassessment', kind='research', path='research/reassessment.md', label='Reassessment', sha256=package.digest(target)))
        research.update(verdict='sufficient', gaps=[], rationale='Supplied rear drawing closes the last gap.', assessment_artifact_id='reassessment')
        self.assertTrue(self.state()['complete'])
        self.assertEqual(research['rounds'], rounds)
        self.assertEqual(self.state()['research_rounds'], 3)

    def test_explicit_limit_increase_preserves_consumed_rounds(self):
        self.block_research()
        rounds = copy.deepcopy(self.data['research']['rounds'])
        self.data['research'].update(max_rounds=4, verdict='pending')
        self.assertEqual(self.state()['research_status'], 'pending')
        self.add_research_round()
        self.assertEqual(self.state()['research_status'], 'blocked')
        self.assertEqual(self.data['research']['rounds'][:3], rounds)

    def test_blocked_package_requests_resources_and_links_assessments(self):
        self.block_research()
        before = copy.deepcopy(self.data)
        (self.root / 'project.json').write_text(json.dumps(self.data))
        command = [sys.executable, str(SKILL / 'scripts/package.py')]
        check = subprocess.run(command + ['check', str(self.root)], capture_output=True, text=True)
        self.assertEqual(check.returncode, 1, check.stderr)
        self.assertEqual(json.loads(check.stdout)['research_status'], 'blocked')
        out = Path(self.temp.name) / 'blocked-delivery'
        result = subprocess.run(command + ['build', str(self.root), '--output', str(out)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['complete'])
        html = (out / 'index.html').read_text()
        for text in ('Incomplete', 'Research is blocked', '3 of 3 research rounds', 'Rear elevation:', 'Please provide resources',
                     'explicitly increased limit', 'href="research/gate-1.md"', 'href="research/gate-3.md"'):
            self.assertIn(text, html)
        self.assertEqual(json.loads((out / 'project.json').read_text()), before)

    def test_rejected_source_cannot_support_geometry(self):
        self.data['sources'][0]['status'] = 'rejected'
        self.reject('unknown ID')

    def test_source_generation_is_not_research(self):
        self.data['sources'][0]['artifact_ids'] = ['raw']
        self.reject('wrong artifact kind')

    def test_missing_or_changed_artifact_rejected(self):
        (self.root / 'plan.md').unlink()
        self.reject('Missing artifact')
        (self.root / 'plan.md').write_text('Changed plan')
        self.reject('changed since registration')

    def test_traversal_and_reserved_paths_rejected(self):
        for path in ('../outside.txt', '/tmp/outside.txt', 'research/../plan.md', 'viewer/evil.js', 'project.json'):
            with self.subTest(path=path):
                self.data['artifacts'][0]['path'] = path
                self.reject('Unsafe|Reserved')

    def test_symlink_rejected(self):
        path = self.root / 'research/notes.txt'
        path.unlink()
        path.symlink_to(self.root / 'plan.md')
        self.reject('Symlink')

    def test_duplicate_paths_rejected(self):
        other = copy.deepcopy(self.data['artifacts'][0])
        other['id'] = 'duplicate'
        self.data['artifacts'].append(other)
        self.reject('Duplicate artifact path')

    def test_script_url_rejected(self):
        self.data['sources'][0]['url'] = 'javascript:alert(1)'
        self.reject('HTTP')

    def test_text_is_escaped(self):
        self.data['building']['name'] = '<script>alert("x")</script>'
        text = package.report(self.data, self.state())
        self.assertNotIn('<script>alert(', text)
        self.assertIn('&lt;script&gt;', text)

    def test_portable_bundle_integrity_and_no_unregistered_files(self):
        (self.root / 'unrelated-secret.txt').write_text('do not package')
        out = Path(self.temp.name) / 'delivery'
        before = copy.deepcopy(self.data)
        result = package.build(self.root, out, self.data, self.state())
        self.assertEqual(before, self.data)
        self.assertFalse((out / 'unrelated-secret.txt').exists())
        self.assertTrue((out / 'viewer/vendor/LICENSE.txt').exists())
        index = json.loads((out / 'package-index.json').read_text())
        for name, expected in index['files'].items():
            self.assertEqual(package.digest(out / name), expected)
        with zipfile.ZipFile(result['zip']) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn('delivery/index.html', archive.namelist())
        with self.assertRaisesRegex(ValueError, 'already exists'):
            package.build(self.root, out, self.data, self.state())

    def test_cli_init_and_incomplete_package(self):
        project = Path(self.temp.name) / 'new-project'
        command = [sys.executable, str(SKILL / 'scripts/package.py')]
        self.assertEqual(subprocess.run(command + ['init', str(project)], capture_output=True).returncode, 0)
        self.assertEqual(json.loads((project / 'project.json').read_text())['research']['max_rounds'], 3)
        self.assertEqual(subprocess.run(command + ['init', str(project)], capture_output=True).returncode, 2)
        self.assertEqual(subprocess.run(command + ['check', str(project)], capture_output=True).returncode, 1)
        result = subprocess.run(command + ['build', str(project)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['complete'])
        self.assertIn('Incomplete', (project / 'delivery/index.html').read_text())


if __name__ == '__main__':
    unittest.main()
