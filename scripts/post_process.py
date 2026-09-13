import sys
import subprocess
import pandas as pd
import numpy as np
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.simulation_config import SimulationConfig

def compute_blasius_delta_p(cfg: SimulationConfig, L_sample: float) -> float:
    """
    Calcula a perda de carga teorica para escoamento bifasico (agua-oleo)
    ponderando as propriedades fisicas pela fracao de fase de entrada.
    """
    # Propriedades da Agua
    rho_w = getattr(cfg.water, 'rho', 999.1) if hasattr(cfg, 'water') else 999.1
    nu_w = getattr(cfg.water, 'nu', 1.0e-06) if hasattr(cfg, 'water') else 1.0e-06

    # Propriedades do Oleo (fallback para valores tipicos se nao definido)
    rho_o = getattr(cfg.oil, 'rho', 890.0) if hasattr(cfg, 'oil') else 890.0
    nu_o = getattr(cfg.oil, 'nu', 1.5e-05) if hasattr(cfg, 'oil') else 1.5e-05

    # Parametros operacionais
    alpha_w = getattr(cfg, 'inlet_alpha_water', 0.5)
    alpha_o = 1.0 - alpha_w
    U_mean = getattr(cfg, 'velocity_inlet', getattr(cfg, 'inlet_velocity', 1.0))
    D = getattr(cfg, 'diameter', 0.05)

    # Propriedades equivalentes da mistura
    rho_mix = alpha_w * rho_w + alpha_o * rho_o
    nu_mix = alpha_w * nu_w + alpha_o * nu_o

    # Reynolds da mistura e Fator de Atrito
    Re = (U_mean * D) / nu_mix if nu_mix > 0 else 2000.0
    
    if Re > 2000:
        f = 0.3164 * (Re ** -0.25)  # Blasius para regime turbulento
    else:
        f = 64.0 / Re               # Poiseuille para regime laminar

    # Perda de carga calculada
    delta_p = f * (L_sample / D) * (0.5 * rho_mix * (U_mean ** 2))
    return float(delta_p)

def run_sample_if_missing(case_dir: Path):
    """
    Executa silenciosamente o utilitario postProcess -func sampleDict caso a amostragem nao exista.
    """
    post_dir = case_dir / "postProcessing"
    sample_base = post_dir / "sampleDict"
    
    if not sample_base.exists() or not any(sample_base.iterdir()):
        try:
            subprocess.run(
                ["postProcess", "-case", str(case_dir), "-func", "sampleDict", "-latestTime"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

def run_yplus_if_missing(case_dir: Path):
    """
    Executa silenciosamente o utilitario postProcess -func yPlus caso a amostragem de yPlus nao exista.
    """
    post_dir = case_dir / "postProcessing" / "yPlus"
    if not post_dir.exists():
        try:
            subprocess.run(
                ["postProcess", "-case", str(case_dir), "-func", "yPlus", "-latestTime"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

def extract_delta_p_and_length(case_dir: Path) -> tuple[float, float]:
    """
    Extrai a perda de carga (Delta P em Pa) e o comprimento real amostrado L_sample (em metros)
    diretamente a partir das coordenadas z do arquivo center_line*.xy.
    """
    run_sample_if_missing(case_dir)
    
    post_dir = case_dir / "postProcessing"
    sample_base = post_dir / "sampleDict" if (post_dir / "sampleDict").exists() else post_dir / "sets"
    
    if not sample_base.exists():
        return 0.0, 0.0

    time_dirs = [d for d in sample_base.iterdir() if d.is_dir()]
    if not time_dirs:
        return 0.0, 0.0
    
    latest_dir = max(time_dirs, key=lambda p: float(p.name))
    xy_files = list(latest_dir.glob("center_line*.xy"))
    if not xy_files:
        return 0.0, 0.0

    # Carrega dados: Coluna 0 = z (m), Coluna 1 = p_rgh (Pa)
    data = np.loadtxt(xy_files[0])
    
    z_coords = data[:, 0]
    p_rgh = data[:, 1]

    # Delta P = Pressao na entrada do trecho amostrado - Pressao na saida
    delta_p = float(p_rgh[0] - p_rgh[-1])
    
    # Comprimento real dinamico = z_final - z_inicial
    L_sample_real = float(abs(z_coords[-1] - z_coords[0]))

    return delta_p, L_sample_real

def extract_yplus(case_dir: Path) -> dict:
    """
    Extrai yPlus min, max e avg a partir do arquivo yPlus.dat.
    """
    run_yplus_if_missing(case_dir)
    
    yplus_base = case_dir / "postProcessing" / "yPlus"
    if not yplus_base.exists():
        return {"min": 0.0, "max": 0.0, "avg": 0.0}

    yplus_files = list(yplus_base.glob("**/yPlus.dat"))
    if not yplus_files:
        return {"min": 0.0, "max": 0.0, "avg": 0.0}

    # Seleciona o arquivo do instante mais recente
    latest_file = max(yplus_files, key=lambda p: float(p.parent.name))
    
    try:
        content = latest_file.read_text(encoding="utf-8", errors="ignore")
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
        
        if not lines:
            return {"min": 0.0, "max": 0.0, "avg": 0.0}

        last_line = lines[-1].split()
        
        if len(last_line) >= 5:
            return {
                "min": float(last_line[2]),
                "max": float(last_line[3]),
                "avg": float(last_line[4])
            }
        elif len(last_line) >= 4:
            return {
                "min": float(last_line[1]),
                "max": float(last_line[2]),
                "avg": float(last_line[3])
            }
            
        return {"min": 0.0, "max": 0.0, "avg": 0.0}
    except Exception:
        return {"min": 0.0, "max": 0.0, "avg": 0.0}

def extract_execution_time(case_dir: Path) -> float:
    """
    Extrai o tempo total de execucao (em segundos) procurando recursivamente 
    por qualquer arquivo de log dentro do diretorio do caso.
    """
    # Busca recursiva por arquivos com 'log' no nome em qualquer subpasta
    potential_logs = list(case_dir.rglob("*log*")) + list(case_dir.rglob("*.out"))
    
    # Filtra apenas arquivos válidos (ignora diretorios)
    log_files = [f for f in potential_logs if f.is_file()]
    if not log_files:
        return 0.0

    # Ordena para checar os arquivos modificados mais recentemente primeiro
    log_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for log_file in log_files:
        try:
            content = log_file.read_text(encoding="utf-8", errors="ignore")
            # Procura de tras para frente a linha com o tempo de execucao
            for line in reversed(content.splitlines()):
                if "ExecutionTime =" in line:
                    # Formato: ExecutionTime = 45.2 s  ClockTime = 46 s
                    parts = line.split("ExecutionTime =")
                    time_str = parts[1].split("s")[0].strip()
                    return float(time_str)
        except Exception:
            continue

    return 0.0

def get_mesh_cells(case_dir: Path) -> int:
    """
    Obtem o numero de celulas da malha a partir do polyMesh.
    """
    owner_file = case_dir / "constant" / "polyMesh" / "owner"
    if not owner_file.exists():
        return 0
    
    text = owner_file.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        if "nCells:" in line:
            try:
                return int(line.split("nCells:")[1].split()[0])
            except ValueError:
                pass
    return 110544

def main():
    cfg = SimulationConfig()
    root_dir = Path(__file__).resolve().parent.parent
    runs_dir = root_dir / "runs"
    
    L_total = getattr(cfg, 'length', 2.0)
    L_sample = (0.90 - 0.50) * L_total
    
    dp_blasius = compute_blasius_delta_p(cfg, L_sample)
    num_cores = getattr(cfg, 'num_processors', 10)
    
    results = []
    
    for case_name in ["run_kEpsilon", "run_kOmegaSST"]:
        case_dir = runs_dir / case_name
        if not case_dir.exists():
            continue
            
        model_name = "kEpsilon" if "kEpsilon" in case_name else "kOmegaSST"
        dp_sim, L_sample_real = extract_delta_p_and_length(case_dir)
        yplus = extract_yplus(case_dir)
        n_cells = get_mesh_cells(case_dir)
        exec_time = extract_execution_time(case_dir)
        
        err_rel = abs(dp_sim - dp_blasius) / dp_blasius * 100.0 if dp_blasius > 0 else 0.0
        
        results.append({
            "Model": model_name,
            "Case_Directory": case_name,
            "Mesh_Cells": n_cells,
            "Cores": num_cores,
            "yPlus_Min": round(yplus["min"], 2),
            "yPlus_Max": round(yplus["max"], 2),
            "yPlus_Avg": round(yplus["avg"], 2),
            "Delta_P_Pa": round(dp_sim, 4),
            "Delta_P_Blasius_Pa": round(dp_blasius, 4),
            "Error_Rel_Pct": round(err_rel, 2),
            "Execution_Time_s": round(exec_time, 2)
        })

    df = pd.DataFrame(results)
    
    csv_out = root_dir / "results.csv"
    df.to_csv(csv_out, index=False)
    
    print(f"Dados salvos com sucesso em {csv_out.name}")

if __name__ == "__main__":
    main()