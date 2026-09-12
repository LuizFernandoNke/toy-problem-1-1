import os
import re
import pandas as pd
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from config.simulation_config import SimulationConfig

def extract_yplus(case_dir):
    base_post = case_dir / "postProcessing" / "yPlus"
    if not base_post.exists():
        return "N/A", "N/A", "N/A"
    
    yfiles = sorted([f for f in base_post.rglob("*.dat") if f.is_file()])
    if not yfiles:
        return "N/A", "N/A", "N/A"
        
    latest_yfile = yfiles[-1]
    
    try:
        with open(latest_yfile, 'r') as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]
            if lines:
                parts = lines[-1].split()
                if len(parts) >= 5:
                    return f"{float(parts[2]):.2f}", f"{float(parts[3]):.2f}", f"{float(parts[4]):.2f}"
    except Exception:
        pass
        
    return "N/A", "N/A", "N/A"

def extract_execution_time(case_dir):
    possible_logs = [
        case_dir / "log.interFoam",
        *list(case_dir.glob("interFoam*.log")),
        *list(case_dir.glob("*.log"))
    ]
    
    for log_file in possible_logs:
        if log_file.exists() and log_file.is_file():
            try:
                with open(log_file, 'r', errors='ignore') as f:
                    content = f.read()
                    matches = re.findall(r'ExecutionTime\s*=\s*([\d\.]+)\s*s', content)
                    if matches:
                        return f"{float(matches[-1]):.2f}"
            except Exception:
                pass
    return "N/A"

def extract_delta_p(case_dir):
    base_post = case_dir / "postProcessing" / "sampleDict"
    if not base_post.exists():
        return 0.0
        
    time_dirs = []
    for d in base_post.iterdir():
        if d.is_dir():
            try:
                t_val = float(d.name)
                if t_val > 0:
                    time_dirs.append((t_val, d))
            except ValueError:
                pass

    if not time_dirs:
        return 0.0

    latest_dir = sorted(time_dirs, key=lambda x: x[0])[-1][1]
    
    xy_files = list(latest_dir.glob("*center_line*.xy"))
    if not xy_files:
        xy_files = list(latest_dir.glob("*.xy"))
    if not xy_files:
        return 0.0
        
    target_file = xy_files[0]

    try:
        # Coluna 0: Z (m), Coluna 1: Pressure (Pa) no interFoam
        df = pd.read_csv(target_file, sep=r'\s+', comment='#', header=None, engine='python')
        if df.empty or df.shape[1] < 2:
            return 0.0

        # Garantir ordenação do início ao fim da amostragem (0.50L -> 0.90L)
        df_sorted = df.sort_values(by=0).reset_index(drop=True)

        p_in = float(df_sorted.iloc[0, 1])   # Pressão na entrada do sample (z = 0.50L)
        p_out = float(df_sorted.iloc[-1, 1]) # Pressão na saída do sample (z = 0.90L)
        
        # Delta P direto da amostragem em Pa
        delta_p_sample = abs(p_in - p_out)
        return delta_p_sample

    except Exception as e:
        print(f"[Aviso] Erro ao extrair Delta P de {target_file}: {e}")

    return 0.0

def main():
    cfg = SimulationConfig()
    
    # --- Comprimento real do trecho de amostragem no sampleDict ---
    # z_start = 0.50 * L, z_end = 0.90 * L  =>  Delta z = 0.40 * L
    L_sample = cfg.length * (0.90 - 0.50)  # 0.80 m para L = 2.0 m
    
    # --- Cálculo Analítico (Blasius + Darcy-Weisbach para o trecho amostrado) ---
    Re = cfg.reynolds_water
    f_blasius = 0.3164 * (Re ** -0.25)
    
    # Usa L_sample em vez de cfg.length
    dp_blasius = f_blasius * (L_sample / cfg.diameter) * (cfg.water_density * (cfg.velocity_inlet ** 2) / 2.0)

    cases = [
        ("kEpsilon", BASE_DIR / "runs" / "run_kEpsilon"),
        ("kOmegaSST", BASE_DIR / "runs" / "run_kOmegaSST")
    ]
    
    records = []
    mesh_cells_total = cfg.nx * cfg.ny * cfg.nz

    for name, case_dir in cases:
        min_y, max_y, avg_y = extract_yplus(case_dir)
        exec_time = extract_execution_time(case_dir)
        delta_p_pa = extract_delta_p(case_dir)  # Retorna abs(p_in - p_out) direto do sampleDict
        
        # Erro relativo % em relação a Blasius no trecho amostrado
        err_rel = (abs(delta_p_pa - dp_blasius) / dp_blasius * 100) if dp_blasius > 0 else 0.0

        records.append({
            'Model': name,
            'Case_Directory': case_dir.name,
            'Mesh_Cells': mesh_cells_total,
            'Cores': cfg.num_processors,
            'yPlus_Min': min_y,
            'yPlus_Max': max_y,
            'yPlus_Avg': avg_y,
            'Delta_P_Pa': round(delta_p_pa, 4),
            'Delta_P_Blasius_Pa': round(dp_blasius, 4),
            'Error_Rel_Pct': round(err_rel, 2),
            'Execution_Time_s': exec_time
        })
        
    df_metrics = pd.DataFrame(records)
    csv_path = BASE_DIR / "simulation_metrics.csv"
    df_metrics.to_csv(csv_path, index=False)
    print(f"[MÉTRICAS] Salvas com sucesso em: {csv_path}")

if __name__ == "__main__":
    main()