import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.simulation_config import SimulationConfig

def setup_system_files(cfg: SimulationConfig, case_dir: Path):
    """
    Gera todos os arquivos do diretório 'system' (controlDict, fvSchemes, fvSolution, sampleDict e decomposeParDict).
    """
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # 1. fvSchemes (Compatível com kEpsilon e kOmegaSST)
    # -------------------------------------------------------------------------
    fv_schemes = r"""/*--------------------------------*- C++ -*----------------------------------*\
| =========                                                                |
| \\      /  F ield         OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     Version:  v2606                                |
|   \\  /    A nd           Website:  www.openfoam.com                     |
|    \\/     M anipulation                                                 |
\*---------------------------------------------------------------------------*/
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
    default                         none;
    
    // Campo de velocidade/momento
    "div\(.*phi.*,U\)"                      Gauss upwind;
    
    // Multifase (VOF / alpha)
    "div\(phi,alpha.*\)"                    Gauss vanLeer;
    "div\(phirb,alpha.*\)"                  Gauss linear;
    
    // Campos de Turbulencia RANS (k, epsilon, omega, nut)
    "div\(.*phi.*,(k|epsilon|omega|nut)\)"  Gauss upwind;
    
    // Tensores de viscosidade e termos difusivos
    "div\(.*dev2\(T\(grad\(U\)\)\)\)"       Gauss linear;
    
    // Fallback generico
    "div\(.*\)"                             Gauss linear;
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

// Calculo de distancia da parede exigido pelo kOmegaSST
wallDist
{
    method          meshWave;
}

// ************************************************************************* //
"""
    (system_dir / "fvSchemes").write_text(fv_schemes, encoding="utf-8")

    # -------------------------------------------------------------------------
    # 2. fvSolution (Solucoes Estaveis com smoothSolver para Turbulencia)
    # -------------------------------------------------------------------------
    fv_solution = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                                                                |
| \\\\      /  F ield         OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     Version:  v2606                                |
|   \\\\  /    A nd           Website:  www.openfoam.com                     |
|    \\\\/     M anipulation                                                 |
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
        nAlphaCorr      2;
        nAlphaSubCycles 2;
        cAlpha          1;
    }

    "(pcorr|pcorrFinal)"
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-05;
        relTol          0;
    }

    "(p_rgh|p_rghFinal)"
    {
        solver          GAMG;
        tolerance       1e-07;
        relTol          0.01;
        smoother        GaussSeidel;
    }

    "U.*"
    {
        solver          PBiCGStab;
        preconditioner  DILU;
        tolerance       1e-08;
        relTol          0.1;
    }

    "(k|epsilon|omega|B|nuTilda).*"
    {
        solver          smoothSolver;
        smoother        GaussSeidel;
        nSweeps         1;
        tolerance       1e-06;
        relTol          0.1;
    }
}

PIMPLE
{
    momentumPredictor   yes;
    nOuterCorrectors            3;
    nCorrectors         3;
    nNonOrthogonalCorrectors 2;
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
    (system_dir / "fvSolution").write_text(fv_solution, encoding="utf-8")

    # -------------------------------------------------------------------------
    # 3. controlDict
    # -------------------------------------------------------------------------
    """end_time = getattr(cfg, 'end_time', 10)
    delta_t = getattr(cfg, 'delta_t', 0.1)"""

    control_dict = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                                                                |
| \\\\      /  F ield         OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     Version:  v2606                                |
|   \\\\  /    A nd           Website:  www.openfoam.com                     |
|    \\\\/     M anipulation                                                 |
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
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {cfg.end_time};
deltaT          {cfg.delta_t};
writeControl    runTime;
writeInterval   {cfg.write_interval};
purgeWrite      0;
writeFormat     ascii;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;
adjustTimeStep  yes;
maxCo           {cfg.max_co};
maxAlphaCo      {cfg.max_alpha_co};
maxDeltaT       {cfg.max_delta_t};

// ************************************************************************* //
"""
    (system_dir / "controlDict").write_text(control_dict, encoding="utf-8")

    # -------------------------------------------------------------------------
    # 4. sampleDict
    # -------------------------------------------------------------------------
    R = getattr(cfg, 'diameter', 0.05) / 2.0
    L = getattr(cfg, 'length', 2.0)
    
    y_min, y_max = -R, R
    z_sample = L * 0.875 
    
    z_start_dev = L * 0.6
    z_end_dev = L * 0.95
    
    sample_dict = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                                                                |
| \\\\      /  F ield         OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     Version:  v2606                                |
|   \\\\  /    A nd           Website:  www.openfoam.com                     |
|    \\\\/     M anipulation                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      sampleDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

type            sets;
writeControl    writeTime;
interpolationScheme cellPoint;
setFormat       raw;

sets
(
    profile_mid
    {{
        type            uniform;
        axis            y;
        start           (0 {y_min*0.95} {z_sample});
        end             (0 {y_max*0.95} {z_sample});
        nPoints         100;
    }}

    center_line
    {{
        type            uniform;
        axis            z;
        start           (0 0 {z_start_dev});
        end             (0 0 {z_end_dev});
        nPoints         100;
    }}
);

fields
(
    p_rgh
    U
);

// ************************************************************************* //
"""
    (system_dir / "sampleDict").write_text(sample_dict, encoding="utf-8")

    # -------------------------------------------------------------------------
    # 5. decomposeParDict
    # -------------------------------------------------------------------------
    decompose_par_dict = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                                                                |
| \\\\      /  F ield         OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     Version:  v2606                                |
|   \\\\  /    A nd           Website:  www.openfoam.com                     |
|    \\\\/     M anipulation                                                 |
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
    (system_dir / "decomposeParDict").write_text(decompose_par_dict, encoding="utf-8")

    print("Arquivos do diretório 'system/' (incluindo decomposeParDict) gerados com sucesso.")

if __name__ == "__main__":
    config = SimulationConfig()
    target_case = Path(__file__).resolve().parent.parent / "template_case"
    setup_system_files(config, target_case)