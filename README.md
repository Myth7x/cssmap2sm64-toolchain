# bsp counter-strike:source to fast64 export Conversion Pipeline
This is a sub project of a larger effort to create a comprehensive Source-to-SM64 conversion pipeline. 
So normal sm64 levels are not compatible with this pipeline, and the output of this pipeline is not compatible with normal sm64 levels.

## Overview
This project converts a Source Engine `.bsp` map (e.g. Counter-Strike: Source) into a Super Mario 64–compatible level format.

The pipeline extracts geometry, processes it through Blender, and exports it using Fast64.

---

## Setup

1. Download `bspsource.jar` and place it in the `vendor/` directory.
2. Download 'Fast64' and place it in the `vendor/` directory.
3. Install Blender and ensure it's added to your system PATH.
4. Build the project:
cmake -B build
cmake --build build
5. Generate pipeline configuration:
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

### 5. (Optional) Convert to compatible native map format
- Using custom module f64_to_native
