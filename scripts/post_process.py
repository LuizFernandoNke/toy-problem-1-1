import sys
import subprocess
import os
import re
import math
import numpy as np
import pandas as pd
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config.simulation_config import SimulationConfig

def compute_multiphase_theoretical_dp(cfg: SimulationConfig, L_sample: float) -> dict:
    """
    Calcula a perda de carga teórica total (atrito + hidrostática) para escoamento 
    bifásico turbulento/laminar utilizando a equação de Haaland / Hagen-Poiseuille.
    """
    # 1. Propriedades físicas dos fluidos (Água e Óleo)
    rho_w = getattr(cfg.water, 'rho', 999.1) if hasattr(cfg, 'water') else 999.1
    nu_w = getattr(cfg.water, 'nu', 1.0e-06) if hasattr(cfg, 'water') else 1.0e-06
    mu_w = rho_w * nu_w

    rho_o = getattr(cfg.oil, 'rho', 890.0) if hasattr(cfg, 'oil') else 890.0
    nu_o = getattr(cfg.oil, 'nu', 1.5e-05) if hasattr(cfg, 'oil') else 1.5e-05
    mu_o = rho_o * nu_o

    # 2. Parâmetros operacionais e geometria
    alpha_w = getattr(cfg, 'inlet_alpha_water', 0.5)
    alpha_o = 1.0 - alpha_w
    U_mean = getattr(cfg, 'velocity_inlet', getattr(cfg, 'inlet_velocity', 1.0))
    D = getattr(cfg, 'diameter', 0.05)
    roughness = getattr(cfg, 'roughness_height', 0.0)
    inclination_deg = getattr(cfg, 'inclination_deg', 0.0)

    # 3. Propriedades equivalentes da mistura
    rho_mix = alpha_w * rho_w + alpha_o * rho_o
    mu_mix = alpha_w * mu_w + alpha_o * mu_o
    nu_mix = mu_mix / rho_mix if rho_mix > 0 else nu_w

    # 4. Número de Reynolds da mistura
    Re_mix = (U_mean * D) / nu_mix if nu_mix > 0 else 2000.0

    # 5. Fator de atrito de Darcy (f_darcy)
    if Re_mix < 2300:
        f_darcy = 64.0 / Re_mix
        flow_regime = "Laminar (Hagen-Poiseuille)"
    else:
        rel_roughness = roughness / D
        term1 = (rel_roughness / 3.7) ** 1.11
        term2 = 6.9 / Re_mix
        inv_sqrt_f = -1.8 * math.log10(term1 + term2)
        f_darcy = 1.0 / (inv_sqrt_f ** 2)
        flow_regime = "Turbulent (Haaland)"

    # 6. Queda de pressão por atrito (Darcy-Weisbach)
    dp_friction_pa = f_darcy * (L_sample / D) * (0.5 * rho_mix * (U_mean ** 2))

    # 7. Componente hidrostática devido à inclinação
    g_acc = 9.81
    theta_rad = math.radians(inclination_deg)
    dp_hydrostatic_pa = rho_mix * g_acc * L_sample * math.sin(theta_rad)

    # 8. Queda de pressão teórica total
    dp_total_theory_pa = dp_friction_pa + dp_hydrostatic_pa

    return {
        "rho_mix": rho_mix,
        "nu_mix": nu_mix,
        "reynolds_mix": Re_mix,
        "f_darcy": f_darcy,
        "flow_regime": flow_regime,
        "dp_friction_pa": dp_friction_pa,
        "dp_hydrostatic_pa": dp_hydrostatic_pa,
        "dp_total_theory_pa": dp_total_theory_pa
    }

def run_sample_if_missing(case_dir: Path):
    """Executa o utilitário postProcess -func sampleDict caso a amostragem não exista."""
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
    """Executa o utilitário postProcess -func yPlus caso a amostragem de yPlus não exista."""
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
    Extrai a perda de carga por atrito (Delta P_rgh em Pa) e o comprimento 
    amostrado L_sample (m) a partir do arquivo center_line*.xy.
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

    # Coluna 0 = z (m), Coluna 1 = p_rgh (Pa)
    data = np.loadtxt(xy_files[0])
    
    z_coords = data[:, 0]
    p_rgh = data[:, 1]

    # Delta P por atrito = p_rgh(entrada) - p_rgh(saída)
    dp_friction_sim = float(p_rgh[0] - p_rgh[-1])
    L_sample_real = float(abs(z_coords[-1] - z_coords[0]))

    return dp_friction_sim, L_sample_real

def extract_yplus(case_dir: Path) -> dict:
    """Extrai yPlus min, max, avg e classifica o status da parede."""
    run_yplus_if_missing(case_dir)
    
    yplus_base = case_dir / "postProcessing" / "yPlus"
    default_res = {"min": 0.0, "max": 0.0, "avg": 0.0, "status": "N/A"}
    
    if not yplus_base.exists():
        return default_res

    yplus_files = list(yplus_base.glob("**/yPlus.dat"))
    if not yplus_files:
        return default_res

    latest_file = max(yplus_files, key=lambda p: float(p.parent.name))
    
    try:
        content = latest_file.read_text(encoding="utf-8", errors="ignore")
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
        
        if not lines:
            return default_res

        last_line = lines[-1].split()
        
        if len(last_line) >= 5:
            y_min, y_max, y_avg = float(last_line[2]), float(last_line[3]), float(last_line[4])
        elif len(last_line) >= 4:
            y_min, y_max, y_avg = float(last_line[1]), float(last_line[2]), float(last_line[3])
        else:
            return default_res

        # Classificação do status do y+
        if y_avg < 1.0:
            status = "Optimal (y+ < 1)"
        elif 30.0 <= y_avg <= 300.0:
            status = "Optimal wall functions (30 < y+ < 300)"
        else:
            status = "Buffer layer (1 < y+ < 30)"

        return {"min": y_min, "max": y_max, "avg": y_avg, "status": status}
    except Exception:
        return default_res

def extract_execution_time(case_dir: Path) -> float:
    """Extrai o tempo total de execução procurando nos logs do OpenFOAM."""
    potential_logs = list(case_dir.rglob("*log*")) + list(case_dir.rglob("*.out"))
    log_files = [f for f in potential_logs if f.is_file()]
    if not log_files:
        return 0.0

    log_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for log_file in log_files:
        try:
            content = log_file.read_text(encoding="utf-8", errors="ignore")
            for line in reversed(content.splitlines()):
                if "ExecutionTime =" in line:
                    parts = line.split("ExecutionTime =")
                    time_str = parts[1].split("s")[0].strip()
                    return float(time_str)
        except Exception:
            continue

    return 0.0

def get_mesh_cells(case_dir: Path) -> int:
    """Obtém o número de células da malha a partir do polyMesh."""
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
    return 0

def main():
    cfg = SimulationConfig()
    root_dir = Path(__file__).resolve().parent.parent
    runs_dir = root_dir / "runs"
    
    L_total = getattr(cfg, 'length', 2.0)
    L_sample_est = (0.90 - 0.50) * L_total
    num_cores = getattr(cfg, 'num_processors', 10)
    
    results = []
    
    for case_name in ["run_kEpsilon", "run_kOmegaSST"]:
        case_dir = runs_dir / case_name
        if not case_dir.exists():
            continue
            
        model_name = "kEpsilon" if "kEpsilon" in case_name else "kOmegaSST"
        
        # 1. Extrai perda de atrito simulada e comprimento amostrado real
        dp_friction_sim, L_sample_real = extract_delta_p_and_length(case_dir)
        if L_sample_real == 0.0:
            L_sample_real = L_sample_est

        # 2. Processa teoria multifásica completa (Haaland + Hidrostática)
        theory_data = compute_multiphase_theoretical_dp(cfg, L_sample_real)

        # 3. Pressão total simulada = Atrito (OpenFOAM) + Hidrostática
        dp_total_sim = dp_friction_sim + theory_data["dp_hydrostatic_pa"]

        # 4. Erro relativo percentual
        dp_theory = theory_data["dp_total_theory_pa"]
        err_rel = abs(dp_total_sim - dp_theory) / dp_theory * 100.0 if dp_theory > 0 else 0.0

        # 5. Métricas de malha, y+ e execução
        yplus = extract_yplus(case_dir)
        n_cells = get_mesh_cells(case_dir)
        exec_time = extract_execution_time(case_dir)
        
        results.append({
            "Model": model_name,
            "Case_Directory": case_name,
            "Re_Mix": round(theory_data["reynolds_mix"], 2),
            "Darcy_f": round(theory_data["f_darcy"], 5),
            "L_Sample_m": round(L_sample_real, 3),
            "Delta_P_Theory_Pa": round(dp_theory, 4),
            "Delta_P_Simulated_Pa": round(dp_total_sim, 4),
            "Error_Rel_Pct": round(err_rel, 2),
            "yPlus_Min": round(yplus["min"], 2),
            "yPlus_Max": round(yplus["max"], 2),
            "yPlus_Avg": round(yplus["avg"], 2),
            "yPlus_Status": yplus["status"],
            "Mesh_Cells": n_cells,
            "Cores": num_cores,
            "Execution_Time_s": round(exec_time, 2)
        })

    df = pd.DataFrame(results)
    csv_out = root_dir / "results.csv"
    df.to_csv(csv_out, index=False)
    
    print(f"Validação multifásica concluída. Resultados salvos em: {csv_out.resolve()}")

if __name__ == "__main__":
    main()