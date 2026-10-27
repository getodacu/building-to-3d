#!/usr/bin/env python3
"""Validate reconstruction records and build a portable, offline evidence package."""
import argparse
import base64
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import sys
from urllib.parse import quote, urlsplit
import zipfile

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
ASPECTS = ('massing', 'elevations', 'roof', 'materials', 'defining_features')
KINDS = {'blend', 'glb', 'texture', 'generated_image', 'script', 'research', 'plan',
         'checkpoint', 'render', 'comparison', 'report', 'log', 'other'}
ACCEPTED = {'accepted', 'no_change'}
RASTER = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
FINAL_CHECKS = {'reopened_blend', 'packed_textures', 'geometry', 'rebuild_consistency', 'glb_visual'}
RESERVED = {'index.html', 'project.json', 'package-index.json', 'viewer'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def string(value, name, nonempty=False):
    require(isinstance(value, str) and (not nonempty or value.strip()), f'{name}: expected string' + (' with content' if nonempty else ''))
    return value


def strings(value, name, nonempty=False):
    require(isinstance(value, list), f'{name}: expected array')
    for item in value:
        string(item, name, True)
    require(not nonempty or value, f'{name}: empty array')
    return value


def records(value, name):
    require(isinstance(value, list) and all(isinstance(x, dict) for x in value), f'{name}: expected record array')
    return value


def identified(value, name):
    result = {}
    for row in records(value, name):
        ident = string(row.get('id'), name + '.id', True)
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', ident), f'{name}: unsafe ID {ident!r}')
        require(ident not in result, f'{name}: duplicate ID {ident}')
        result[ident] = row
    return result


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def check_glb(path):
    with path.open('rb') as stream:
        header = stream.read(20)
        require(len(header) == 20, 'Truncated GLB: ' + str(path))
        magic, version, length, chunk_size, chunk_kind = struct.unpack('<4sIIII', header)
        require(magic == b'glTF' and version == 2 and length == path.stat().st_size
                and chunk_kind == 0x4E4F534A and 0 < chunk_size <= length - 20 and chunk_size % 4 == 0,
                'Invalid GLB header: ' + str(path))
        document = json.loads(stream.read(chunk_size))
    require(isinstance(document, dict) and isinstance(document.get('asset'), dict) and document['asset'].get('version') == '2.0', 'Expected glTF 2.0 asset')
    for resource in records(document.get('buffers', []), 'glb.buffers') + records(document.get('images', []), 'glb.images'):
        uri = resource.get('uri')
        require(uri is None or (isinstance(uri, str) and uri.startswith('data:')),
                'GLB must embed all buffers/textures; external resource: ' + str(uri))
    extensions = set(strings(document.get('extensionsUsed', []), 'glb.extensionsUsed')) | set(strings(document.get('extensionsRequired', []), 'glb.extensionsRequired'))
    require(not extensions & {'KHR_draco_mesh_compression', 'EXT_meshopt_compression', 'KHR_texture_basisu'},
            'Export an uncompressed GLB; bundled viewer has no Draco, Meshopt, or KTX2 decoders')


def artifact_path(root, value):
    value = string(value, 'artifact.path', True)
    path = PurePosixPath(value)
    require(not path.is_absolute() and '\\' not in value and ':' not in value and '?' not in value and '#' not in value,
            f'Unsafe artifact path: {value}')
    require(all(part not in ('', '.', '..') for part in value.split('/')), f'Unsafe artifact path: {value}')
    require(path.parts[0].casefold() not in RESERVED, f'Reserved artifact path: {value}')
    full = root
    for part in path.parts:
        full = full / part
        require(not full.is_symlink(), f'Symlink not allowed: {value}')
    require(full.resolve().is_relative_to(root), f'Artifact escapes project: {value}')
    require(full.is_file(), f'Missing artifact: {value}')
    require(full.stat().st_size > 0, f'Empty artifact: {value}')
    return full


def validate(root, data):
    root = root.resolve()
    require(isinstance(data, dict) and type(data.get('schema_version')) is int and data['schema_version'] == 1, 'Unsupported manifest schema')
    require(isinstance(data.get('building'), dict), 'Missing building record')
    for key in ('name', 'location', 'historical_state'):
        string(data['building'].get(key), 'building.' + key)
    string(data.get('summary'), 'summary')
    strings(data.get('limitations'), 'limitations')
    n = data.get('iterations')
    require(type(n) is int and n > 0, 'iterations must be a positive integer')
    artifacts = identified(data.get('artifacts'), 'artifacts')
    seen_paths = set()
    for row in artifacts.values():
        require(row.get('kind') in KINDS, f"Unknown artifact kind: {row.get('kind')}")
        string(row.get('label'), 'artifact.label', True)
        string(row.get('description', ''), 'artifact.description')
        path = artifact_path(root, row.get('path'))
        key = row['path'].casefold()
        require(key not in seen_paths, f'Duplicate artifact path: {row["path"]}')
        seen_paths.add(key)
        expected = row.get('sha256')
        require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), f'Invalid SHA-256: {row["id"]}')
        require(digest(path) == expected, f'Artifact changed since registration: {row["path"]}')
        if row['kind'] in {'blend', 'checkpoint'}:
            require(path.suffix.lower() == '.blend', f'Expected .blend: {row["path"]}')
        if row['kind'] == 'glb':
            require(path.suffix.lower() == '.glb', f'Expected .glb: {row["path"]}')
            check_glb(path)

    def refs(ids, table, name, kinds=None):
        for ident in strings(ids, name):
            require(ident in table, f'{name}: unknown ID {ident}')
            if kinds:
                require(table[ident].get('kind') in kinds, f'{name}: wrong artifact kind for {ident}')
        return ids

    sources = identified(data.get('sources'), 'sources')
    for row in sources.values():
        for key in ('title', 'author', 'date', 'retrieved_at', 'observations', 'uncertainties', 'rights'):
            string(row.get(key), 'source.' + key, key in {'title', 'observations', 'rights'})
        url = string(row.get('url'), 'source.url')
        parsed = urlsplit(url)
        require(not url or (parsed.scheme in {'https', 'http'} and parsed.netloc and not parsed.username), 'Source URL must be HTTP(S)')
        require(row.get('status') in {'accepted', 'rejected', 'unavailable'}, 'Invalid source status')
        refs(row.get('artifact_ids'), artifacts, 'source.artifact_ids', {'research'})
        require(row['status'] != 'accepted' or row['artifact_ids'], 'Accepted source needs local research evidence')
    accepted_sources = {k: v for k, v in sources.items() if v['status'] == 'accepted'}
    research = data.get('research')
    require(isinstance(research, dict), 'Missing research record')
    max_rounds = research.get('max_rounds', 3)
    require(type(max_rounds) is int and max_rounds > 0, 'research.max_rounds must be a positive integer')
    assessment = string(research.get('assessment_artifact_id', ''), 'research.assessment_artifact_id')
    if assessment:
        refs([assessment], artifacts, 'research.assessment_artifact_id', {'research'})
    rounds = records(research.get('rounds'), 'research.rounds')
    for row in rounds:
        strings(row.get('queries'), 'research.queries', True)
        refs(row.get('source_ids'), sources, 'research.source_ids')
        string(row.get('new_evidence'), 'research.new_evidence')
        round_assessment = string(row.get('assessment_artifact_id', ''), 'research.round.assessment_artifact_id')
        if round_assessment:
            refs([round_assessment], artifacts, 'research.round.assessment_artifact_id', {'research'})
    coverage = {}
    for row in records(research.get('coverage'), 'research.coverage'):
        aspect = row.get('aspect')
        require(aspect in ASPECTS and aspect not in coverage, 'Unknown or repeated research aspect')
        require(row.get('assessment') in {'supported', 'inferred'}, 'Invalid coverage assessment')
        refs(row.get('source_ids'), accepted_sources, 'coverage.source_ids')
        string(row.get('notes'), 'coverage.notes', True)
        require(row['assessment'] != 'supported' or row['source_ids'], 'Supported coverage needs sources')
        coverage[aspect] = row
    verdict = research.get('verdict')
    require(verdict in {'pending', 'sufficient', 'blocked', 'proceed_with_approximations'}, 'Invalid research verdict')
    string(research.get('rationale'), 'research.rationale')
    strings(research.get('gaps'), 'research.gaps')
    if verdict in {'sufficient', 'blocked'}:
        require(rounds and set(coverage) == set(ASPECTS) and research['rationale'].strip(), 'Research gate needs rounds, coverage, and rationale')
        if verdict == 'sufficient':
            require(all(r['assessment'] == 'supported' for r in coverage.values()) and not research['gaps'],
                    'Sufficient research cannot contain inferred coverage or unresolved gaps')
        else:
            require(research['gaps'], 'Blocked research needs documented gaps')
    research_ready = verdict == 'sufficient' and 'max_rounds' in research and bool(assessment)
    research_status = 'sufficient' if research_ready else (
        'blocked' if verdict in {'blocked', 'proceed_with_approximations'} or len(rounds) >= max_rounds else 'pending')
    sections = identified(data.get('sections'), 'sections')
    for row in sections.values():
        for key in ('name', 'scope'):
            string(row.get(key), 'section.' + key, True)
        strings(row.get('target_features'), 'section.target_features', True)
        refs(row.get('source_ids'), accepted_sources, 'section.source_ids')
    plan = string(data.get('plan_artifact_id'), 'plan_artifact_id')
    if plan:
        refs([plan], artifacts, 'plan_artifact_id', {'plan'})
    textures = identified(data.get('textures'), 'textures')
    for row in textures.values():
        for key in ('material', 'generator', 'prompt', 'rationale'):
            string(row.get(key), 'texture.' + key, True)
        require(isinstance(row.get('settings'), dict), 'texture.settings must be an object')
        strings(row.get('derived_maps'), 'texture.derived_maps')
        require(row.get('decision') in {'selected', 'rejected'}, 'Invalid texture decision')
        refs(row.get('raw_artifact_ids'), artifacts, 'texture.raw_artifact_ids', {'generated_image'})
        refs(row.get('map_artifact_ids'), artifacts, 'texture.map_artifact_ids', {'texture'})
        require(row['raw_artifact_ids'], 'Texture candidate needs raw generation')
        require(row['decision'] != 'selected' or row['map_artifact_ids'], 'Selected texture needs processed maps')
    deliverables = data.get('deliverables')
    require(isinstance(deliverables, dict), 'Missing deliverables record')
    for key, kind in (('blend_id', 'blend'), ('glb_id', 'glb')):
        ident = string(deliverables.get(key), 'deliverables.' + key)
        if ident:
            refs([ident], artifacts, key, {kind})

    sequence = [('blockout', None, None), ('textures', None, None)]
    sequence += [('refinement', i, s) for i in range(1, n + 1) for s in sections]
    sequence += [('final', None, None)]
    latest, attempts = {}, {}

    def required_checks(slot):
        stage, iteration, section = slot
        if stage == 'blockout':
            return {'massing_views'}
        if stage == 'textures':
            return {'tiling_scale', 'geometry_unchanged'}
        if stage == 'final':
            return FINAL_CHECKS
        return {'assembly'} if section == next(reversed(sections)) else set()

    def review_ready(row, slot):
        if not row or row['status'] not in ACCEPTED or row['remaining'] or not row['checkpoint_id']:
            return False
        if not any(artifacts[x]['kind'] in {'render', 'comparison'} and Path(artifacts[x]['path']).suffix.lower() in RASTER for x in row['evidence_ids']):
            return False
        passed = {c['name'] for c in row['checks'] if c['status'] == 'passed'}
        if not required_checks(slot) <= passed or any(c['status'] != 'passed' for c in row['checks']):
            return False
        if slot[0] == 'final':
            check = next(c for c in row['checks'] if c['name'] == 'glb_visual')
            return bool(deliverables['blend_id'] and deliverables['glb_id'] and row['checkpoint_id'] == deliverables['blend_id']
                        and deliverables['glb_id'] in check['evidence_ids']
                        and any(artifacts[x]['kind'] in {'render', 'comparison'} and Path(artifacts[x]['path']).suffix.lower() in RASTER for x in check['evidence_ids']))
        return True

    for row in identified(data.get('reviews'), 'reviews').values():
        stage = row.get('stage')
        require(stage in {'blockout', 'textures', 'refinement', 'final'}, 'Invalid review stage')
        if stage == 'refinement':
            require(type(row.get('iteration')) is int and 1 <= row['iteration'] <= n and row.get('section_id') in sections,
                    'Refinement review needs a planned section and iteration')
        else:
            require(row.get('iteration') is None and row.get('section_id') is None, 'Only refinement has iteration/section')
        slot = (stage, row.get('iteration'), row.get('section_id'))
        index = sequence.index(slot)
        count = row.get('correction_attempts')
        require(type(count) is int and attempts.get(slot, 0) <= count <= 3, 'Correction attempts must be cumulative and within 0..3')
        attempts[slot] = count
        require(row.get('status') in ACCEPTED | {'unresolved', 'blocked'}, 'Invalid review status')
        require(row['status'] != 'no_change' or stage == 'refinement', 'no_change is refinement-only')
        string(row.get('summary'), 'review.summary', True)
        strings(row.get('remaining'), 'review.remaining')
        refs(row.get('source_ids'), accepted_sources, 'review.source_ids')
        refs(row.get('evidence_ids'), artifacts, 'review.evidence_ids')
        checkpoint = string(row.get('checkpoint_id'), 'review.checkpoint_id')
        if checkpoint:
            refs([checkpoint], artifacts, 'review.checkpoint_id', {'blend', 'checkpoint'})
        check_names = set()
        for check in records(row.get('checks'), 'review.checks'):
            name = string(check.get('name'), 'check.name', True)
            require(name not in check_names, 'Duplicate review check')
            check_names.add(name)
            require(check.get('status') in {'passed', 'failed', 'not_checked'}, 'Invalid check status')
            refs(check.get('evidence_ids'), artifacts, 'check.evidence_ids')
            string(check.get('notes'), 'check.notes', True)
            require(check['status'] != 'passed' or check['evidence_ids'], 'Passing check needs evidence')
        # Retain historical reviews when stricter research requirements invalidate their prerequisite.
        require(plan and sections, 'Reviews require plan and sections')
        require(all(review_ready(latest.get(previous), previous) for previous in sequence[:index]),
                'Review skips an incomplete prerequisite stage, section, or sweep')
        # Reworking an earlier slot invalidates later verdicts, never silently reuses stale proof.
        for later in sequence[index + 1:]:
            latest.pop(later, None)
        latest[slot] = row

    pending = []
    if not data['building']['name'].strip() or not data['building']['location'].strip():
        pending.append('Identify building and location')
    if not research_ready:
        if research_status == 'blocked':
            pending.append(f'Research blocked after {len(rounds)} of {max_rounds} allowed rounds; '
                           'ask the user to provide resources addressing the evidence gaps. '
                           'Further searching requires an explicitly increased limit.')
        else:
            pending.append(f'Complete the research evidence gate ({len(rounds)} of {max_rounds} rounds used)')
        if verdict == 'proceed_with_approximations' or 'max_rounds' not in research or not assessment:
            pending.append('Reassess research under the current gate; record max_rounds and a saved assessment artifact')
        pending.extend('Research gap: ' + gap for gap in research['gaps'])
    if not plan:
        pending.append('Save implementation plan')
    if not sections:
        pending.append('Define building sections')
    for slot in sequence:
        if not research_ready or not review_ready(latest.get(slot), slot):
            pending.append('Review ' + ' / '.join(str(x) for x in slot if x is not None))
    if not any(t['decision'] == 'selected' for t in textures.values()):
        pending.append('Generate and select material textures')
    for key in ('blend_id', 'glb_id'):
        if not deliverables[key]:
            pending.append('Deliver ' + key.removesuffix('_id'))
    for kind in ('script', 'research', 'comparison'):
        if not any(a['kind'] == kind for a in artifacts.values()):
            pending.append('Register ' + kind + ' artifacts')
    sweeps = sum(bool(sections) and all(review_ready(latest.get(('refinement', i, s)), ('refinement', i, s)) for s in sections) for i in range(1, n + 1)) if research_ready else 0
    return {'complete': not pending, 'pending': pending, 'completed_sweeps': sweeps, 'requested_sweeps': n,
            'research_status': research_status, 'research_rounds': len(rounds), 'research_max_rounds': max_rounds}


def escape(value):
    return html.escape(str(value), quote=True)


def report(data, state):
    artifacts = {a['id']: a for a in data['artifacts']}

    def link(ident):
        a = artifacts[ident]
        return f'<a download href="{quote(a["path"], safe="/")}">{escape(a["label"])}</a>'

    def links(ids):
        return '<ul>' + ''.join(f'<li>{link(i)}</li>' for i in ids) + '</ul>' if ids else ''

    def gallery(ids):
        return '<div class="gallery">' + ''.join(
            f'<figure><a href="{quote(artifacts[i]["path"], safe="/")}" download><img loading="lazy" src="{quote(artifacts[i]["path"], safe="/")}" alt="{escape(artifacts[i]["label"])}"></a><figcaption>{escape(artifacts[i]["label"])}</figcaption></figure>'
            for i in ids if Path(artifacts[i]['path']).suffix.lower() in RASTER) + '</div>'

    def bullets(items):
        return '<ul>' + ''.join(f'<li>{escape(x)}</li>' for x in items) + '</ul>' if items else '<p>None recorded.</p>'

    building = data['building']
    status = 'Recorded checks complete' if state['complete'] else 'Incomplete'
    glb_id = data['deliverables']['glb_id']
    model = quote(artifacts[glb_id]['path'], safe='/') if glb_id else ''
    parts = [f'<header><h1>{escape(building["name"] or "Building reconstruction")}</h1><p class="location">{escape(building["location"])} · {escape(building["historical_state"])}</p><p>{escape(data["summary"])}</p><p class="status">{status} · {state["completed_sweeps"]} of {state["requested_sweeps"]} sweeps reviewed</p></header>',
             '<nav aria-label="Report sections"><a href="#model">Model</a><a href="#renders">Renders</a><a href="#research">Research</a><a href="#plan">Plan</a><a href="#textures">Textures</a><a href="#history">Reviews</a><a href="#limitations">Limitations</a><a href="#artifacts">Files</a></nav>',
             f'<section id="model"><h2>Explore the model</h2><div id="viewer" data-model="{escape(model)}"><p id="viewer-status" role="status">Loading model. If it does not appear, serve this folder locally using the command below.</p></div>',
             '<div class="viewer-controls" role="group" aria-label="Model controls"><button type="button" data-action="left">Rotate left</button><button type="button" data-action="right">Rotate right</button><button type="button" data-action="in">Zoom in</button><button type="button" data-action="out">Zoom out</button><button type="button" data-action="reset">Reset view</button></div>',
             '<p>Drag to orbit; scroll to zoom. Keyboard: focus the model and use arrow keys to pan, or use the controls above. Blender renders remain the reference for full material appearance.</p><details><summary>Open this report offline</summary><p>From this unpacked folder, run:</p><pre>python3 -m http.server 8000 --bind 127.0.0.1</pre><p>Then open <a href="http://127.0.0.1:8000/">http://127.0.0.1:8000/</a>. All viewer files are bundled. WebGL is required only for the interactive model.</p></details><noscript><p>JavaScript is disabled. Use the render galleries and downloadable models below.</p></noscript></section>']
    recent_views = [a['id'] for a in data['artifacts'] if a['kind'] in {'render', 'comparison'}][-4:]
    parts.append('<section id="renders"><h2>Saved views</h2>' + (gallery(recent_views) if recent_views else '<p>No rendered views saved yet.</p>') + '</section>')
    if state['pending']:
        parts.append('<section><h2>Work remaining</h2>' + bullets(state['pending']) + '</section>')
    r = data['research']
    parts.append(f'<section id="research"><h2>Research and evidence</h2><p><strong>{escape(state["research_status"])}</strong> — {escape(r["rationale"])}</p>'
                 f'<p>{state["research_rounds"]} of {state["research_max_rounds"]} research rounds used.</p>')
    if state['research_status'] == 'blocked':
        parts.append('<p role="status">Research is blocked. Please provide resources addressing the gaps below, '
                     'such as photos of missing elevations, roof/aerial views, plans, schematics, or architectural descriptions. '
                     'Supplied resources can be reassessed without resetting the counter; further searching requires '
                     'an explicitly increased limit. Reconstruction cannot continue until the gate passes.</p>')
    if r.get('assessment_artifact_id'):
        parts.append('<h3>Current assessment</h3>' + links([r['assessment_artifact_id']]))
    parts.append('<div class="table-scroll"><table><caption>Reference coverage</caption><thead><tr><th scope="col">Aspect</th><th scope="col">Basis</th><th scope="col">Assessment</th></tr></thead><tbody>')
    for row in r['coverage']:
        parts.append(f'<tr><th scope="row">{escape(row["aspect"].replace("_", " "))}</th><td>{escape(row["assessment"])}</td><td>{escape(row["notes"])}<br>{escape(", ".join(row["source_ids"]))}</td></tr>')
    if not r['coverage']:
        parts.append('<tr><td colspan="3">Coverage has not been reviewed.</td></tr>')
    parts.append('</tbody></table></div><h3>Evidence gaps</h3>' + bullets(r['gaps']))
    for i, row in enumerate(r['rounds'], 1):
        assessment_links = links([row['assessment_artifact_id']]) if row.get('assessment_artifact_id') else ''
        parts.append(f'<details><summary>Research round {i}</summary>{bullets(row["queries"])}<p>{escape(row["new_evidence"] or "No useful new evidence.")}</p><p>Sources: {escape(", ".join(row["source_ids"]))}</p>{assessment_links}</details>')
    for row in data['sources']:
        url = f'<a href="{escape(row["url"])}" target="_blank" rel="noopener noreferrer">Original source</a>' if row['url'] else ''
        parts.append(f'<article><h3>{escape(row["title"])}</h3><p>{escape(row["status"])} · {escape(row["author"])} · {escape(row["date"])}</p><p>{escape(row["observations"])}</p><p><strong>Uncertainty:</strong> {escape(row["uncertainties"])}</p><p>{escape(row["rights"])} · Retrieved {escape(row["retrieved_at"])}</p><p>{url}</p>{gallery(row["artifact_ids"])}{links(row["artifact_ids"])}</article>')
    parts.append('</section><section id="plan"><h2>Implementation plan</h2>')
    if data['plan_artifact_id']:
        parts.append(links([data['plan_artifact_id']]))
    else:
        parts.append('<p>No implementation plan saved yet.</p>')
    for row in data['sections']:
        parts.append(f'<article><h3>{escape(row["name"])}</h3><p>{escape(row["scope"])}</p>{bullets(row["target_features"])}<p>Sources: {escape(", ".join(row["source_ids"]) or "Inferred; see plan.")}</p></article>')
    parts.append('</section><section id="textures"><h2>Texture generation</h2>')
    if not data['textures']:
        parts.append('<p>No generated texture candidates recorded.</p>')
    for row in data['textures']:
        parts.append(f'<article><h3>{escape(row["material"])} · {escape(row["decision"])}</h3><p>{escape(row["generator"])}</p><details><summary>Prompt and settings</summary><pre>{escape(row["prompt"])}</pre><pre>{escape(json.dumps(row["settings"], indent=2, ensure_ascii=False))}</pre></details><p>{escape(row["rationale"])}</p>{bullets(row["derived_maps"])}{gallery(row["raw_artifact_ids"] + row["map_artifact_ids"])}{links(row["raw_artifact_ids"] + row["map_artifact_ids"])}</article>')
    parts.append('</section><section id="history"><h2>Review history</h2><p>Agent assessments linked to saved evidence. Record validation does not certify visual accuracy.</p>')
    for row in data['reviews']:
        title = row['stage'].title()
        if row['stage'] == 'refinement':
            title = f'Sweep {row["iteration"]} · {row["section_id"]}'
        parts.append(f'<article><h3>{escape(title)}</h3><p><strong>{escape(row["status"].replace("_", " "))}</strong> · {row["correction_attempts"]} corrections</p><p>{escape(row["summary"])}</p>')
        if row['remaining']:
            parts.append('<h4>Unresolved</h4>' + bullets(row['remaining']))
        for check in row['checks']:
            parts.append(f'<details><summary>{escape(check["name"])} · {escape(check["status"])}</summary><p>{escape(check["notes"])}</p>{links(check["evidence_ids"])}</details>')
        parts.append(gallery(row['evidence_ids']) + links(row['evidence_ids']))
        if row['checkpoint_id']:
            parts.append('<p>Checkpoint: ' + link(row['checkpoint_id']) + '</p>')
        parts.append('</article>')
    parts.append('</section><section id="limitations"><h2>Limitations</h2>' + bullets(data['limitations']) + '</section><section id="artifacts"><h2>Files and reproducibility</h2><p>Models, scripts, references, textures, and evidence. File integrity is recorded in <a download href="package-index.json">package-index.json</a>; the complete record is in <a download href="project.json">project.json</a>.</p><ul class="files">')
    for row in data['artifacts']:
        parts.append(f'<li>{link(row["id"])} <span>{escape(row["kind"])} · {escape(row.get("description", ""))}</span></li>')
    parts.append('</ul></section><footer>Exterior reconstruction · Evidence and approximations are recorded, not surveyed accuracy.</footer>')
    importmap = json.dumps({'imports': {'three': './viewer/vendor/three.module.js', 'three/addons/': './viewer/vendor/addons/'}}, separators=(',', ':'))
    script_hash = base64.b64encode(hashlib.sha256(importmap.encode()).digest()).decode()
    csp = f"default-src 'none'; img-src 'self' data: blob:; style-src 'self'; script-src 'self' 'sha256-{script_hash}'; connect-src 'self' blob:; base-uri 'none'; object-src 'none'"
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{escape(csp)}"><title>{escape(building["name"] or "Building reconstruction")} — reconstruction report</title><link rel="stylesheet" href="viewer/report.css"><script type="importmap">{importmap}</script><script type="module" src="viewer/viewer.js"></script></head><body><a class="skip" href="#main">Skip to report</a><main id="main">' + ''.join(parts) + '</main></body></html>'


def build(root, output, data, state):
    root = root.resolve()
    output = output.expanduser().absolute()
    archive = output.with_name(output.name + '.zip')
    require(output != root and not root.is_relative_to(output.resolve()), 'Output cannot replace or contain the source project')
    require(not output.exists() and not output.is_symlink() and not archive.exists() and not archive.is_symlink(), 'Output folder or ZIP already exists; choose a new output')
    for a in data['artifacts']:
        require(not (root / a['path']).resolve().is_relative_to(output.resolve()), 'Output contains a registered input')
    viewer = ASSETS / 'viewer'
    for item in ('viewer.js', 'report.css', 'vendor/three.module.js', 'vendor/three.core.js',
                 'vendor/addons/loaders/GLTFLoader.js', 'vendor/addons/controls/OrbitControls.js',
                 'vendor/addons/utils/BufferGeometryUtils.js', 'vendor/LICENSE.txt', 'vendor/version.json'):
        require((viewer / item).is_file(), 'Missing bundled viewer dependency: ' + item)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    archive_created = False
    try:
        for a in data['artifacts']:
            source = artifact_path(root, a['path'])
            dest = output / a['path']
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            require(digest(dest) == a['sha256'], 'Artifact changed during packaging: ' + a['path'])
        shutil.copytree(viewer, output / 'viewer')
        (output / 'project.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        (output / 'index.html').write_text(report(data, state), encoding='utf-8')
        index = {'schema_version': 1, **state, 'files': {p.relative_to(output).as_posix(): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}}
        (output / 'package-index.json').write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8')
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
            archive_created = True
            for path in sorted(output.rglob('*')):
                if path.is_file():
                    bundle.write(path, Path(output.name) / path.relative_to(output))
    except BaseException:
        shutil.rmtree(output)
        if archive_created:
            archive.unlink(missing_ok=True)
        raise
    return {'report': str(output / 'index.html'), 'folder': str(output), 'zip': str(archive), **state}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'check', 'build'):
        sub = subs.add_parser(name)
        sub.add_argument('project', type=Path)
        if name == 'build':
            sub.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        root = args.project.expanduser().resolve()
        manifest = root / 'project.json'
        if args.command == 'init':
            root.mkdir(parents=True, exist_ok=True)
            with manifest.open('x', encoding='utf-8') as stream:
                stream.write((ASSETS / 'project.json').read_text(encoding='utf-8'))
            print(json.dumps({'manifest': str(manifest), 'iterations': 2}))
            return 0
        require(not manifest.is_symlink(), 'Manifest cannot be a symlink')
        data = json.loads(manifest.read_text(encoding='utf-8'))
        state = validate(root, data)
        if args.command == 'check':
            print(json.dumps(state, indent=2))
            return 0 if state['complete'] else 1
        print(json.dumps(build(root, args.output or root / 'delivery', data, state), indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
