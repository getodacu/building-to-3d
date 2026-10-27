# Manifest and package helper

Use Python 3.10+; no Python packages required. The skill bundles a pinned MIT-licensed Three.js viewer and downloads nothing at runtime.

```sh
python3 <skill-dir>/scripts/package.py init <project-dir>
python3 <skill-dir>/scripts/package.py check <project-dir>
python3 <skill-dir>/scripts/package.py build <project-dir> --output <new-output-dir>
```

`init` creates `project.json` without overwriting existing work. Update the manifest throughout the task, preferably by atomic file replacement. `check` exits 0 for recorded completion, 1 for incomplete work, 2 for invalid records/paths/hashes. `build` rejects invalid records but packages incomplete work visibly labeled **Incomplete**. It refuses existing output folders/ZIPs. Only registered artifacts, the manifest, report/viewer, and a SHA-256 integrity index are included. The sibling ZIP contains the output folder as its top-level directory.

Serve the unpacked output with `python3 -m http.server 8000 --bind 127.0.0.1 --directory <output-dir>`; open `http://127.0.0.1:8000/`. Direct `file://` navigation cannot load GLB reliably. The report remains readable without WebGL/JavaScript and gives recovery instructions.

## Top-level records

`assets/project.json` is the starting manifest:

- `schema_version`: 1; `iterations`: positive integer, default 2.
- `building`: `name`, `location`, `historical_state` strings; `summary`: current result.
- `research`: `max_rounds` (positive integer, default 3, independent of refinement `iterations`), `rounds`, `coverage`, `verdict`, `rationale`, `gaps`, `assessment_artifact_id` (initially empty).
- `plan_artifact_id`: saved plan ID, initially empty.
- `sections`, `sources`, `textures`, `reviews`, `artifacts`: arrays.
- `deliverables`: `blend_id`, `glb_id`, initially empty.
- `limitations`: strings covering inaccuracies, unresolved defects, and export differences.

## Artifacts

Register all task outputs, including rejected candidates, logs, reports, and scripts. Do not bundle unrelated files/secrets. Paths are project-relative; absolute paths, `..`, symlinks, and reserved package paths (`index.html`, `viewer/`, `package-index.json`, `project.json`) are rejected. Each path is registered once, must exist, and needs a matching SHA-256. Reviewed files stay immutable: corrections use new IDs/files.

```json
{"id":"clay-front-v1","kind":"render","label":"Blockout front in clay","path":"renders/front.png","sha256":"<64 lowercase hex characters>","description":"Orthographic front; metres."}
```

Compute hashes with `hashlib.sha256(path.read_bytes()).hexdigest()`. Kinds: `blend`, `glb`, `texture`, `generated_image`, `script`, `research`, `plan`, `checkpoint`, `render`, `comparison`, `report`, `log`, `other`. Blend/checkpoint files use `.blend`; GLB uses `.glb`. GLBs must embed all buffers and textures, without Draco, Meshopt, or KTX2 compression; the helper rejects dependencies the bundled viewer cannot load offline. The report embeds raster images and offers other files as downloads.

## Sources and research

```json
{"id":"facade-photo","title":"Facade photograph","url":"https://example.org/building","author":"Known author or unknown","date":"2024-06 or unknown","retrieved_at":"2026-10-26","status":"accepted","artifact_ids":["downloaded-photo"],"observations":"Features actually inspected.","uncertainties":"Occlusions and perspective limitations.","rights":"Known license/attribution or research-only status."}
```

Source status: `accepted`, `rejected`, `unavailable`. Keep rejected/unavailable attempts with reasons. Accepted sources require local evidence: an image, extracted text, screenshot, plan, or notes of inspected content when downloading fails. URLs must be HTTP(S), or empty. Supporting `source_ids` must name accepted sources; generations never count as sources.

Each chronological research round has `queries` (nonempty string array), `source_ids` (including rejected inspected sources), `new_evidence` (new observations, or empty), and `assessment_artifact_id` referencing its immutable gate assessment, with artifact kind `research`. Each round includes a batch of queries, resource inspection, and assessment; the initial search counts as round 1. Empty `new_evidence` does not reset or extend the allowance.

Coverage has one row per aspect: `massing`, `elevations`, `roof`, `materials`, `defining_features`. Each has `assessment` (`supported` or `inferred`), `source_ids`, and `notes`. Supported rows need accepted sources and notes identifying the exterior areas/features covered. Inferred rows may have none but must explain the missing support. See [workflow.md](workflow.md) for acceptance criteria. `gaps` contains blocking evidence gaps; minor supported estimates belong in notes, the assessment, and `limitations`.

Verdict starts `pending`; current verdicts are `pending`, `sufficient`, and `blocked`. Only `sufficient` with rounds, all aspects supported, no blocking gaps, rationale, an explicit `max_rounds`, and a current `assessment_artifact_id` satisfies research. `blocked` needs rounds, all five coverage rows, rationale, and documented gaps. The current assessment may differ from the last round's assessment after user-supplied resources are inspected; save a new artifact without consuming another search round. Each assessment records sources, coverage, uncertainties, verdict, rationale, and specific missing resources or next queries. Keep previous files immutable.

After each failed round continue targeted research while `len(rounds) < max_rounds`. At exhaustion record `blocked`, stop dependent work, and invite the user to supply resources addressing the gaps. Useful new findings do not extend the limit. Only the user can explicitly increase the limit; never delete/reset rounds. The helper reports a failed gate at or above the limit as blocked even if its recorded verdict is still `pending`.

Schema version remains 1. For older manifests, omitted `max_rounds` uses 3 to display remaining/exhausted allowance, but omitted new current fields never establish acceptance. Legacy `proceed_with_approximations` is readable as blocked and requires reassessment. Historical rounds may omit assessment references: do not invent retrospective assessments. Preserve all historical rounds (including counts above 3), artifacts, and reviews. Reassess with existing or user-supplied evidence, explicitly record the limit and a new current assessment, and pass the current gate before continuing. Incomplete packaging preserves the manifest unchanged; historical reviews do not establish current progress until research passes.

`check` returns the existing completion/sweep fields plus `research_status`, `research_rounds`, and `research_max_rounds`. Blocked research exits 1 rather than an invalid-record error and remains packageable as **Incomplete**. Reports show the effective research status, round count/limit, current and per-round assessment links, evidence gaps, and an invitation to supply resources. The helper checks recorded structure and evidence references; the agent judges sufficiency and enforces the search limit.

## Sections and textures

Sections define sweep order; derive them from dependencies after research passes. Minor inferred details must be explained in scope/plan; a wholly unsupported exterior section blocks research acceptance.

```json
{"id":"entrance","name":"Entrance wing","scope":"Entrance and connections; small molding depth estimated.","source_ids":["facade-photo"],"target_features":["Recessed portal","Window rhythm"]}
```

Generated texture records preserve exact prompts and metadata actually exposed by the tool:

```json
{"id":"masonry-a","material":"Masonry","generator":"Actual tool/model","prompt":"Exact submitted prompt","settings":{"seed":42},"raw_artifact_ids":["raw-masonry-a"],"map_artifact_ids":["masonry-color","masonry-roughness"],"decision":"selected","rationale":"Repeat and physical-scale tests accepted.","derived_maps":["Roughness is an authored estimate."]}
```

Decision: `selected` or `rejected`. Raw files are `generated_image`; processed maps are `texture`. Rejected candidates may have no processed maps. At least one selected generated texture is needed for completion.

## Reviews and progress

Append chronologically. The latest record for a stage or iteration/section pair is its current verdict; keep prior records/artifacts. Correction attempts are cumulative within that slot, cannot decrease, and cannot exceed 3. Do not change scope/counts to evade gates.

```json
{"id":"entrance-sweep-1","stage":"refinement","iteration":1,"section_id":"entrance","status":"accepted","correction_attempts":1,"summary":"Portal depth corrected after comparison.","source_ids":["facade-photo"],"evidence_ids":["entrance-comparison-1"],"checkpoint_id":"entrance-checkpoint-1","remaining":[],"checks":[{"name":"openings","status":"passed","evidence_ids":["opening-check-1"],"notes":"No unintended occlusion in sampled openings."}]}
```

Stages: `blockout`, `textures`, `refinement`, `final`. Only refinement has `iteration`/`section_id`. Status: `accepted`, `no_change`, `unresolved`, `blocked`. `no_change` is refinement-only and needs a reason. Accepted/no-change records need visual evidence (`render`/`comparison`) and a `.blend` checkpoint. Checks have `name`, `status` (`passed`, `failed`, `not_checked`), `evidence_ids`, `notes`. Passing checks need evidence/notes. Accepted reviews cannot include failed/unperformed checks or unresolved `remaining` defects. Accepted approximations belong in `limitations`; defects failing the target remain unresolved.

Required passing checks:

| Stage | Names |
| --- | --- |
| blockout | `massing_views` |
| textures | `tiling_scale`, `geometry_unchanged` |
| each sweep's last section | `assembly` |
| final | `reopened_blend`, `packed_textures`, `geometry`, `rebuild_consistency`, `glb_visual` |

`glb_visual` evidence includes the delivered GLB and a viewer screenshot. The final checkpoint is the delivered blend. Completion requires research, saved plan, accepted blockout/textures, all requested section sweeps, final proof, generated textures, scripts, research files, render/comparison evidence, and both deliverables. Refinement cannot precede texturing or skip an unfinished sweep; final acceptance follows all sweeps. The helper validates recorded evidence, not its visual truth.
