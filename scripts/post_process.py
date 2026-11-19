import sys
import subprocess
import os
import math
import shutil
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

# Adiciona o diretório raiz ao path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config.simulation_config import SimulationConfig

# ==============================================================================
# CONFIGURAÇÕES GERAIS DE AMOSTRAGEM E AMBIENTE OPENFOAM
# ==============================================================================
SAMPLING_START_PCT = 55.0  # Início da região desenvolvida (% do comprimento L)
SAMPLING_END_PCT = 85.0    # Fim da região de medição (% do comprimento L)
TIME_AVG_STEPS = 15        # Quantidade de últimos passos salvos para a média temporal
OPENFOAM_BASHRC = "/usr/lib/openfoam/openfoam2606/etc/bashrc"

# ==============================================================================
# BLOCO 1: DADOS EXPERIMENTAIS DA PLANILHA (MUKHERJEE & BRILL, 1979 - ID 26894)
# ==============================================================================
A_pipe = math.pi * (0.0381 ** 2) / 4.0
Q_G_in_situ = 3.483864 * A_pipe   # Vazão in-situ real (0.0039719 m³/s)
Q_L_in_situ = 0.039624 * A_pipe   # Vazão in-situ real (0.00004517 m³/s)

EXPERIMENTAL_DATA = {
    "GLDataID": 26894,
    "Authors": "MukherjeeHor (1979)",
    "PipeDia_m": 0.0381,
    "PipeIncli_deg": 0.0,
    "SystPressure_Pa": 210980.88,
    "GasVolFlowrate_m3s": Q_G_in_situ,
    "GasDensity_kgm3": 2.376139379,
    "GasViscosity_Pas": 9.99623e-06,
    "LiqVolFlowrate_m3s": Q_L_in_situ,
    "LiqDensity_kgm3": 801.7835916,
    "LiqViscosity_Pas": 0.001359885,
    "PressureDrop_Exp_Pa_m": 14.83317691,  # Gradiente de pressão medido (Pa/m)
    "LiqHoldUp_Exp": 0.08,                 # Holdup de óleo medido (-)
    "GasHoldUp_Exp": 0.92,                 # Fração de vazio medida (-)
    "Phi2_Exp": 9.906224053                # Multiplicador bifásico experimental
}


# ==============================================================================
# BLOCO 2: MODELO ANALÍTICO DE LOCKHART-MARTINELLI / CHISHOLM (1967)
# ==============================================================================
class ModeloFasesSeparadasChisholm:
    """Calcula gradiente de pressão (Pa/m), multiplicadores e holdup sem precisar inserir phi^2 manualmente."""

    def __init__(self, Q_L, Q_G, D, theta_deg, rho_L, rho_G, mu_L, mu_G, p_Pa=101325.0, g=9.81):
        self.Q_L = Q_L
        self.Q_G = Q_G
        self.D = D
        self.theta_rad = math.radians(theta_deg)
        self.rho_L = rho_L
        self.rho_G = rho_G
        self.mu_L = mu_L
        self.mu_G = mu_G
        self.p_Pa = p_Pa
        self.g = g

        # Área e velocidades superficiais
        self.A = math.pi * (D**2) / 4.0
        self.j_L = self.Q_L / self.A
        self.j_G = self.Q_G / self.A
        self.j = self.j_L + self.j_G

        # Reynolds superficiais das fases
        self.Re_L = (self.rho_L * self.j_L * self.D) / self.mu_L
        self.Re_G = (self.rho_G * self.j_G * self.D) / self.mu_G

        # Fatores de atrito de Fanning monofásicos
        self.f_FL = 16.0 / self.Re_L if self.Re_L < 1000 else 0.079 * (self.Re_L**-0.25)
        self.f_FG = 16.0 / self.Re_G if self.Re_G < 1000 else 0.079 * (self.Re_G**-0.25)

        # Gradientes de pressão por fricção monofásicos (Pa/m)
        self.dp_dz_FL = (2.0 / self.D) * self.f_FL * self.rho_L * (self.j_L**2)
        self.dp_dz_FG = (2.0 / self.D) * self.f_FG * self.rho_G * (self.j_G**2)

        # Parâmetro de Lockhart-Martinelli (X)
        self.X2 = self.dp_dz_FL / self.dp_dz_FG if self.dp_dz_FG > 0 else 1e-6
        self.X = math.sqrt(self.X2)

        # Coeficiente C de Chisholm baseado no regime de cada fase
        is_liq_turb = self.Re_L >= 1000
        is_gas_turb = self.Re_G >= 1000

        if is_liq_turb and is_gas_turb:
            self.C = 20  # Turbulento - Turbulento
        elif not is_liq_turb and is_gas_turb:
            self.C = 12  # Líquido Laminar - Gás Turbulento
        elif is_liq_turb and not is_gas_turb:
            self.C = 10  # Líquido Turbulento - Gás Laminar
        else:
            self.C = 5   # Laminar - Laminar

        # Multiplicadores bifásicos calculados automaticamente
        self.phi_G2 = 1.0 + self.C * self.X + self.X2
        self.phi_L2 = 1.0 + (self.C / self.X) + (1.0 / self.X2)

        # Gradiente por fricção bifásico (Pa/m)
        self.dp_dz_fric = self.phi_G2 * self.dp_dz_FG

        # Fração de vazio (alpha_G) e Holdup de líquido in-situ (y_L)
        self.alpha_G = (1.0 + self.X**0.8) ** -0.378
        self.y_L = 1.0 - self.alpha_G

        # Massa específica in-situ e gradiente gravitacional (Pa/m)
        self.rho_TP = self.rho_L * self.y_L + self.rho_G * self.alpha_G
        self.dp_dz_grav = self.rho_TP * self.g * math.sin(self.theta_rad)

        # Gradiente total incompressível (compatível com interFoam)
        self.dp_dz_total_incomp = self.dp_dz_fric + self.dp_dz_grav


# ==============================================================================
# BLOCO 3: EXTRAÇÃO DO GRADIENTE E HOLDUP NO OPENFOAM (MÉDIA TEMPORAL)
# ==============================================================================
def run_foam_cmd(case_dir: Path, foam_cmd: str, num_cores: int = 10) -> subprocess.CompletedProcess:
    """Executa comandos do OpenFOAM carregando o bashrc e detectando pastas processor*."""
    has_processors = any(case_dir.glob("processor*"))
    exec_cmd = f"mpirun -np {num_cores} {foam_cmd} -parallel" if has_processors else foam_cmd
    full_cmd = f"source {OPENFOAM_BASHRC} && {exec_cmd}"

    return subprocess.run(
        full_cmd,
        shell=True,
        executable="/bin/bash",
        capture_output=True,
        text=True,
        env=os.environ.copy()
    )


def create_plane_dict(case_dir: Path, dict_name: str, z_target: float, field_name: str) -> Path:
    """Cria dicionário surfaceFieldValue para média na área (areaAverage) no plano z."""
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    dict_path = system_dir / dict_name

    content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2606                                 |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/

type            surfaceFieldValue;
libs            ("fieldFunctionObjects");
writeControl    writeTime;
writeFields     false;
log             true;
operation       areaAverage;
fields          ({field_name});
regionType      sampledSurface;
name            {dict_name};
sampledSurfaceDict
{{
    type            plane;
    planeType       pointAndNormal;
    pointAndNormalDict
    {{
        point   (0 0 {z_target:.6f});
        normal  (0 0 1);
    }}
}}
"""
    dict_path.write_text(content, encoding="utf-8")
    return dict_path


def read_surface_time_average(case_dir: Path, dict_name: str, last_n_steps: int = TIME_AVG_STEPS) -> tuple[float, float, int]:
    """
    Lê a série temporal gerada em postProcessing/<dict_name>, filtra apenas a janela
    estacionária (últimos N passos) e retorna (média, desvio_padrão, n_amostras).
    """
    post_dir = case_dir / "postProcessing" / dict_name
    if not post_dir.exists():
        return None, 0.0, 0

    time_map = {}
    for dat_file in post_dir.glob("**/*.dat"):
        try:
            for line in dat_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    t_val = float(parts[0])
                    val = float(parts[-1])
                    if t_val > 0.0 and math.isfinite(val):
                        time_map[round(t_val, 6)] = val
        except Exception:
            continue

    if not time_map:
        return None, 0.0, 0

    # Ordena estritamente pelo tempo real (t_val)
    sorted_times = sorted(time_map.keys())
    selected_times = sorted_times[-last_n_steps:]
    window_values = np.array([time_map[t] for t in selected_times], dtype=float)

    print(f"    [DEBUG {dict_name}] t=[{selected_times[0]}s .. {selected_times[-1]}s] | último={window_values[-1]:.4f} | média={np.mean(window_values):.4f}")
    # Filtra spikes numéricos não-físicos de p_rgh (mantém apenas valores coerentes)
    if "plane_p" in dict_name:
        clean_values = window_values[(window_values > -500.0) & (window_values < 2000.0)]
        if len(clean_values) > 0:
            window_values = clean_values

    return float(np.median(window_values)), float(np.std(window_values)), len(window_values)


def extract_cfd_gradient_and_holdup(case_dir: Path, z_start: float, z_end: float, num_cores: int) -> dict:
    """
    Amostra p_rgh e alpha.oil em TODOS os tempos salvos nos planos z_start e z_end,
    calcula a média temporal dos últimos passos e retorna o gradiente médio (Pa/m).
    """
    sample_tasks = [
        ("plane_p_start", z_start, "p_rgh"),
        ("plane_p_end", z_end, "p_rgh"),
        ("plane_alpha_start", z_start, "alpha.oil"),
        ("plane_alpha_end", z_end, "alpha.oil"),
    ]
    avg_values = {}
    samples_used = 0

    for dict_name, z_pos, field_name in sample_tasks:
        old_post = case_dir / "postProcessing" / dict_name
        if old_post.exists():
            shutil.rmtree(old_post, ignore_errors=True)

        create_plane_dict(case_dir, dict_name, z_pos, field_name)
        res = run_foam_cmd(case_dir, f"postProcess -case {case_dir} -func {dict_name}", num_cores)

        mean_val, std_val, n_used = read_surface_time_average(case_dir, dict_name, TIME_AVG_STEPS)
        if mean_val is None:
            raise RuntimeError(
                f"Falha ao ler série temporal de '{field_name}' em z={z_pos:.3f}m ({case_dir.name}). "
                f"Stderr: {res.stderr.strip()}"
            )
        avg_values[dict_name] = mean_val
        samples_used = n_used
        print(f"  -> {dict_name} (z={z_pos:.2f}m): média={mean_val:.4f} ± {std_val:.4f} (últimos {n_used} tempos)")

    L_sample = abs(z_end - z_start)
    dp_pa = avg_values["plane_p_start"] - avg_values["plane_p_end"]
    grad_p_pa_m = dp_pa / L_sample if L_sample > 0 else 0.0
    holdup_avg = 0.5 * (avg_values["plane_alpha_start"] + avg_values["plane_alpha_end"])

    return {
        "L_sample_m": L_sample,
        "p_rgh_start_Pa": avg_values["plane_p_start"],
        "p_rgh_end_Pa": avg_values["plane_p_end"],
        "dp_friction_Pa": dp_pa,
        "grad_p_CFD_Pa_m": grad_p_pa_m,
        "holdup_start": avg_values["plane_alpha_start"],
        "holdup_end": avg_values["plane_alpha_end"],
        "holdup_CFD_avg": holdup_avg,
        "time_samples_used": samples_used
    }


# ==============================================================================
# MÉTRICAS AUXILIARES (y+, MALHA E TEMPO DE EXECUÇÃO)
# ==============================================================================
def extract_yplus(case_dir: Path, num_cores: int) -> dict:
    yplus_base = case_dir / "postProcessing" / "yPlus"
    default_res = {"min": 0.0, "max": 0.0, "avg": 0.0, "status": "N/A"}

    if not yplus_base.exists():
        run_foam_cmd(case_dir, f"postProcess -case {case_dir} -func yPlus -latestTime", num_cores)

    if not yplus_base.exists():
        return default_res

    yplus_files = list(yplus_base.glob("**/yPlus.dat"))
    if not yplus_files:
        return default_res

    latest_file = max(yplus_files, key=lambda p: float(p.parent.name))
    try:
        lines = [
            l.strip() for l in latest_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            if l.strip() and not l.startswith("#")
        ]
        if not lines:
            return default_res

        last_line = lines[-1].split()
        if len(last_line) >= 5:
            y_min, y_max, y_avg = float(last_line[2]), float(last_line[3]), float(last_line[4])
        elif len(last_line) >= 4:
            y_min, y_max, y_avg = float(last_line[1]), float(last_line[2]), float(last_line[3])
        else:
            return default_res

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
    potential_logs = list(case_dir.rglob("*log*")) + list(case_dir.rglob("*.out"))
    log_files = sorted([f for f in potential_logs if f.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)

    for log_file in log_files:
        try:
            for line in reversed(log_file.read_text(encoding="utf-8", errors="ignore").splitlines()):
                if "ExecutionTime =" in line:
                    return float(line.split("ExecutionTime =")[1].split("s")[0].strip())
        except Exception:
            continue
    return 0.0


def get_mesh_cells(case_dir: Path) -> int:
    owner_file = case_dir / "constant" / "polyMesh" / "owner"
    if not owner_file.exists():
        return 0
    for line in owner_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "nCells:" in line:
            try:
                return int(line.split("nCells:")[1].split()[0])
            except ValueError:
                pass
    return 0


# ==============================================================================
# ROTINA PRINCIPAL DE VALIDAÇÃO
# ==============================================================================
def main():
    cfg = SimulationConfig()
    root_dir = Path(__file__).resolve().parent.parent
    runs_dir = root_dir / "runs"

    L_total = getattr(cfg, 'length', 2.0)
    z_start = L_total * (SAMPLING_START_PCT / 100.0)
    z_end = L_total * (SAMPLING_END_PCT / 100.0)
    num_cores = getattr(cfg, 'num_processors', 10)

    exp = EXPERIMENTAL_DATA
    lm = ModeloFasesSeparadasChisholm(
        Q_L=exp["LiqVolFlowrate_m3s"],
        Q_G=exp["GasVolFlowrate_m3s"],
        D=exp["PipeDia_m"],
        theta_deg=getattr(cfg, 'inclination_deg', exp["PipeIncli_deg"]),
        rho_L=exp["LiqDensity_kgm3"],
        rho_G=exp["GasDensity_kgm3"],
        mu_L=exp["LiqViscosity_Pas"],
        mu_G=exp["GasViscosity_Pas"],
        p_Pa=exp["SystPressure_Pa"]
    )

    dp_dz_exp = exp["PressureDrop_Exp_Pa_m"]
    holdup_exp = exp["LiqHoldUp_Exp"]

    results = []

    for case_name in ["run_kEpsilon", "run_kOmegaSST"]:
        case_dir = runs_dir / case_name
        if not case_dir.exists():
            continue

        model_name = "kEpsilon" if "kEpsilon" in case_name else "kOmegaSST"
        print(f"\nProcessando série temporal de {model_name}...")

        try:
            cfd = extract_cfd_gradient_and_holdup(case_dir, z_start, z_end, num_cores)
        except Exception as err:
            print(f"[ERRO] Falha no pós-processamento de {model_name}: {err}")
            continue

        dp_dz_cfd_total = cfd["grad_p_CFD_Pa_m"] + lm.dp_dz_grav

        err_vs_exp_pct = abs(dp_dz_cfd_total - dp_dz_exp) / dp_dz_exp * 100.0
        err_vs_lm_pct = abs(dp_dz_cfd_total - lm.dp_dz_total_incomp) / lm.dp_dz_total_incomp * 100.0
        err_holdup_exp_pct = abs(cfd["holdup_CFD_avg"] - holdup_exp) / holdup_exp * 100.0

        yplus = extract_yplus(case_dir, num_cores)
        n_cells = get_mesh_cells(case_dir)
        exec_time = extract_execution_time(case_dir)

        results.append({
            "Model": model_name,
            "z_Start_m": round(z_start, 3),
            "z_End_m": round(z_end, 3),
            "L_Sample_m": round(cfd["L_sample_m"], 3),
            "Time_Samples_Used": cfd["time_samples_used"],

            # --- Gradiente de Pressão (Pa/m) ---
            "Grad_P_Exp_Pa_m": round(dp_dz_exp, 4),
            "Grad_P_Martinelli_Pa_m": round(lm.dp_dz_total_incomp, 4),
            "Grad_P_CFD_Pa_m": round(dp_dz_cfd_total, 4),
            "Error_CFD_vs_Exp_Pct": round(err_vs_exp_pct, 2),
            "Error_CFD_vs_LM_Pct": round(err_vs_lm_pct, 2),

            # --- Holdup de Óleo (-) e Parâmetros Martinelli ---
            "Holdup_Exp": round(holdup_exp, 4),
            "Holdup_Martinelli": round(lm.y_L, 4),
            "Holdup_CFD": round(cfd["holdup_CFD_avg"], 4),
            "Error_Holdup_vs_Exp_Pct": round(err_holdup_exp_pct, 2),
            "LM_Parameter_X": round(lm.X, 4),
            "LM_Chisholm_C": lm.C,
            "LM_PhiG2": round(lm.phi_G2, 4),

            # --- Qualidade da Malha e Performance ---
            "yPlus_Min": round(yplus["min"], 2),
            "yPlus_Max": round(yplus["max"], 2),
            "yPlus_Avg": round(yplus["avg"], 2),
            "yPlus_Status": yplus["status"],
            "Mesh_Cells": n_cells,
            "Cores": num_cores,
            "Execution_Time_s": round(exec_time, 2)
        })

    df_new = pd.DataFrame(results)
    csv_out = root_dir / "results.csv"

    if not df_new.empty:
        # Adiciona carimbo de data/hora para diferenciar cada rodada no histórico
        df_new.insert(0, "Timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        if csv_out.exists() and csv_out.stat().st_size > 0:
            df_old = pd.read_csv(csv_out)
            df_final = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_final = df_new

        df_final.to_csv(csv_out, index=False)
        print(f"\nValidação concluída! Resultados acumulados em: {csv_out.resolve()} (Total de registros: {len(df_final)})")
        print(df_new[["Timestamp", "Model", "Mesh_Cells", "Grad_P_Exp_Pa_m", "Grad_P_Martinelli_Pa_m", "Grad_P_CFD_Pa_m", "Error_CFD_vs_Exp_Pct", "Holdup_CFD"]].to_string(index=False))
    else:
        print("\nNenhum resultado novo foi gerado para adicionar ao CSV.")

if __name__ == "__main__":
    main()