import os
import re
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def extract_yplus(case_dir):
    base_post = case_dir / "postProcessing" / "yPlus"
    if not base_post.exists():
        return "N/A", "N/A", "N/A"
    
    # Encontra todos os arquivos .dat dentro de yPlus recursivamente
    yfiles = sorted([f for f in base_post.rglob("*.dat") if f.is_file()])
    if not yfiles:
        return "N/A", "N/A", "N/A"
        
    # Pega o último arquivo gerado (tempo mais recente)
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
    base_post = case_dir / "postProcessing"
    if not base_post.exists():
        return 0.0
        
    # Encontra qualquer arquivo center_line recursivamente
    center_files = sorted([f for f in base_post.rglob("*center_line*") if f.is_file()])
    if center_files:
        try:
            df = pd.read_csv(center_files[-1], sep=r'\s+', comment='#', header=None, engine='python')
            if not df.empty and df.shape[1] >= 2:
                p_in = float(df.iloc[0, 1])
                p_out = float(df.iloc[-1, 1])
                return p_in - p_out
        except Exception:
            pass
    return 0.0

def main():
    cases = [
        ("kEpsilon", BASE_DIR / "runs" / "run_kEpsilon"),
        ("kOmegaSST", BASE_DIR / "runs" / "run_kOmegaSST")
    ]
    
    records = []
    for name, case_dir in cases:
        min_y, max_y, avg_y = extract_yplus(case_dir)
        exec_time = extract_execution_time(case_dir)
        delta_p = extract_delta_p(case_dir)
        
        records.append({
            'Model': name,
            'Case_Directory': case_dir.name,
            'Mesh_Cells': 40000,
            'Cores': 10,
            'yPlus_Min': min_y,
            'yPlus_Max': max_y,
            'yPlus_Avg': avg_y,
            'Delta_P_Pa': round(delta_p, 4),
            'Execution_Time': exec_time
        })
        
    df_metrics = pd.DataFrame(records)
    csv_path = BASE_DIR / "simulation_metrics.csv"
    df_metrics.to_csv(csv_path, index=False)
    print(f"[MÉTRICAS] Salvas com sucesso em: {csv_path}")

if __name__ == "__main__":
    main()