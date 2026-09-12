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
| =========                                                                 |
| \\      /  F ield         OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     Version:  v2606                                 |
|   \\  /    A nd           Website:  www.openfoam.com                      |
|    \\/     M anipulation                                                  |
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
    "div\(.*phi.*,U\)"                      Gauss linearUpwind grad(U);
    
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
    # 2. fvSolution (Solucoes de Matriz atualizadas com pcorr)
    # -------------------------------------------------------------------------
    fv_solution = """/*--------------------------------*- C++ -*----------------------------------*\\
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
    object      fvSolution;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

solvers
{
    "alpha.water.*"
    {
        nAlphaCorr      2;
        nAlphaSubCycles 1;
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

    "(U|k|epsilon|omega|B|nuTilda).*"
    {
        solver          PBiCGStab;
        preconditioner  DILU;
        tolerance       1e-08;
        relTol          0.1;
    }
}

PIMPLE
{
    momentumPredictor   yes;
    nCorrectors         2;
    nNonOrthogonalCorrectors 0;
}

// Limites numéricos para prevenir estouros em modelos k-omega SST
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
    end_time = getattr(cfg, 'end_time', 10)
    delta_t = getattr(cfg, 'delta_t', 0.1)

    control_dict = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                                                                 |
| \\\\      /  F ield         OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     Version:  v2606                                 |
|   \\\\  /    A nd           Website:  www.openfoam.com                      |
|    \\\\/     M anipulation                                                  |
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
writeControl    timeStep;
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
    # 4. sampleDict (Amostragem para Delta P e Perfil de Velocidade)
    # -------------------------------------------------------------------------
    R = getattr(cfg, 'diameter', 0.05) / 2.0
    L = getattr(cfg, 'length', 2.0)
    
    y_min, y_max = -R, R
    z_sample = L * 0.875  # 1.75 m para L = 2.0 m
    
    sample_dict = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                                                                 |
| \\\\      /  F ield         OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     Version:  v2606                                 |
|   \\\\  /    A nd           Website:  www.openfoam.com                      |
|    \\\\/     M anipulation                                                  |
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
    // Perfil de velocidade transversal
    profile_mid
    {{
        type            uniform;
        axis            y;
        start           (0 {y_min*0.95} {z_sample});
        end             (0 {y_max*0.95} {z_sample});
        nPoints         100;
    }}
    // Linha central para calcular Delta P ao longo de Z
    center_line
    {{
        type            uniform;
        axis            z;
        start           (0 0 {L*0.01});
        end             (0 0 {L*0.99});
        nPoints         200;
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
    # 5. decomposeParDict (Configuração de Decomposição Paralela)
    # -------------------------------------------------------------------------
    decompose_par_dict = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                                                                  |
| \\\\      /  F ield         OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     Version:  v2606                                |
|   \\\\  /    A nd           Website:  www.openfoam.com                      |
|    \\\\/     M anipulation                                                   |
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