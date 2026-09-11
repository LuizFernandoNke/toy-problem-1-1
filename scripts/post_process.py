import os
import sys
import subprocess
import re
import math
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
    """
    Executa a validação da malha (número de células e estimativa de Re)
    ANTES de iniciar a simulação principal.
    """
    n_cells = count_mesh_cells(case_dir)
    print("\n" + "=" * 60)
    print("PRÉ-VALIDAÇÃO DA MALHA E PARÂMETROS DE ESCOAMENTO")
    print("=" * 60)
    print(f"Número Total de Células     : {n_cells}")
    print(f"Resolução da Malha (Nx,Ny,Nz): {cfg.nx} x {cfg.ny} x {cfg.nz}")
    
    # Estimativa de Reynolds para a água na entrada
    dh = cfg.diameter
    velocity = cfg.velocity_inlet
    rho_water = cfg.water.rho
    mu_water = cfg.water.rho * cfg.water.nu

    re_water = (rho_water * velocity * dh) / mu_water
    
    print(f"Diâmetro Hidráulico (Dh)    : {dh:.4f} m")
    print(f"Número de Reynolds (Água)   : {re_water:.2f}")
    if re_water > 4000:
        print("Regime de Escoamento       : Turbulento (Modelagem k-omega SST ativa)")
    elif re_water < 2300:
        print("Regime de Escoamento       : Laminar")
    else:
        print("Regime de Escoamento       : Transição")
    print("=" * 60 + "\n")


def run_openfoam_postprocess(case_dir: Path):
    """Reconstrói o último tempo e calcula o yPlus com tratamento de erros visível."""
    current_env = os.environ.copy()
    
    # 1. Reconstruir o último passo de tempo
    cmd_reconstruct = f"{OF_ENV} reconstructPar -case {case_dir} -latestTime"
    rec_res = subprocess.run(
        cmd_reconstruct, shell=True, executable="/bin/bash", 
        capture_output=True, text=True, env=current_env
    )
    
    if rec_res.returncode != 0:
        print(f"[AVISO] Falha no reconstructPar: {rec_res.stderr.strip()}")

    # 2. Executa o pós-processamento do yPlus
    cmd_yplus = f"{OF_ENV} interFoam -case {case_dir} -postProcess -func yPlus -latestTime"
    result = subprocess.run(
        cmd_yplus, shell=True, executable="/bin/bash", 
        capture_output=True, text=True, env=current_env
    )
    
    if result.returncode != 0:
        print(f"[AVISO] interFoam -postProcess falhou: {result.stderr.strip()}")
        # Fallback para o utilitário genérico postProcess
        cmd_yplus_alt = f"{OF_ENV} postProcess -case {case_dir} -func yPlus -latestTime"
        subprocess.run(cmd_yplus_alt, shell=True, executable="/bin/bash", capture_output=True, env=current_env)


def get_wall_yplus(case_dir: Path) -> dict:
    """Executa a reconstrução e captura os dados de y+ direto do terminal do interFoam."""
    current_env = os.environ.copy()
    
    # 1. Reconstruir o último tempo
    subprocess.run(
        f"{OF_ENV} reconstructPar -case {case_dir} -latestTime",
        shell=True, executable="/bin/bash", capture_output=True, env=current_env
    )

    # 2. Executa o pós-processamento do yPlus e captura a saída textual
    cmd_yplus = f"{OF_ENV} interFoam -case {case_dir} -postProcess -func yPlus -latestTime"
    res = subprocess.run(
        cmd_yplus, shell=True, executable="/bin/bash", capture_output=True, text=True, env=current_env
    )
    
    # Busca a linha do log impressa na saída padrão (stdout)
    output = res.stdout
    match = re.search(r"patch\s+\w+\s+y\+\s*:\s*min\s*=\s*([\d\.]+),\s*max\s*=\s*([\d\.]+),\s*average\s*=\s*([\d\.]+)", output)
    if match:
        return {
            "min": float(match.group(1)),
            "max": float(match.group(2)),
            "avg": float(match.group(3))
        }

    # Fallback: Tenta buscar nos arquivos .dat se existirem
    post_dir = case_dir / "postProcess"
    if post_dir.exists():
        for dat_file in post_dir.rglob("*.dat"):
            with open(dat_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "walls" in line or "wall" in line:
                        parts = line.split()
                        try:
                            return {"min": float(parts[1]), "max": float(parts[2]), "avg": float(parts[3])}
                        except (IndexError, ValueError):
                            continue

    return {"min": 0.0, "max": 0.0, "avg": 0.0}


def get_performance_metrics(case_dir: Path):
    """Extrai contagem de núcleos e tempo de execução do log interFoam."""
    log_path = case_dir / "interFoam.log"
    execution_time = "N/A"
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            for line in reversed(f.readlines()):
                if "ExecutionTime" in line or "ClockTime" in line:
                    execution_time = line.strip()
                    break

    num_cores = "N/A"
    decomp_path = case_dir / "system" / "decomposeParDict"
    if decomp_path.exists():
        with open(decomp_path, "r", encoding="utf-8") as f:
            for line in f:
                if "numberOfSubdomains" in line:
                    num_cores = line.split()[1].rstrip(';')
                    break

    return num_cores, execution_time


def verify_results():
    """Gera o relatório final de pós-processamento da simulação."""
    cfg = SimulationConfig()
    case_dir = Path(__file__).resolve().parent.parent / "template_case"

    print("\n" + "=" * 60)
    print("RELATÓRIO FINAL DE SIMULAÇÃO E DESEMPENHO (interFoam)")
    print("=" * 60)

    try:
        # Métricas de y+
        yplus_data = get_wall_yplus(case_dir)
        print("MÉTRICAS DE DISTÂNCIA DA PAREDE (y+)")
        print(f"Wall y+ (Mín / Máx / Média) : {yplus_data['min']:.2f} / {yplus_data['max']:.2f} / {yplus_data['avg']:.2f}")

        if yplus_data['avg'] < 1.0:
            print("Status y+                   : Excelente para resolução da subcamada viscosa (y+ < 1)")
        elif 30.0 <= yplus_data['avg'] <= 300.0:
            print("Status y+                   : Adequado para funções de parede padrão (30 < y+ < 300)")
        else:
            print("Status y+                   : Na camada limite intermediária (1 < y+ < 30). Ajuste a malha.")

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
    case_dir = Path(__file__).resolve().parent.parent / "template_case"
    
    # Se chamado com argumento "pre", valida a malha antes do solver
    if len(sys.argv) > 1 and sys.argv[1] == "--pre":
        validate_mesh_pre_run(cfg, case_dir)
    else:
        verify_results()