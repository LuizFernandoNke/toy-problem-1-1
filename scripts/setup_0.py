import math
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.simulation_config import SimulationConfig


def calcular_y_interface(R: float, alpha_target: float) -> float:
    """
    Calcula a coordenada vertical y_base exata para um segmento circular
    ocupar a fração de área alpha_target dentro de um tubo de raio R.
    """
    if alpha_target <= 0.0:
        return -R
    if alpha_target >= 1.0:
        return R
    if math.isclose(alpha_target, 0.5):
        return 0.0

    target = 2.0 * math.pi * alpha_target
    low, high = 0.0, 2.0 * math.pi
    for _ in range(60):
        mid = 0.5 * (low + high)
        if mid - math.sin(mid) < target:
            low = mid
        else:
            high = mid
    theta = 0.5 * (low + high)
    return -R * math.cos(0.5 * theta)


def calcular_turbulencia_entrada(u_gas: float, D: float) -> tuple[float, float]:
    """
    Estima k e omega desenvolvidos para o escoamento turbulento no duto
    a partir da velocidade real do gás e do diâmetro hidráulico.
    """
    # Intensidade turbulenta típica em dutos (~4.5%) e escala de comprimento l = 0.07 * D
    I = 0.045
    l_turb = 0.07 * D
    C_mu = 0.09

    k_inlet = max(1.5 * (u_gas * I) ** 2, 1e-4)
    omega_inlet = max(math.sqrt(k_inlet) / ((C_mu ** 0.25) * l_turb), 1.0)
    return k_inlet, omega_inlet


def setup_zero_files(cfg: SimulationConfig, case_dir: Path):
    """
    Gera todos os ficheiros do diretório 0/ e o setFieldsDict em system/
    com escoamento estratificado ÓLEO-GÁS já desenvolvido e em movimento desde t = 0s
    (Hagen-Poiseuille no óleo + Perfil de Prandtl-Nikuradse 1/7 no gás).
    """
    zero_dir = case_dir / "0"
    zero_dir.mkdir(parents=True, exist_ok=True)
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)

    # 1. Leitura sincronizada das variáveis do SimulationConfig (Óleo no fundo, Gás no topo)
    u_oil = cfg.velocity_oil  # m/s (Fase inferior - óleo in-situ)
    u_gas = cfg.velocity_gas  # m/s (Fase superior - gás in-situ)
    u_avg = (u_gas + u_oil) / 2.0
    du = u_gas - u_oil

    D = cfg.diameter
    R = D / 2.0
    L = cfg.length

    alpha_target = cfg.inlet_alpha_oil
    y_base = calcular_y_interface(R, alpha_target)
    k_init, omega_init = calcular_turbulencia_entrada(u_gas, D)

    # --- 1. alpha.oil (Domínio inteiro + Entrada já estratificados na cota y_base) ---
    phase_field_name = "alpha.oil"
    alpha_content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    object      {phase_field_name};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 0 0 0 0 0 0];

internalField   #codeStream
{{
    codeInclude
    #{{
        #include "fvCFD.H"
    #}};

    codeOptions
    #{{
        -I$(LIB_SRC)/finiteVolume/lnInclude \\
        -I$(LIB_SRC)/meshTools/lnInclude
    #}};

    codeLibs
    #{{
        -lfiniteVolume \\
        -lmeshTools
    #}};

    code
    #{{
        const IOdictionary& d = static_cast<const IOdictionary&>(dict);
        const fvMesh& mesh = refCast<const fvMesh>(d.db());
        const vectorField& C = mesh.C();

        scalarField alpha(mesh.nCells(), 0.0);
        const scalar y0 = {y_base:.6f};

        forAll(C, i)
        {{
            alpha[i] = (C[i].y() <= y0) ? 1.0 : 0.0;
        }}

        alpha.writeEntry("", os);
    #}};
}};

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
            const scalar y0 = {y_base:.6f};

            forAll(C, i)
            {{
                alpha[i] = (C[i].y() <= y0) ? 1.0 : 0.0;
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
    (zero_dir / phase_field_name).write_text(alpha_content, encoding="utf-8")

    # --- 2. U (Domínio inteiro + Entrada em movimento: Hagen-Poiseuille no Óleo + Prandtl-Nikuradse 1/7 no Gás) ---
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

internalField   #codeStream
{{
    codeInclude
    #{{
        #include "fvCFD.H"
    #}};

    codeOptions
    #{{
        -I$(LIB_SRC)/finiteVolume/lnInclude \\
        -I$(LIB_SRC)/meshTools/lnInclude
    #}};

    codeLibs
    #{{
        -lfiniteVolume \\
        -lmeshTools
    #}};

    code
    #{{
        const IOdictionary& d = static_cast<const IOdictionary&>(dict);
        const fvMesh& mesh = refCast<const fvMesh>(d.db());
        const vectorField& C = mesh.C();

        vectorField U(mesh.nCells(), vector::zero);
        const scalar R = {R:.6f};
        const scalar Uavg = {u_avg:.6f};
        const scalar dU = {du:.6f};
        const scalar y0 = {y_base:.6f};
        const scalar delta = 0.0015; // Camada de transição suave na interface (1.5 mm)

        forAll(C, i)
        {{
            scalar x = C[i].x();
            scalar y = C[i].y();
            scalar r = Foam::sqrt(x * x + y * y);
            scalar rRatio = Foam::min(r / R, 1.0);

            // Fração suave de gás (0 no óleo -> 1 no gás)
            scalar f_gas = 0.5 * (1.0 + std::tanh((y - y0) / delta));

            // Velocidades médias locais de cada fase (in-situ)
            scalar u_oil_mean = Uavg - 0.5 * dU;
            scalar u_gas_mean = Uavg + 0.5 * dU;

            // Perfil parabólico laminar (Hagen-Poiseuille) para o óleo
            scalar prof_oil = 2.0 * (1.0 - rRatio * rRatio);

            // Perfil de Prandtl-Nikuradse (Lei de Potência 1/7) para o gás turbulento
            scalar prof_gas = 1.224 * Foam::pow(Foam::max(1.0 - rRatio, 1e-6), 1.0 / 7.0);

            scalar uz = (1.0 - f_gas) * (u_oil_mean * prof_oil) + f_gas * (u_gas_mean * prof_gas);
            U[i] = vector(0, 0, uz);
        }}

        U.writeEntry("", os);
    #}};
}};

boundaryField
{{
    inlet
    {{
        type            codedFixedValue;
        value           uniform (0 0 {u_avg:.6f});
        name            prandtlNikuradseInletProfile;

        code
        #{{
            const scalar R = {R:.6f};
            const scalar Uavg = {u_avg:.6f};
            const scalar dU = {du:.6f};
            const scalar y0 = {y_base:.6f};
            const scalar delta = 0.0015; // Camada de transição suave na interface (1.5 mm)

            const vectorField& C = patch().Cf();
            vectorField& U = *this;

            forAll(C, i)
            {{
                scalar x = C[i].x();
                scalar y = C[i].y();
                scalar r = Foam::sqrt(x * x + y * y);
                scalar rRatio = Foam::min(r / R, 1.0);

                // Fração suave de gás (0 no óleo -> 1 no gás)
                scalar f_gas = 0.5 * (1.0 + std::tanh((y - y0) / delta));

                // Velocidades médias locais de cada fase (in-situ)
                scalar u_oil_mean = Uavg - 0.5 * dU;
                scalar u_gas_mean = Uavg + 0.5 * dU;

                // Perfil parabólico laminar (Hagen-Poiseuille) para o óleo
                scalar prof_oil = 2.0 * (1.0 - rRatio * rRatio);

                // Perfil de Prandtl-Nikuradse (Lei de Potência 1/7) para o gás turbulento
                scalar prof_gas = 1.224 * Foam::pow(Foam::max(1.0 - rRatio, 1e-6), 1.0 / 7.0);

                scalar uz = (1.0 - f_gas) * (u_oil_mean * prof_oil) + f_gas * (u_gas_mean * prof_gas);
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

    # --- 3. k (Inicializado com intensidade turbulenta do gás) ---
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

internalField   uniform {k_init:.6f};

boundaryField
{{
    inlet
    {{
        type            fixedValue;
        value           $internalField;
    }}

    walls
    {{
        type            kqRWallFunction;
        value           $internalField;
    }}

    outlet
    {{
        type            zeroGradient;
    }}
}}

// ************************************************************************* //
"""
    (zero_dir / "k").write_text(k_content, encoding="utf-8")

    # --- 4. omega (Inicializado com escala turbulenta do gás) ---
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

internalField   uniform {omega_init:.6f};

boundaryField
{{
    inlet
    {{
        type            fixedValue;
        value           uniform {omega_init:.6f};
    }}

    walls
    {{
        type            omegaWallFunction;
        value           uniform {omega_init:.6f};
    }}

    outlet
    {{
        type            zeroGradient;
    }}
}}

// ************************************************************************* //
"""
    (zero_dir / "omega").write_text(omega_content, encoding="utf-8")

    # --- 5. nut (Parede rugosa ou lisa conforme cfg.roughness) ---
    if cfg.roughness > 0:
        walls_nut_block = f"""        type            nutkRoughWallFunction;
        Ks              uniform {cfg.roughness};
        Cs              uniform 0.5;
        value           uniform 0;"""
    else:
        walls_nut_block = """        type            nutkWallFunction;
        value           uniform 0;"""

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
{walls_nut_block}
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

    # --- 7. setFieldsDict (Mantido para compatibilidade com o pipeline) ---
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

// Região superior (Gás): alpha.oil = 0 e U = u_gas
defaultFieldValues
(
    volScalarFieldValue {phase_field_name} 0
    volVectorFieldValue U (0 0 {u_gas:.6f})
);

regions
(
    // Região inferior (Óleo): alpha.oil = 1 e U = u_oil
    boxToCell
    {{
        box ({-R*1.1:.6f} {-R*1.1:.6f} -0.1) ({R*1.1:.6f} {y_base:.6f} {L*1.1:.6f});
        fieldValues
        (
            volScalarFieldValue {phase_field_name} 1
            volVectorFieldValue U (0 0 {u_oil:.6f})
        );
    }}
);

// ************************************************************************* //
"""
    (system_dir / "setFieldsDict").write_text(set_fields_dict, encoding="utf-8")

    print(
        f"Ficheiros '0/' gerados com sucesso: y_base={y_base:.5f}m, "
        f"u_oil={u_oil:.4f}m/s, u_gas={u_gas:.4f}m/s, k={k_init:.5f}, omega={omega_init:.2f}."
    )


if __name__ == "__main__":
    config = SimulationConfig()
    target_case = Path(__file__).resolve().parent.parent / "template_case"
    setup_zero_files(config, target_case)