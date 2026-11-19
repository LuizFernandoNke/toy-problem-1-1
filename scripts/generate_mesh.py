import cmd
import math
import os
import subprocess
import sys
from pathlib import Path

# Add the parent directory to sys.path to allow imports from the config module
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.simulation_config import SimulationConfig

def generate_blockmesh_dict(cfg: SimulationConfig, output_path: Path, wall_expansion_ratio: float = 2.0):
    """Generate a cylindrical O-grid (butterfly) blockMeshDict optimized for stratified bottom film flow."""
    
    # Parâmetros geométricos
    R = cfg.diameter / 2.0
    L = cfg.length
    
    # Raio do núcleo central (50% do raio total)
    r0 = 0.5 * R
    
    # Coordenadas x,y dos vértices (projeção a 45 graus)
    c0 = r0 * math.cos(math.radians(45))  # Núcleo central
    c1 = R * math.cos(math.radians(45))   # Borda externa do tubo
    
    # Parâmetros de resolução da malha (redistribuídos para concentrar células na interface inferior)
    n_core = max(8, int(10 * cfg.mesh_factor))            # Células ao longo do núcleo
    n_radial_bottom = max(18, int(26 * cfg.mesh_factor))  # Mais células no fundo (lâmina de óleo + interface)
    n_radial_other = max(12, int(14 * cfg.mesh_factor))   # Menos células no topo/laterais (gás puro)
    nz = max(10, int(100 * cfg.mesh_factor))              # Células ao longo do comprimento (z)

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
    // ================= Nível z = 0 =================
    ({-c0:.6f} {-c0:.6f} 0.0) // 0
    ( {c0:.6f} {-c0:.6f} 0.0) // 1
    ( {c0:.6f}  {c0:.6f} 0.0) // 2
    ({-c0:.6f}  {c0:.6f} 0.0) // 3

    ( {c1:.6f} {-c1:.6f} 0.0) // 4
    ( {c1:.6f}  {c1:.6f} 0.0) // 5
    ({-c1:.6f}  {c1:.6f} 0.0) // 6
    ({-c1:.6f} {-c1:.6f} 0.0) // 7

    // ================= Nível z = {L:.6f} =================
    ({-c0:.6f} {-c0:.6f} {L:.6f}) // 8
    ( {c0:.6f} {-c0:.6f} {L:.6f}) // 9
    ( {c0:.6f}  {c0:.6f} {L:.6f}) // 10
    ({-c0:.6f}  {c0:.6f} {L:.6f}) // 11

    ( {c1:.6f} {-c1:.6f} {L:.6f}) // 12
    ( {c1:.6f}  {c1:.6f} {L:.6f}) // 13
    ({-c1:.6f}  {c1:.6f} {L:.6f}) // 14
    ({-c1:.6f} {-c1:.6f} {L:.6f}) // 15
);

blocks
(
    // Bloco 0: Núcleo central
    hex (0 1 2 3 8 9 10 11) ({n_core} {n_core} {nz}) simpleGrading (1 1 1)

    // Bloco 1 (INFERIOR - Óleo e Interface): Alta resolução radial
    hex (7 4 1 0 15 12 9 8)   ({n_core} {n_radial_bottom} {nz}) simpleGrading (1 {wall_expansion_ratio} 1)

    // Blocos 2..4 (Laterais e Topo - Gás): Resolução otimizada para Courant e y+
    hex (4 5 2 1 12 13 10 9)   ({n_core} {n_radial_other} {nz}) simpleGrading (1 {wall_expansion_ratio} 1)
    hex (5 6 3 2 13 14 11 10)  ({n_core} {n_radial_other} {nz}) simpleGrading (1 {wall_expansion_ratio} 1)
    hex (6 7 0 3 14 15 8 11)   ({n_core} {n_radial_other} {nz}) simpleGrading (1 {wall_expansion_ratio} 1)
);

edges
(
    // Arcos da parede cilíndrica na entrada (z = 0)
    arc 7 4 (0.0 {-R:.6f} 0.0)
    arc 4 5 ({R:.6f} 0.0 0.0)
    arc 5 6 (0.0 {R:.6f} 0.0)
    arc 6 7 ({-R:.6f} 0.0 0.0)

    // Arcos da parede cilíndrica na saída (z = {L:.6f})
    arc 15 12 (0.0 {-R:.6f} {L:.6f})
    arc 12 13 ({R:.6f} 0.0 {L:.6f})
    arc 13 14 (0.0 {R:.6f} {L:.6f})
    arc 14 15 ({-R:.6f} 0.0 {L:.6f})
);

boundary
(
    inlet
    {{
        type patch;
        faces
        (
            (0 3 2 1)
            (7 0 1 4)
            (4 1 2 5)
            (5 2 3 6)
            (6 3 0 7)
        );
    }}
    outlet
    {{
        type patch;
        faces
        (
            (8 9 10 11)
            (15 8 9 12)
            (12 9 10 13)
            (13 10 11 14)
            (14 11 8 15)
        );
    }}
    walls
    {{
        type wall;
        faces
        (
            (7 4 12 15)
            (4 5 13 12)
            (5 6 14 13)
            (6 7 15 14)
        );
    }}
);

mergePatchPairs
(
);

// ************************************************************************* //
"""

    # Garante que o diretório de destino existe e grava o arquivo
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"File blockMeshDict (Cylindrical Mesh with Wall Refinement) generated in: {output_path}")

if __name__ == "__main__":
    config = SimulationConfig()
    target_path = Path("template_case/system/blockMeshDict")
    
    # wall_expansion_ratio define a razão entre a célula no centro e a célula na parede.
    generate_blockmesh_dict(config, target_path, wall_expansion_ratio=3.0)

    # Executa automaticamente o comando blockMesh no OpenFOAM
    print("Executing blockMesh in OpenFOAM...")

    cmd = "source /usr/lib/openfoam/openfoam2606/etc/bashrc && blockMesh -case template_case"

    result = subprocess.run(
        cmd,
        shell=True,
        executable="/bin/bash",
        capture_output=True,
        text=True,
        env=os.environ.copy()
    )

    if result.returncode != 0:
        print(f"Error generating mesh:\n{result.stderr}")
        sys.exit(1)
    else:
        print("Cylindrical mesh with wall refinement generated successfully!")