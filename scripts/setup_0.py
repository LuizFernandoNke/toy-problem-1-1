import sys
from pathlib import Path

# Adiciona o diretório raiz do projeto ao sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.simulation_config import SimulationConfig

def setup_zero_files(cfg: SimulationConfig, case_dir: Path):
    """
    Gera todos os ficheiros do diretório 0/ e o setFieldsDict em system/
    para escoamento estratificado ÓLEO-ÁGUA com instabilidade de Kelvin-Helmholtz.
    """
    zero_dir = case_dir / "0"
    zero_dir.mkdir(parents=True, exist_ok=True)
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)

    # 1. Leitura correta das variáveis definidas no simulation_config.py
    u_water = cfg.velocity_water  # m/s (Água no fundo)
    u_oil = cfg.velocity_oil      # m/s (Óleo no topo)
    u_avg = (u_oil + u_water) / 2.0
    du = u_oil - u_water

    R = cfg.diameter / 2.0
    L = cfg.length
    
    # Altura base da interface a partir de inlet_alpha_water (0.5 = centro y=0)
    alpha_target = getattr(cfg, 'inlet_alpha_water', 0.5)
    y_base = 0.0 if alpha_target == 0.5 else R * (2.0 * alpha_target - 1.0)

    # --- 1. alpha.water ---
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
        type            codedFixedValue;
        value           uniform 0;
        name            alphaInletProfile;

        code
        #{{
            const vectorField& C = patch().Cf();
            scalarField& alpha = *this;
            const scalar t = db().time().value();

            const scalar R = {R:.6f};
            const scalar y0 = {y_base:.6f};
            // Amplitude ajustada para perturbação entre dois líquidos
            const scalar amplitude = 0.3 * R;
            const scalar freq = 1.; // Hz

            const scalar y_interface = y0 + amplitude * std::sin(2.0 * M_PI * freq * t);

            forAll(C, i)
            {{
                alpha[i] = (C[i].y() <= y_interface) ? 1.0 : 0.0;
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

    # --- 2. U (Campo de Velocidades com Cisalhamento tanh) ---
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
            const scalar y0 = {y_base:.6f};
            const scalar delta = 0.002; // Espessura da camada de transição (2mm)

            const vectorField& C = patch().Cf();
            vectorField& U = *this;

            forAll(C, i)
            {{
                scalar y = C[i].y();
                scalar uz = Uavg + 0.5 * dU * std::tanh((y - y0) / delta);
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

    # --- 3. k ---
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

    # --- 4. omega ---
    omega_content = """/*--------------------------------*- C++ -*----------------------------------*\\
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

    # --- 5. nut ---
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

    # --- 6. p_rgh ---
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

    # --- 7. setFieldsDict ---
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
    boxToCell
    {{
        box ({-R*1.1} {-R*1.1} -0.1) ({R*1.1} {y_base} {L*1.1});
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