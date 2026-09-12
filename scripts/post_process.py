import os
import sys
import subprocess
import re
import csv
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

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
    """Extrai a contagem total de células da malha via checkMesh."""
    current_env = os.environ.copy()
    cmd = f"{OF_ENV} checkMesh -case {case_dir} -time 0"
    res = subprocess.run(cmd, shell=True, executable="/bin/bash", capture_output=True, text=True, env=current_env)
    match = re.search(r"cells:\s*(\d+)", res.stdout)
    return int(match.group(1)) if match else 0


def read_dp_from_postprocessing_files(case_dir: Path) -> float:
    """Fallback: Lê os arquivos salvos em postProcessing/patchAverage caso o comando via CLI falhe."""
    post_dir = case_dir / "postProcessing"
    if not post_dir.exists():
        return 0.0

    def get_latest_value(patch_name: str) -> float:
        patch_dirs = list(post_dir.glob(f"*{patch_name}*")) + list(post_dir.glob(f"patchAverage*{patch_name}*"))
        for pdir in patch_dirs:
            time_dirs = [d for d in pdir.iterdir() if d.is_dir() and d.name.replace('.', '', 1).isdigit()]
            if time_dirs:
                latest = sorted(time_dirs, key=lambda x: float(x.name))[-1]
                for dat_file in latest.glob("*.dat"):
                    with open(dat_file, "r", encoding="utf-8", errors="ignore") as f:
                        lines = [line.strip() for line in f if not line.startswith("#") and line.strip()]
                        if lines:
                            last_line = lines[-1].split()
                            return float(last_line[-1])
        return 0.0

    p_in = get_latest_value("inlet")
    p_out = get_latest_value("outlet")
    return abs(p_in - p_out)


def extract_dp_and_yplus(case_dir: Path) -> tuple[float, float]:
    """Extrai o y+ médio e a diferença de pressão (Delta P) em paralelo usando mpirun -np 10."""
    current_env = os.environ.copy()

    # 1. Extrai o y+ médio no último tempo
    cmd_yplus = f"{OF_ENV} mpirun -np 10 interFoam -parallel -case {case_dir} -postProcess -func yPlus -latestTime"
    res_yplus = subprocess.run(cmd_yplus, shell=True, executable="/bin/bash", capture_output=True, text=True, env=current_env)
    
    matches_y = re.findall(r"average\s*=\s*([\d\.\-eE]+)", res_yplus.stdout)
    yplus_avg = float(matches_y[-1]) if matches_y else 0.0

    # 2. Extrai a pressão média no inlet e no outlet usando patchAverage
    cmd_pin = f"{OF_ENV} mpirun -np 10 postProcess -parallel -case {case_dir} -func 'patchAverage(name=inlet, field=p_rgh)' -latestTime"
    cmd_pout = f"{OF_ENV} mpirun -np 10 postProcess -parallel -case {case_dir} -func 'patchAverage(name=outlet, field=p_rgh)' -latestTime"

    res_pin = subprocess.run(cmd_pin, shell=True, executable="/bin/bash", capture_output=True, text=True, env=current_env)
    res_pout = subprocess.run(cmd_pout, shell=True, executable="/bin/bash", capture_output=True, text=True, env=current_env)

    p_in_match = re.findall(r"(?:average|areaAverage)\([^)]+\)\s*(?:of\s+\w+\s*)?=\s*([\d\.\-eE]+)", res_pin.stdout)
    p_out_match = re.findall(r"(?:average|areaAverage)\([^)]+\)\s*(?:of\s+\w+\s*)?=\s*([\d\.\-eE]+)", res_pout.stdout)

    if p_in_match and p_out_match:
        p_in = float(p_in_match[-1])
        p_out = float(p_out_match[-1])
        # Multiplica por 1000 (rho da água) para converter m²/s² -> Pa            
        rho = 1000.0  
        delta_p = abs(p_in - p_out) * rho
    else:
            delta_p = read_dp_from_postprocessing_files(case_dir) * 1000.0

    return delta_p, yplus_avg



def get_performance_metrics(case_dir: Path) -> tuple[str, str]:
    """Extrai o número de núcleos (processadores) e o tempo final de execução do log."""
    execution_time = "N/A"
    
    # Busca arquivos de log do interFoam na raiz do caso
    log_files = list(case_dir.glob("log.*")) + list(case_dir.glob("*.log"))
    for log_path in log_files:
        if log_path.is_file():
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in reversed(f.readlines()):
                    if "ExecutionTime" in line:
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
                    num_cores = line.split()[1].rstrip(';').strip()
                    break

    return num_cores, execution_time


def save_to_csv(row_data: dict):
    """Salva os dados no CSV sem duplicar modelos."""
    csv_file = ROOT_DIR / "simulation_metrics.csv"
    fieldnames = [
        "Model", "Case_Directory", "Mesh_Cells", "Cores", 
        "yPlus_Min", "yPlus_Max", "yPlus_Avg", "Delta_P_Pa", "Execution_Time"
    ]
    
    rows = {}
    if csv_file.exists():
        with open(csv_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if r.get("Model"):
                    rows[r["Model"]] = r

    rows[row_data["Model"]] = row_data

    with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows.values())

    print(f"[CSV] Métricas atualizadas em: {csv_file}\n")


def verify_results(case_dir: Path):
    """Executa a verificação e salva o relatório."""
    delta_p, yplus_avg = extract_dp_and_yplus(case_dir)
    num_cores, execution_time = get_performance_metrics(case_dir)
    n_cells = count_mesh_cells(case_dir)
    model_name = case_dir.name.replace("run_", "")

    print("\n" + "=" * 60)
    print(f"RELATÓRIO FINAL DE SIMULAÇÃO - CASO: {case_dir.name}")
    print("=" * 60)
    print(f"Wall y+ (Média)             : {yplus_avg:.2f}")
    print(f"Delta P (Entrada - Saída)    : {delta_p:.4f} Pa")
    print(f"Número de Processadores     : {num_cores}")
    print(f"Tamanho da Malha            : {n_cells} células")
    print(f"Tempo de Execução           : {execution_time}")
    print("=" * 60 + "\n")

    row_data = {
        "Model": model_name,
        "Case_Directory": case_dir.name,
        "Mesh_Cells": n_cells,
        "Cores": num_cores,
        "yPlus_Min": "N/A",
        "yPlus_Max": "N/A",
        "yPlus_Avg": f"{yplus_avg:.2f}",
        "Delta_P_Pa": f"{delta_p:.4f}",
        "Execution_Time": execution_time
    }

    save_to_csv(row_data)


if __name__ == "__main__":
    case_path = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT_DIR / "runs" / "run_kEpsilon"
    verify_results(case_path)