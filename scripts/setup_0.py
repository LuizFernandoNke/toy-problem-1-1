import sys
from pathlib import Path

# Adiciona o diretório raiz do projeto ao sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.simulation_config import SimulationConfig

def setup_zero_files(cfg: SimulationConfig, case_dir: Path):
    """
    Gera todos os arquivos do diretório 0/ e o setFieldsDict em system/
    para escoamento estratificado com instabilidade de Kelvin-Helmholtz.
    """
    zero_dir = case_dir / "0"
    zero_dir.mkdir(parents=True, exist_ok=True)
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)

    # Velocidades de referência para o cisalhamento (Ar vs Água)
    u_water = getattr(cfg, 'u_water', 0.5)   # m/s (Água mais lenta)
    u_air = getattr(cfg, 'u_air', 5.0)       # m/s (Ar mais rápido)
    u_avg = (u_air + u_water) / 2.0
    du = u_air - u_water

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

internalField   uniform 0; // Preenchido pelo setFields depois

boundaryField
{{
    inlet
    {{
        type            codedFixedValue;
        value           uniform 0;
        name            alphaInletProfile;

        code
        #{{
            const vectorField& C = patch().Cf();
            scalarField& alpha = *this;

            forAll(C, i)
            {{
                // Água na metade inferior (y < 0)
                alpha[i] = (C[i].y() <= 0.0) ? 1.0 : 0.0;
            }}
        #}};
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

    # 2. U (Campo de Velocidades com Cisalhamento tanh entre Fases)
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

internalField   uniform (0 0 {u_avg});

boundaryField
{{
    inlet
    {{
        type            codedFixedValue;
        value           uniform (0 0 {u_avg});
        name            shearInletProfile;

        code
        #{{
            const scalar Uavg = {u_avg:.6f};
            const scalar dU = {du:.6f};
            const scalar delta = 0.002; // Espessura da camada de transição (2mm)

            const vectorField& C = patch().Cf();
            vectorField& U = *this;

            forAll(C, i)
            {{
                scalar y = C[i].y();
                // Perfil em tanh: Água lenta embaixo, Ar rápido em cima
                scalar uz = Uavg + 0.5 * dU * std::tanh(y / delta);
                U[i] = vector(0, 0, uz);
            }}
        #}};
    }}

    outlet
    {{
        type            zeroGradient;
    }}

    walls
    {{
        type            noSlip;
    }}
}}

// ************************************************************************* //
"""
    (zero_dir / "U").write_text(u_content, encoding="utf-8")

    # 3. k (Energia Cinética Turbulenta Baixa)
    k_content = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2606                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      k;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 2 -2 0 0 0 0];

internalField   uniform 1e-05;

boundaryField
{
    inlet
    {
        type            fixedValue;
        value           $internalField;
    }

    walls
    {
        type            kqRWallFunction;
        value           $internalField;
    }

    outlet
    {
        type            zeroGradient;
    }
}

// ************************************************************************* //
"""
    (zero_dir / "k").write_text(k_content, encoding="utf-8")

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
    inlet
    {
        type            fixedValue;
        value           uniform 10;
    }

    walls
    {
        type            omegaWallFunction;
        value           uniform 10;
    }

    outlet
    {
        type            zeroGradient;
    }
}

// ************************************************************************* //
"""
    (zero_dir / "omega").write_text(omega_content, encoding="utf-8")

    # 5. nut (Viscosidade Turbulenta)
    nut_content = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2606                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      nut;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 2 -1 0 0 0 0];

internalField   uniform 0;

boundaryField
{
    walls
    {
        type            nutkWallFunction;
        value           uniform 0;
    }

    ".*"
    {
        type            calculated;
        value           uniform 0;
    }
}

// ************************************************************************* //
"""
    (zero_dir / "nut").write_text(nut_content, encoding="utf-8")

    # 6. p_rgh (Pressão Hidrostática Modificada)
    p_rgh_content = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2606                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      p_rgh;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [1 -1 -2 0 0 0 0];

internalField   uniform 0;

boundaryField
{
    inlet
    {
        type            fixedFluxPressure;
        value           uniform 0;
    }

    outlet
    {
        type            fixedValue;
        value           uniform 0;
    }

    walls
    {
        type            fixedFluxPressure;
        value           uniform 0;
    }
}

// ************************************************************************* //
"""
    (zero_dir / "p_rgh").write_text(p_rgh_content, encoding="utf-8")

    # 7. Criar system/setFieldsDict para preencher a água e aplicar a onda no instante t=0
    R = cfg.diameter / 2.0
    L = cfg.length
    set_fields_dict = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    object      setFieldsDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

defaultFieldValues
(
    volScalarFieldValue alpha.water 0
);

regions
(
    // Preenche a metade inferior com água (y <= 0)
    boxToCell
    {{
        box ({-R*1.1} {-R*1.1} -0.1) ({R*1.1} 0.0 {L*1.1});
        fieldValues
        (
            volScalarFieldValue alpha.water 1
        );
    }}
);

// ************************************************************************* //
"""
    (system_dir / "setFieldsDict").write_text(set_fields_dict, encoding="utf-8")

    print("Ficheiros do diretório '0/' e 'system/setFieldsDict' gerados com sucesso.")

if __name__ == "__main__":
    config = SimulationConfig()
    target_case = Path(__file__).resolve().parent.parent / "template_case"
    setup_zero_files(config, target_case)