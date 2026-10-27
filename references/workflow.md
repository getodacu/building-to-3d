# Research, modeling, and review

## Research acceptance gate

Start with identity, address, date/state, and alternate names. Seek official dimensions and plans, ground views from each side, aerial/roof views, and close photographs of characteristic materials and ornament. For complex buildings include courtyards, connecting wings, and additions. These are evidence categories, not fixed modeling sections.

Inspect actual content. Distinguish exterior from interior, current from historic, schematic from measured plan, and the target building from a similarly named one. Preserve plan scale, orientation, legends, image date, occlusions, and overlays. Do not infer color from monochrome images or dimensions directly from uncalibrated perspective.

Research and assess in rounds, with `research.max_rounds` defaulting to **3 total rounds**, including the initial search. A round is a coherent batch of targeted queries, inspection of the resulting resources, and a gate assessment; it is not a single query or download. Unproductive rounds still count. Record the queries, inspected source IDs, and genuinely new observations. `new_evidence` is empty when the round added nothing useful, even if downloads succeeded. After every round review the combined evidence across five coverage aspects:

- **Massing:** footprint, relative heights, setbacks, connections, scale anchors.
- **Elevations:** each distinct facade, rhythm, levels, corners, openings, asymmetry.
- **Roof:** forms, ridges, terraces, courtyards, parapets, prominent features.
- **Materials:** color/finish at useful scale, glazing, frames, weathering placement.
- **Defining features:** features whose absence would make this a generic building.

`supported` means inspected accepted sources support the decisions needed for the complete exterior in that aspect. Name every distinct elevation, wing, courtyard, and roof relationship in the relevant coverage notes and link supporting sources. Judge sources together: photographs, plans, schematics, and descriptions can complement one another; none is universally mandatory. Sources must match the building and historical state and be sufficiently legible and unoccluded for the claimed decisions. Copies of one photograph are not independent corroboration.

Minor dimension/detail estimates do not fail an otherwise supported aspect: explain their basis and uncertainty in the assessment and carry them into the plan and `limitations`. Use `inferred` and list a blocking gap when an important part is unseen or contradictory. An unseen facade, unknown roof structure, missing scale basis, or unsupported defining feature fails the gate. A front photograph cannot silently support the rear. Resolve material conflicts before acceptance; document the resolution and supporting sources.

Save an immutable assessment file with artifact kind `research` after each round. Include source/artifact references, coverage and uncertainties for each aspect, gate verdict and rationale, specific blocking gaps, and targeted next queries or requested resources. Register it and reference it from the round's and current research record's `assessment_artifact_id`. Keep previous assessment files and round records unchanged.

- Record `sufficient` only when all aspects are supported and no blocking gaps remain. Stop searching and proceed to analysis/planning.
- Otherwise record `pending` and search specifically for the gaps while fewer than `max_rounds` rounds have been consumed. Do not stop early just because consecutive rounds added nothing useful, or keep searching after acceptance.
- On the final failed round record `blocked`, even if useful new evidence was found. Stop all dependent work, including planning, blockout, textures, and refinement. Tell the user how many rounds were used, why the complete exterior cannot yet be supported, and exactly what would help (for example a rear elevation photograph, roof plan/aerial view, dimensioned schematic, or architectural description of a hidden wing). Invite uploads, local files, or links. A research-only incomplete package may be delivered; this is a blocker, not routine approval.

On resume preserve all search rounds. Legacy `proceed_with_approximations` never passes this gate; missing new manifest fields require a fresh assessment. Existing models, artifacts, and reviews remain historical work, not permission to continue. Counts already at or above the limit mean the search allowance is exhausted.

When the user supplies resources, inspect and register them as sources, then save a new assessment and update current coverage/verdict/rationale/gaps and `assessment_artifact_id`. Do not add a search round merely to inspect supplied resources or replace earlier round assessments. If sufficient, resume; otherwise remain blocked when the allowance is exhausted and explain the remaining gaps. Only an explicit user instruction may increase `max_rounds`; preserve consumed rounds and use only the additional allowance. Never fabricate supporting evidence or silently resume with approximations.

## Implementation plan and ownership

Record metres, axes, origin, geographic orientation, and historical state. Distinguish published/measured dimensions, photo estimates, and assumptions. Derive sections by architectural relationships and modeling dependencies. Include courtyards and rear sections where needed, without a fixed section list.

Plan shared repeated systems (window bays, columns, cornices, roof tiles) in the layer that owns them. Preserve asymmetries. Use shared mesh data/instances for true repetition; keep sections editable. Build silhouette and relationships, then openings and large profiles, then ornament. Surface grain belongs in textures; openings, balustrades, capitals, and silhouette-changing moldings may need geometry.

Start Blender work with addon/connection status and scene information. Inspect the existing scene first. Save scripts in the project and execute the same source through MCP, e.g. `runpy.run_path`, rather than maintaining a different live implementation. Resolve project paths from the source location. Replace only this project's owned collection/data. Never clear someone else's scene, save over their open file, or overwrite unsaved work. Use dedicated project files/checkpoints.

Query Blender version, supported enums, and shader node types rather than localized display names or undocumented settings. Background renders/rebuilds use the same source and separate checkpoints, leaving the live scene and settings intact.

## Review instruments

**Blockout:** clay front/rear/sides, roof/top, and meaningful obliques. Verify scale anchors, silhouette, recesses, voids, heights, attachments, and wing/roof relationships before ornament.

**Textures:** generate neutral front-facing material swatches without perspective, baked shadows/highlights, borders, text, or scene objects. Keep raw images, process tiling, and create needed maps. Review repeats and a material test at world scale, near and at facade distance. Record source resolution separately from upscaled delivery resolution. Reject repetition artifacts or changed grain rather than assuming higher resolution is better. Use sRGB for color and non-color data for scalar/normal maps. Broad dirt/runoff belongs to building-scale placement, not identical stains in every tile.

**Sections:** compare source crops and actual renders. Keep stable cameras/lighting for before/after; disclose differences. Use clay for geometry, daylight for materials, close views for details, and grazing light for relief/intersections. Distant hero renders cannot verify small features. Check neighboring joins and the whole building after each sweep.

**Corrections:** record the defect, evidence, change, and result. Correct one coherent discrepancy group before re-review. A gate may pass initially with 0 corrections, or after at most 3. Missing images mean unreviewed. At the cap mark unresolved/blocked and deliver a partial package; do not proceed into dependent stages with a failed gate.

## Final proof

Record five checks with evidence artifacts:

1. `reopened_blend`: reopen the delivered file in separate/background Blender; confirm scene/scale match the reviewed checkpoint.
2. `packed_textures`: pack required resources and verify availability after reopening. Use relative paths for intentional remaining dependencies. Package scripts and their inputs so rebuilding needs neither the skill installation nor the original workspace.
3. `geometry`: inspect evaluated geometry and relevant defects/clearances. Document intentional open surfaces, modifier handling, exceptions, and unmeasured regions rather than demanding universal watertightness.
4. `rebuild_consistency`: compare stable geometry/transforms/UVs/material assignments from a clean scripted rebuild. Rerun in the same process and ensure owned objects, meshes, materials, and images do not accumulate. Compare stable scene data, not `.blend` bytes.
5. `glb_visual`: register the GLB, build an incomplete preview package, and serve it locally. Inspect the export in that viewer from multiple angles, including UV scale/transparency. Save screenshots outside the generated package into the project, register them, and record final proof; then build a fresh final package. Bake unsupported materials where needed. If a lighter browser preview is necessary, keep the detailed `.blend`, label simplification, and record differences. Never silently substitute a lower-detail model. Export a self-contained, uncompressed GLB with embedded textures; the bundled loader does not include Draco, Meshopt, or KTX2 decoders.

Keep logs/measurements for programmatic checks and images for visual judgments. The helper validates records, paths, and hashes; it cannot certify resemblance or that a claimed Blender check happened.
