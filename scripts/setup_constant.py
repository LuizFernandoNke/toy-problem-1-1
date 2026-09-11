import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.simulation_config import SimulationConfig

def setup_constant_files(cfg: SimulationConfig, case_dir: Path):
    """
    Gera todos os arquivos da pasta 'constant' (fluidos, turbulência e gravidade)
    utilizando f-strings puras do Python.
    """
    constant_dir = case_dir / "constant"
    constant_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # 1. Configurar Aceleração da Gravidade (constant/g)
    # -------------------------------------------------------------------------
    g_props = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       uniformDimensionedVectorField;
    object      g;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 1 -2 0 0 0 0];
value           (0 -9.81 0);

// ************************************************************************* //
"""
    g_path = constant_dir / "g"
    with open(g_path, "w", encoding="utf-8") as f:
        f.write(g_props)

    # -------------------------------------------------------------------------
    # 2. Configurar Propriedades de Transporte dos Fluidos (constant/transportProperties)
    # -------------------------------------------------------------------------
    sigma_val = getattr(cfg, 'sigma', getattr(cfg, 'surface_tension', 0.03))

    transport_props = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    location    "constant";
    object      transportProperties;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

phases          (water oil);

water
{{
    transportModel  Newtonian;
    nu              {cfg.water.nu};
    rho             {cfg.water.rho};
}}

oil
{{
    transportModel  Newtonian;
    nu              {cfg.oil.nu};
    rho             {cfg.oil.rho};
}}

sigma           {sigma_val};

// ************************************************************************* //
"""
    transport_path = constant_dir / "transportProperties"
    with open(transport_path, "w", encoding="utf-8") as f:
        f.write(transport_props)

    # -------------------------------------------------------------------------
    # 3. Configurar Modelo de Turbulência (constant/turbulenceProperties)
    # -------------------------------------------------------------------------
    turb_props = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    location    "constant";
    object      turbulenceProperties;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

simulationType      RAS;

RAS
{{
    RASModel        {cfg.turbulence_model};

    turbulence      on;

    printCoeffs     on;
}}

// ************************************************************************* //
"""
    # Grava o arquivo exigido pelo solver
    (constant_dir / "turbulenceProperties").write_text(turb_props, encoding="utf-8")
    
    # Grava também momentumTransport por compatibilidade
    (constant_dir / "momentumTransport").write_text(turb_props.replace("turbulenceProperties", "momentumTransport"), encoding="utf-8")


if __name__ == "__main__":
    config = SimulationConfig()
    target_case = Path(__file__).resolve().parent.parent / "template_case"
    setup_constant_files(config, target_case)
    print("Arquivos do diretório 'constant/' gerados com sucesso!")