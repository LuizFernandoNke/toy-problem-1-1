import os
import subprocess
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

ROOT_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT_DIR / "runs"
OF_ENV = "source /usr/lib/openfoam/openfoam2606/etc/bashrc && "

def ensure_sample_dict(case_path: Path):
    """Garante a gravação do system/sampleDict com sintaxe rigorosa para OpenFOAM v2606."""
    target_sample = case_path / "system" / "sampleDict"
    
    # Sintaxe estrita do dicionario com FoamFile correto
    sample_content = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  2606                                  |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      sampleDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

type            sets;
libs            ("libsampling.so");

writeControl    writeTime;
interpolationScheme cellPoint;
setFormat       raw;

sets
(
    profile_mid
    {
        type        lineCell;
        axis        y;
        start       (0.5 0.0 0.005);
        end         (0.5 0.1 0.005);
    }

    center_line
    {
        type        lineCell;
        axis        x;
        start       (0.0 0.05 0.005);
        end         (1.0 0.05 0.005);
    }
);

fields          (U p_rgh p);

// ************************************************************************* //
"""
    target_sample.parent.mkdir(parents=True, exist_ok=True)
    target_sample.write_text(sample_content, encoding="utf-8")

def get_latest_sample_dir(case_path: Path) -> Path:
    """Garante a regeneração do dicionário e executa a amostragem."""
    ensure_sample_dict(case_path)

    possible_dirs = [
        case_path / "postProcessing" / "sampleDict",
        case_path / "postProcessing" / "sets"
    ]

    # Executa postProcess apontando para system/sampleDict
    cmd = f"bash -c '{OF_ENV} postProcess -case {case_path} -dict system/sampleDict -latestTime'"
    subprocess.run(cmd, shell=True, capture_output=True)

    target_dir = None
    for p in possible_dirs:
        if p.exists():
            target_dir = p
            break

    if not target_dir:
        raise FileNotFoundError(f"Erro ao processar {case_path}: pasta postProcessing não foi criada.")

    time_dirs = [d for d in target_dir.iterdir() if d.is_dir() and d.name.replace('.', '', 1).isdigit()]
    if not time_dirs:
        raise FileNotFoundError(f"Nenhum diretório de tempo encontrado em {target_dir}")

    return sorted(time_dirs, key=lambda x: float(x.name))[-1]

def calculate_delta_p(case_path: Path) -> float:
    """Calcula a queda de pressão ΔP."""
    latest_dir = get_latest_sample_dir(case_path)
    
    p_file = latest_dir / "center_line_p_rgh.xy"
    if not p_file.exists():
        p_file = latest_dir / "center_line_p.xy"
    if not p_file.exists():
        p_files = list(latest_dir.glob("center_line_p*"))
        if not p_files:
            raise FileNotFoundError(f"Arquivo de pressão não encontrado em {latest_dir}")
        p_file = p_files[0]

    df = pd.read_csv(p_file, sep=r'\s+', comment='#', header=None)
    p_inlet = df.iloc[0, 1]
    p_outlet = df.iloc[-1, 1]
    return p_inlet - p_outlet

def plot_comparison():
    models = {
        "kEpsilon": {"folder": "run_kEpsilon", "color": "blue", "ls": "--"},
        "kOmegaSST": {"folder": "run_kOmegaSST", "color": "red", "ls": "-"}
    }

    fig, ax = plt.subplots(figsize=(8, 6))

    print("\n" + "=" * 60)
    print("GRADIENTE E QUEDA DE PRESSÃO TOTAL (ΔP)")
    print("=" * 60)

    for name, config in models.items():
        case_path = RUNS_DIR / config["folder"]
        
        delta_p = calculate_delta_p(case_path)
        print(f"Modelo {name:12s} | ΔP Total: {delta_p:.4f} Pa")

        latest_dir = get_latest_sample_dir(case_path)
        u_files = list(latest_dir.glob("profile_mid_U*"))
        if not u_files:
            raise FileNotFoundError(f"Arquivo de velocidade U não encontrado em {latest_dir}")
        
        df_u = pd.read_csv(u_files[0], sep=r'\s+', comment='#', header=None)
        y = df_u.iloc[:, 0]
        ux = df_u.iloc[:, 1]
        
        ax.plot(ux, y, label=f'RANS: {name}', color=config["color"], linestyle=config["ls"], linewidth=2)

    print("=" * 60 + "\n")

    ax.set_title("Perfil Comparativo de Velocidade $U_x$")
    ax.set_xlabel("Velocidade $U_x$ [m/s]")
    ax.set_ylabel("Posição Vertical $y$ [m]")
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend()

    output_path = ROOT_DIR / "rans_velocity_comparison.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"[GRÁFICO] Imagem salva em: {output_path}")

if __name__ == "__main__":
    plot_comparison()