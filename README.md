# Building to 3D

A Codex skill for researching a real building and reconstructing its exterior in Blender. It combines inspected source evidence, editable modeling scripts, generated material textures, and section-by-section refinement with an offline report and interactive 3D viewer.

This repository contains the complete skill and its supporting tools. Start with [SKILL.md](SKILL.md) for the agent instructions.

## Requirements

- **Codex** with local skill support.
- **Git** for the installation and update commands below.
- **Python 3.9+** for the packaging helper; it uses only the standard library.
- **Blender and a working Blender MCP connection** so the agent can build and inspect the scene. Background Blender may also be used for expensive renders and verification.
- **Web research, downloads, and image inspection** so the agent can collect and inspect photographs, plans, and descriptions.
- **An image generation tool** for material textures. If generation is unavailable, the texture phase is blocked and the agent can deliver an incomplete package.
- **A modern browser** with JavaScript modules, import maps, and WebGL for the interactive viewer. The report remains readable without JavaScript.

Installing this skill does not install Blender, configure MCP connections, or provide access to research or image generation services. Configure those tools in your Codex environment separately.

## Install

Choose one installation location. Keep the complete repository together: the skill needs its scripts, references, and assets as well as `SKILL.md`.

### For all projects

Run in a terminal:

```sh
mkdir -p ~/.agents/skills
git clone https://github.com/getodacu/building-to-3d.git \
  ~/.agents/skills/building-to-3d
```

### For one project

Run from that project's root:

```sh
mkdir -p .agents/skills
git clone https://github.com/getodacu/building-to-3d.git \
  .agents/skills/building-to-3d
```

These are the user and project skill locations described in the [official OpenAI skill documentation](https://learn.chatgpt.com/docs/build-skills). Codex detects newly installed skills automatically; if the skill does not appear, restart Codex.

If the destination already exists, preserve it. Check its contents and Git remote before deciding whether to update it or keep a backup; do not overwrite or delete an existing installation. Install in one location to avoid duplicate skill entries.

### Update

For the all-projects installation:

```sh
git -C ~/.agents/skills/building-to-3d pull --ff-only
```

For a project installation, run from the project's root:

```sh
git -C .agents/skills/building-to-3d pull --ff-only
```

If Git reports local changes or diverging history, preserve your work and resolve that situation before updating. No reset or forced overwrite is needed.

## Use

Invoke the skill in Codex with the building, location, historical state, project folder, and desired refinement count:

```text
Use $building-to-3d to reconstruct the Romanian Athenaeum in Bucharest,
Romania, in its present-day state. Run 2 complete refinement sweeps.
Save the reconstruction project in ./athenaeum-project.
```

The agent researches the building, assesses the available evidence, saves a modeling plan, builds and reviews a blockout, generates textures, visits every section during each refinement sweep, and verifies the saved files before packaging.

The default is **2 complete refinement sweeps**, with **3 total research rounds** including the initial search. Each stage or section visit allows at most **3 corrections**. Research and refinement counts are independent.

The evidence gate requires support for massing and scale, every distinct elevation, roof and courtyard relationships, materials, and defining features. If evidence remains insufficient after the research limit, the agent stops before modeling and explains what additional resources would help. Supplied resources can unblock the project without resetting consumed research rounds. Missing texture generation or unresolved review gates also prevent a completed delivery.

## Outputs

A completed reconstruction includes:

- An editable `.blend` model and a self-contained `.glb` export.
- Research sources, attribution, modeling scripts, generated textures, checkpoints, renders, and comparisons.
- A `project.json` manifest recording evidence, reviews, progress, and limitations.
- An HTML report with a locally bundled Three.js viewer.
- A `package-index.json` integrity index and a sibling ZIP archive.

Incomplete projects can still be packaged, with their incomplete status and blockers shown in the report.

## Package tools

The agent maintains the manifest during reconstruction. These commands are also available for manual initialization, checking, and packaging.

For an all-projects installation, set the paths and initialize a new project:

```sh
SKILL_DIR="$HOME/.agents/skills/building-to-3d"
PROJECT_DIR="$PWD/athenaeum-project"
DELIVERY_DIR="$PWD/athenaeum-delivery"

python3 "$SKILL_DIR/scripts/package.py" init "$PROJECT_DIR"
```

For a project installation, set `SKILL_DIR="$PWD/.agents/skills/building-to-3d"` instead. Initialization creates a manifest and refuses to overwrite an existing one. Follow the [manifest reference](references/manifest.md) when recording work.

Blender creates the `.blend` and `.glb` deliverables during the reconstruction workflow. The packaging helper validates and bundles the registered files; it does not generate or export building geometry.

After the agent has populated the manifest and registered the artifacts:

```sh
python3 "$SKILL_DIR/scripts/package.py" check "$PROJECT_DIR"
python3 "$SKILL_DIR/scripts/package.py" build "$PROJECT_DIR" \
  --output "$DELIVERY_DIR"
```

`check` exits with `0` for complete records, `1` for incomplete or blocked work, and `2` for invalid input or errors. A newly initialized project is incomplete. `build` can package valid incomplete records and labels them accordingly. Choose a fresh output path each time: an existing output directory or sibling ZIP is never overwritten.

Serve the unpacked output locally:

```sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory "$DELIVERY_DIR"
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/). All viewer dependencies are bundled; no internet connection is required to view the package. Use the local server rather than opening the HTML through `file://`, which cannot reliably load the model. Stop the server with Ctrl+C.

## Repository guide

- [SKILL.md](SKILL.md): complete agent workflow and stopping rules.
- [references/workflow.md](references/workflow.md): research acceptance, modeling, review, and final proof.
- [references/manifest.md](references/manifest.md): records, artifacts, hashes, review gates, and packaging.
- [scripts/package.py](scripts/package.py): initialization, validation, and packaging helper.
- [assets](assets/): starter manifest, report styling, and bundled viewer.
- [agents/openai.yaml](agents/openai.yaml): Codex display metadata and default prompt.
- [tests](tests/): packaging tests and optional Blender/browser integration fixtures.

## Development checks

From this repository's root:

```sh
python3 -m unittest discover -s tests -p 'test_package.py'
```

These tests use synthetic records and cover research gates, refinement order, evidence references, file integrity, portable exports, and packaging safety. The separate Blender and browser fixtures require their respective tools; passing the packaging suite does not establish visual fidelity.

## Limitations and attribution

The default scope is the building's present-day exterior. Interiors and grounds are excluded unless requested. A reconstruction derived from photographs is not surveyed or construction-ready. Blender materials can differ from their GLB representation; reviewed Blender renders remain the authority for material appearance, and export differences must be disclosed.

Retain source rights and attribution. Collecting photography for research does not grant permission to redistribute it or use it as a texture. Generated textures are materials, not evidence of the real building.

The skill's code and documentation are licensed under [MIT](LICENSE). The bundled Three.js 0.180.0 files retain their [own MIT license and copyright notice](assets/viewer/vendor/LICENSE.txt); their origin is recorded in [version.json](assets/viewer/vendor/version.json). The repository license does not grant rights to external research sources or generated project content.
