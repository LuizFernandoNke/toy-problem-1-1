import os
import subprocess
import sys
from pathlib import Path

# Adiciona o diretório raiz ao sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.simulation_config import SimulationConfig

def generate_blockmesh_dict(cfg: SimulationConfig, output_path: Path):
    """Generate the blockMeshDict file for a cylindrical/prismatic duct based on the config."""
    
    # Parametros do Pydantic
    R = cfg.diameter / 2.0
    L = cfg.length
    
    # Resolução da malha
    nx = cfg.nx
    ny = cfg.ny
    nz = cfg.nz

    content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2606                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

scale 1;

vertices
(
    ({-R} {-R} 0)
    ( {R} {-R} 0)
    ( {R}  {R} 0)
    ({-R}  {R} 0)
    ({-R} {-R} {L})
    ( {R} {-R} {L})
    ( {R}  {R} {L})
    ({-R}  {R} {L})
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)
);

edges
(
);

boundary
(
    inlet
    {{
        type patch;
        faces
        (
            (0 3 2 1)
        );
    }}
    outlet
    {{
        type patch;
        faces
        (
            (4 5 6 7)
        );
    }}
    walls
    {{
        type wall;
        faces
        (
            (0 1 5 4)
            (1 2 6 5)
            (2 3 7 6)
            (3 0 4 7)
        );
    }}
);

mergePatchPairs
(
);

// ************************************************************************* //
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"File blockMeshDict generated in directory: {output_path}")

if __name__ == "__main__":
    config = SimulationConfig()
    target_path = Path(__file__).resolve().parent.parent / "template_case" / "system" / "blockMeshDict"
    generate_blockmesh_dict(config, target_path)