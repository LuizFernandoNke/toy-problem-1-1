import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.simulation_config import SimulationConfig


def setup_system_files(cfg: SimulationConfig, case_dir: Path):
    """
    Gera todos os arquivos da pasta 'system' (controlDict, fvSchemes, fvSolution,
    setFieldsDict e decomposeParDict) utilizando f-strings puras do Python.
    """
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------------------
    # 1. Configurar controlDict
    # -------------------------------------------------------------------------
    control_dict = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    object      controlDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

application     interFoam;

startFrom       latestTime;
startTime       0;
stopAt          endTime;
endTime         {getattr(cfg, 'end_time', 5)};
deltaT          {getattr(cfg, 'delta_t', 0.1)};

writeControl    adjustable;
writeInterval   1;
purgeWrite      0;
writeFormat     ascii;
writePrecision  6;
writeCompression on;
timeFormat      general;
timePrecision   6;
runTimeModifiable yes;

adjustTimeStep  yes;
maxCo           1;
maxAlphaCo      1;
maxDeltaT       1;

functions
{{
    inletFlux
    {{
        type            surfaceFieldValue;
        libs            (fieldFunctionObjects);
        writeControl    timeStep;
        log             true;
        writeFields     false;
        regionType      patch;
        name            inlet;
        operation       sum;

        fields
        (
            rhoPhi
        );
    }}

    outletFlux
    {{
        $inletFlux;
        name            outlet;
    }}

    sTransport
    {{
        type            scalarTransport;
        libs            (solverFunctionObjects);

        enabled         true;
        writeControl    writeTime;
        writeInterval   1;

        field           s;
        bounded01       false;
        phase           alpha.water;

        write           true;

        fvOptions
        {{
            unitySource
            {{
                type            scalarSemiImplicitSource;
                enabled         true;

                selectionMode   all;
                volumeMode      specific;

                sources
                {{
                    s           (1 0);
                }}
            }}
        }}

        resetOnStartUp  false;
    }}
}}

// ************************************************************************* //
"""
    (system_dir / "controlDict").write_text(control_dict)

    # -------------------------------------------------------------------------
    # 2. Configurar fvSchemes
    # -------------------------------------------------------------------------
    fv_schemes = """/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       dictionary;
    object      fvSchemes;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

ddtSchemes
{
    default         Euler;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    default             none;

    div(rhoPhi,U)       Gauss linearUpwind grad(U);
    div(phi,alpha)      Gauss vanLeer;
    div(phirb,alpha)    Gauss linear;

    "div\\(phi,(k|omega)\\)"      Gauss upwind;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;

    div(phi,s)   Gauss vanLeer;
    div(phirb,s) Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear corrected;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         corrected;
}

wallDist
{
    method          meshWave;
}

// ************************************************************************* //
"""
    (system_dir / "fvSchemes").write_text(fv_schemes)

    # -------------------------------------------------------------------------
    # 3. Configurar fvSolution
    # -------------------------------------------------------------------------
    fv_solution = """/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       dictionary;
    object      fvSolution;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

solvers
{
    "alpha.water.*"
    {
        nAlphaCorr      1;
        nAlphaSubCycles 1;
        cAlpha          1;

        MULESCorr       yes;
        nLimiterIter    3;

        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0;
    }

    "pcorr.*"
    {
        solver          PCG;
        preconditioner
        {
            preconditioner  GAMG;
            tolerance       1e-5;
            relTol          0;
            smoother        GaussSeidel;
        }
        tolerance       1e-5;
        relTol          0;
        maxIter         50;
    }

    p_rgh
    {
        solver           GAMG;
        tolerance        5e-9;
        relTol           0.01;
        smoother         GaussSeidel;
        maxIter          50;
    };

    p_rghFinal
    {
        $p_rgh;
        tolerance       5e-9;
        relTol          0;
    }

    "(U|k|omega|s).*"
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        nSweeps         1;
        tolerance       1e-6;
        relTol          0.1;
    };
}

PIMPLE
{
    momentumPredictor no;
    nCorrectors     2;
    nNonOrthogonalCorrectors 0;
}

relaxationFactors
{
    equations
    {
        ".*" 1;
    }
}

// ************************************************************************* //
"""
    (system_dir / "fvSolution").write_text(fv_solution)

    # -------------------------------------------------------------------------
    # 4. Configurar setFieldsDict
    # -------------------------------------------------------------------------
    set_fields = """/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       dictionary;
    object      setFieldsDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

defaultFieldValues
(
    volScalarFieldValue alpha.water 0
);

regions
(
    boxToCell
    {
        box (-10 -20 -10) (50 20 2.2);
        fieldValues
        (
            volScalarFieldValue alpha.water 1
        );
    }
);

// ************************************************************************* //
"""
    (system_dir / "setFieldsDict").write_text(set_fields)

    # -------------------------------------------------------------------------
    # 5. Configurar decomposeParDict
    # -------------------------------------------------------------------------
    decompose_par = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    object      decomposeParDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

numberOfSubdomains {cfg.num_processors};
method          scotch;

// ************************************************************************* //
"""
    (system_dir / "decomposeParDict").write_text(decompose_par)

    print("Arquivos do diretório 'system/' gerados com sucesso.")

# -------------------------------------------------------------------------
    # 5. Configurar sampleDict (Pós-processamento de U e P)
    # -------------------------------------------------------------------------
    sample_dict = """/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       dictionary;
    object      sampleDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

type            sets;
libs            ("libsampling.so");
setFormat       raw;

sets
{
    // Linha vertical para capturar o perfil de velocidade U no centro do domínio
    profile_mid
    {
        type        lineCell;
        axis        y;
        start       (0.5 0.0 0.005);
        end         (0.5 0.1 0.005);
    }

    // Linha horizontal no centro do canal para capturar a queda de pressão p_rgh
    center_line
    {
        type        lineCell;
        axis        x;
        start       (0.0 0.05 0.005);
        end         (1.0 0.05 0.005);
    }
}

fields          (U p_rgh p);

// ************************************************************************* //
"""
    (system_dir / "sampleDict").write_text(sample_dict)

def main():
    cfg = SimulationConfig()
    root_dir = Path(__file__).resolve().parent.parent
    case_dir = root_dir / "template_case"
    setup_system_files(cfg, case_dir)


if __name__ == "__main__":
    main()