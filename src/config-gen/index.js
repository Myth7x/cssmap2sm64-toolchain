const prompts = require('prompts');
const path = require('path');
const fs = require('fs');

(async () => {
    const questions = [
        {
            type: 'text',
            name: 'decomp_path',
            message: 'Path to SM64 decomp repo',
            validate: v => fs.existsSync(v) && fs.statSync(v).isDirectory()
                ? true
                : 'Directory not found'
        },
        {
            type: 'text',
            name: 'blender_path',
            message: 'Path to Blender executable',
            validate: v => fs.existsSync(v) ? true : 'Executable not found'
        },
        {
            type: 'text',
            name: 'java_path',
            message: 'Path to java executable (or "java" for PATH)',
            initial: 'java'
        },
        {
            type: 'text',
            name: 'level_name',
            message: 'Level name (e.g. "bob" for Bob-omb Battlefield, or a custom name)',
            initial: 'custom_level'
        },
        {
            type: 'confirm',
            name: 'is_custom_level',
            message: 'Is this a new custom level (not replacing an existing one)?',
            initial: true
        },
        {
            type: 'number',
            name: 'area_id',
            message: 'Area ID (1-8)',
            initial: 1,
            min: 1,
            max: 8
        },
        {
            type: 'number',
            name: 'scale_factor',
            message: 'VMF scale factor (applied to OBJ vertex positions)',
            initial: 1.0,
            float: true
        },
        {
            type: 'number',
            name: 'blender_to_sm64_scale',
            message: 'Blender to SM64 scale (Fast64 setting)',
            initial: 300
        },
        {
            type: 'number',
            name: 'collision_divisor',
            message: 'Collision scale divisor (divides Fast64 coords to fit s16 ±32768)',
            initial: 150
        },
        {
            type: 'number',
            name: 'texture_resolution_limit',
            message: 'Max texture dimension',
            initial: 512
        }
    ];

    const response = await prompts(questions, {
        onCancel: () => {
            process.stderr.write('Aborted.\n');
            process.exit(1);
        }
    });

    const config = {
        decomp_path: path.resolve(response.decomp_path),
        blender_path: path.resolve(response.blender_path),
        java_path: response.java_path,
        level_name: response.level_name,
        is_custom_level: response.is_custom_level,
        area_id: response.area_id,
        scale_factor: response.scale_factor,
        blender_to_sm64_scale: response.blender_to_sm64_scale,
        texture_resolution_limit: response.texture_resolution_limit
    };

    const out = path.join(process.cwd(), 'pipeline.json');
    fs.writeFileSync(out, JSON.stringify(config, null, 2));
    process.stdout.write(`Written: ${out}\n`);
})();
