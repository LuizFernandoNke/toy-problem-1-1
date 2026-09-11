import os
import sys
import subprocess
import re
import math
import argparse
from pathlib import Path

# Adiciona a raiz ao path do Python
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from config.simulation_config import SimulationConfig

# Detecta e prepara a variável do OpenFOAM
def get_openfoam_env() -> str:
    possible_paths = [
        "/usr/lib/openfoam/openfoam2606/etc/bashrc",
        "/opt/openfoam2606/etc/bashrc",
        os.path.expanduser("~/OpenFOAM/openfoam2606/etc/bashrc"),
        "/usr/lib/openfoam/openfoam/etc/bashrc",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return f"source {path} && "
    return "source /usr/lib/openfoam/openfoam2606/etc/bashrc && "

OF_ENV = get_openfoam_env()


def parse_args():
    parser = argparse.ArgumentParser(description="Pós-processamento do OpenFOAM")
    parser.add_argument("-case", type=str, default=None, help="Caminho do caso")
    parser.add_argument("--pre", action="store_true", help="Validação pré-simulação")
    return parser.parse_args()


def count_mesh_cells(case_dir: Path) -> int:
    """Extrai a contagem de células via checkMesh após a reconstrução do caso."""
    current_env = os.environ.copy()
    cmd = f"{OF_ENV} checkMesh -case {case_dir} -time 0"
    res = subprocess.run(cmd, shell=True, executable="/bin/bash", capture_output=True, text=True, env=current_env)
    
    match = re.search(r"cells:\s*(\d+)", res.stdout)
    if match:
        return int(match.group(1))
        
    # Fallback no log.blockMesh
    log_mesh = case_dir / "log.blockMesh"
    if log_mesh.exists():
        content = log_mesh.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"Creating cells\s*:\s*total:(\d+)", content)
        if match:
            return int(match.group(1))

    return 0


def validate_mesh_pre_run(cfg: SimulationConfig, case_dir: Path):
    """Executa a validação da malha ANTES de iniciar a simulação principal."""
    n_cells = count_mesh_cells(case_dir)
    print("\n" + "=" * 60)
    print(f"PRÉ-VALIDAÇÃO DA MALHA [{case_dir.name}]")
    print("=" * 60)
    print(f"Número Total de Células     : {n_cells}")
    print(f"Resolução da Malha (Nx,Ny,Nz): {cfg.nx} x {cfg.ny} x {cfg.nz}")
    
    dh = cfg.diameter
    velocity = cfg.velocity_inlet
    rho_water = cfg.water.rho
    mu_water = cfg.water.rho * cfg.water.nu

    re_water = (rho_water * velocity * dh) / mu_water
    
    print(f"Diâmetro Hidráulico (Dh)    : {dh:.4f} m")
    print(f"Número de Reynolds (Água)   : {re_water:.2f}")
    if re_water > 4000:
        print("Regime de Escoamento       : Turbulento")
    elif re_water < 2300:
        print("Regime de Escoamento       : Laminar")
    else:
        print("Regime de Escoamento       : Transição")
    print("=" * 60 + "\n")


def get_wall_yplus(case_dir: Path) -> dict:
    """Executa o cálculo e captura os dados de y+."""
    current_env = os.environ.copy()
    
    # Executa o pós-processamento do yPlus no OpenFOAM
    cmd_yplus = f"{OF_ENV} interFoam -case {case_dir} -postProcess -func yPlus -latestTime"
    res = subprocess.run(
        cmd_yplus, shell=True, executable="/bin/bash", capture_output=True, text=True, env=current_env
    )
    
    output = res.stdout
    match = re.search(r"patch\s+\w+\s+y\+\s*:\s*min\s*=\s*([\d\.]+),\s*max\s*=\s*([\d\.]+),\s*average\s*=\s*([\d\.]+)", output)
    if match:
        return {
            "min": float(match.group(1)),
            "max": float(match.group(2)),
            "avg": float(match.group(3))
        }

    # Fallback: Tenta buscar nos arquivos .dat do postProcess
    post_dir = case_dir / "postProcess"
    if post_dir.exists():
        for dat_file in post_dir.rglob("*.dat"):
            with open(dat_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "wall" in line.lower():
                        parts = line.split()
                        try:
                            return {"min": float(parts[1]), "max": float(parts[2]), "avg": float(parts[3])}
                        except (IndexError, ValueError):
                            continue

    return {"min": 0.0, "max": 0.0, "avg": 0.0}


def get_performance_metrics(case_dir: Path):
    """Extrai contagem de núcleos e tempo de execução procurando qualquer log do interFoam."""
    execution_time = "N/A"
    
    # Procura qualquer log gerado (ex: interFoam.log, interFoam_kEpsilon.log...)
    log_files = list(case_dir.glob("*.log")) + list(case_dir.glob("log.*"))
    for log_path in log_files:
        if "interFoam" in log_path.name:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in reversed(f.readlines()):
                    if "ExecutionTime" in line or "ClockTime" in line:
                        execution_time = line.strip()
                        break
            if execution_time != "N/A":
                break

    num_cores = "N/A"
    decomp_path = case_dir / "system" / "decomposeParDict"
    if decomp_path.exists():
        with open(decomp_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "numberOfSubdomains" in line:
                    num_cores = line.split()[1].rstrip(';')
                    break

    return num_cores, execution_time


def verify_results(case_dir: Path):
    """Gera o relatório final de pós-processamento da simulação."""
    print("\n" + "=" * 60)
    print(f"RELATÓRIO FINAL DE SIMULAÇÃO - CASO: {case_dir.name}")
    print("=" * 60)

    try:
        # Métricas de y+
        yplus_data = get_wall_yplus(case_dir)
        print("MÉTRICAS DE DISTÂNCIA DA PAREDE (y+)")
        print(f"Wall y+ (Mín / Máx / Média) : {yplus_data['min']:.2f} / {yplus_data['max']:.2f} / {yplus_data['avg']:.2f}")

        if yplus_data['avg'] > 0:
            if yplus_data['avg'] < 1.0:
                print("Status y+                   : Excelente para resolução da subcamada viscosa (y+ < 1)")
            elif 30.0 <= yplus_data['avg'] <= 300.0:
                print("Status y+                   : Adequado para funções de parede padrão (30 < y+ < 300)")
            else:
                print("Status y+                   : Na camada limite intermediária (1 < y+ < 30). Ajuste a malha.")
        else:
            print("Status y+                   : Não capturado (Verifique se a solução convergiu).")

        print("-" * 60)

        # Desempenho computacional
        num_cores, execution_time = get_performance_metrics(case_dir)
        n_cells = count_mesh_cells(case_dir)

        print("DESEMPENHO COMPUTACIONAL")
        print(f"Núcleos de Processamento     : {num_cores}")
        print(f"Tamanho Total da Malha       : {n_cells} células")
        print(f"Tempo de Execução           : {execution_time}")
        print("=" * 60 + "\n")

    except Exception as err:
        print(f"Erro no pós-processamento: {err}")


if __name__ == "__main__":
    cfg = SimulationConfig()
    args = parse_args()

    # Define o caso dinamicamente se passado via -case, senão usa template_case
    if args.case:
        case_dir = Path(args.case).resolve()
    else:
        case_dir = ROOT_DIR / "template_case"

    if args.pre:
        validate_mesh_pre_run(cfg, case_dir)
    else:
        verify_results(case_dir)