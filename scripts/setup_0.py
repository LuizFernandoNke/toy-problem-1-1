import sys
from pathlib import Path

# Adiciona o diretório raiz do projeto ao sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.simulation_config import SimulationConfig

def setup_zero_files(cfg: SimulationConfig, case_dir: Path):
    """
    Gera todos os arquivos do diretório 0/ (condições iniciais e de contorno)
    para a simulação multifásica interFoam.
    """
    zero_dir = case_dir / "0"
    zero_dir.mkdir(parents=True, exist_ok=True)

    # 1. alpha.water (Fração de fase)
    alpha_water_content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       volScalarField;
    object      alpha.water;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 0 0 0 0 0 0];

internalField   uniform 0;

boundaryField
{{
    inlet
    {{
        type            fixedValue;
        value           uniform {cfg.inlet_alpha_water};
    }}

    walls
    {{
        type            zeroGradient;
    }}

    outlet
    {{
        type            zeroGradient;
    }}
}}

// ************************************************************************* //
"""
    (zero_dir / "alpha.water").write_text(alpha_water_content, encoding="utf-8")

    # 2. k (Energia Cinética Turbulenta)
    k_content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       volScalarField;
    object      k;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 2 -2 0 0 0 0];

internalField   uniform 0.0001;

boundaryField
{{
    inlet
    {{
        type            fixedValue;
        intensity       0.05;
        value           $internalField;
    }}

    walls
    {{
        type            kqRWallFunction;
        value           $internalField;
    }}

    ".*"
    {{
        type            inletOutlet;
        inletValue      $internalField;
        value           $internalField;
    }}
}}

// ************************************************************************* //
"""
    (zero_dir / "k").write_text(k_content, encoding="utf-8")

    # 3. nut (Viscosidade Turbulenta Cinemática)
    nut_content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       volScalarField;
    object      nut;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 2 -1 0 0 0 0];

internalField   uniform 0;

boundaryField
{{
    walls
    {{
        type            nutkWallFunction;
        value           uniform 0;
    }}

    ".*"
    {{
        type            calculated;
        value           uniform 0;
    }}
}}

// ************************************************************************* //
"""
    (zero_dir / "nut").write_text(nut_content, encoding="utf-8")

    # 4. omega (Taxa de Dissipação Específica)
    omega_content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       volScalarField;
    object      omega;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 0 -1 0 0 0 0];

internalField   uniform 0.003;

boundaryField
{{
    inlet
    {{
        type            fixedValue;
        value           $internalField;
    }}

    walls
    {{
        type            omegaWallFunction;
        value           $internalField;
    }}

    ".*"
    {{
        type            inletOutlet;
        inletValue      $internalField;
        value           $internalField;
    }}
}}

// ************************************************************************* //
"""
    (zero_dir / "omega").write_text(omega_content, encoding="utf-8")

    # 5. p_rgh (Pressão Hidrostática Modificada)
    p_rgh_content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       volScalarField;
    object      p_rgh;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [1 -1 -2 0 0 0 0];

internalField   uniform 0;

boundaryField
{{
    inlet
    {{
        type            fixedFluxPressure;
        value           uniform 0;
    }}

    outlet
    {{
        type            fixedValue;
        value           uniform 0;
    }}

    walls
    {{
        type            fixedFluxPressure;
        value           uniform 0;
    }}
}}

// ************************************************************************* //
"""
    (zero_dir / "p_rgh").write_text(p_rgh_content, encoding="utf-8")

    # 6. U (Campo de Velocidades)
    u_content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       volVectorField;
    object      U;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 1 -1 0 0 0 0];

internalField   uniform ({getattr(cfg, 'initial_velocity_x', 0.0)} 0 0);

boundaryField
{{
    inlet
    {{
        type            fixedValue;
        value           uniform (0 0 {cfg.velocity_inlet});
    }}

    walls
    {{
        type            noSlip;
    }}

    outlet
    {{
        type            inletOutlet;
        inletValue      uniform (0 0 0);
        value           $internalField;
    }}
}}

// ************************************************************************* //
"""
    (zero_dir / "U").write_text(u_content, encoding="utf-8")

def main():
    config = SimulationConfig()
    # Aponta exatamente para a pasta utilizada no run_pipeline.py
    target_case = Path(__file__).resolve().parent.parent / "template_case"
    setup_zero_files(config, target_case)
    print("Arquivos do diretório '0/' gerados com sucesso")

if __name__ == "__main__":
    main()