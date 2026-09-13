import sys
from pathlib import Path

# Adiciona o diretório raiz do projeto ao sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.simulation_config import SimulationConfig

def setup_zero_files(cfg: SimulationConfig, case_dir: Path):
    """
    Gera todos os arquivos do diretório 0/ (condições iniciais e de contorno)
    para a simulação multifásica interFoam (com transição suave para Kelvin-Helmholtz).
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
    omega_content = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                                                                 |
| \\\\      /  F ield         OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     Version:  v2606                                 |
|   \\\\  /    A nd           Website:  www.openfoam.com                      |
|    \\\\/     M anipulation                                                  |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      omega;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 0 -1 0 0 0 0];

internalField   uniform 10;

boundaryField
{
    walls
    {
        type            omegaWallFunction;
        value           uniform 10;
    }

    inlet
    {
        type            fixedValue;
        value           uniform 10;
    }

    outlet
    {
        type            zeroGradient;
    }

    atmosphere
    {
        type            inletOutlet;
        inletValue      uniform 10;
        value           uniform 10;
    }
}

// ************************************************************************* //
"""
    (zero_dir / "omega").write_text(omega_content, encoding="utf-8")

    # 5. epsilon (Taxa de Dissipação da Energia Cinética Turbulenta)
    epsilon_content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                                                                 |
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
    object      epsilon;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 2 -3 0 0 0 0];

internalField   uniform 0.001;

boundaryField
{{
    inlet
    {{
        type            fixedValue;
        value           $internalField;
    }}

    walls
    {{
        type            epsilonWallFunction;
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
    (zero_dir / "epsilon").write_text(epsilon_content, encoding="utf-8")

    # 6. p_rgh (Pressão Hidrostática Modificada)
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

    # 7. U (Campo de Velocidades com Transição Suave via tanh)
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

internalField   uniform (0 0 {getattr(cfg, 'initial_velocity_x', 1e-6)});

boundaryField
{{
    inlet
    {{
        type            codedFixedValue;
        value           uniform (0 0 0);
        name            velocityProfileKH;

        code
        #{'{'}
            const vectorField& Cf = patch().Cf();
            vectorField& Upatch = *this;

            const scalar U_water = {cfg.velocity_water};
            const scalar U_oil = {cfg.velocity_oil};

            forAll(Cf, i)
            {{
                scalar y = Cf[i].y();
                // Transição suave em uma camada limite de 2mm ao redor da interface (y = 0)
                scalar blend = 0.5 * (1.0 + std::tanh(y / 0.002));
                Upatch[i] = vector(0, 0, U_water * (1.0 - blend) + U_oil * blend);
            }}
        #{'}'};
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
    target_case = Path(__file__).resolve().parent.parent / "template_case"
    setup_zero_files(config, target_case)
    print("Arquivos do diretório '0/' gerados com sucesso")

if __name__ == "__main__":
    main()