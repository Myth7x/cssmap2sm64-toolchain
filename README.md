# CSS Map to SM64 Conversion Pipeline

## Overview
This project converts a Source Engine `.bsp` map (e.g. Counter-Strike: Source) into a Super Mario 64–compatible level format.

The pipeline extracts geometry, processes it through Blender, and exports it using SM64 tooling.

---

## Setup

1. Download `bspsource.jar` and place it in the `vendor/` directory.

2. Build the project:
cmake -B build
cmake --build build

3. Generate pipeline configuration:
node src/config-gen/index.js

This creates `pipeline.json`.

---

## Usage

Run the full pipeline:
python -m cssmap2sm64 yourmap.bsp

---

## Pipeline Steps

### 1. BSP Extraction
- Tool: BSPSource
- Input: `.bsp`
- Output: `.vmf`
- Purpose: Convert compiled Source map into editable format

### 2. Geometry Conversion
- Extract geometry from `.vmf`
- Convert into:
  - `.obj` (preferred), or
  - `.smd` / `.dmx`

### 3. Blender Processing
- Import geometry into Blender
- Perform cleanup:
  - Remove invisible faces
  - Fix flipped normals
  - Apply correct scale (critical for SM64)

### 4. SM64 Export
- Tool: Fast64 (Blender plugin)
- Convert `.blend` scene into SM64-compatible level data

### 5. (Optional) Convert to compatible native map format NEED IMPLEMENTATION

---

## Notes

- Some geometry may require manual cleanup after import.
- Source maps often contain non-manifold or unnecessary geometry.
- Scale mismatches are common; verify dimensions before export.
- Props and models may need separate extraction and handling.
