import os
import sys
import re
import subprocess
import json
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

import scripts.generate_mesh as gm
from config.simulation_config import SimulationConfig

# Detecta ambiente OpenFOAM
def get_of_env() -> str:
    possible_paths = [
        "/usr/lib/openfoam/openfoam2606/etc/bashrc",
        "/opt/openfoam2606/etc/bashrc",
        os.path.expanduser("~/OpenFOAM/openfoam2606/etc/bashrc"),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return f"source {path} && "
    return "source /usr/lib/openfoam/openfoam2606/etc/bashrc && "

OF_ENV = get_of_env()

def run_cmd(cmd: str, cwd: Path):
    """Executa comandos bash no ambiente do OpenFOAM."""
    env = os.environ.copy()
    subprocess.run(f"{OF_ENV} {cmd}", shell=True, executable="/bin/bash", cwd=cwd, check=True, env=env)

def extract_dp_and_yplus(case_dir: Path) -> tuple[float, float]:
    current_env = os.environ.copy()

    # 1. Extrai o y+ médio (lê a última ocorrência no log do OpenFOAM)
    cmd_yplus = f"{OF_ENV} mpirun -np 10 interFoam -parallel -case {case_dir} -postProcess -func yPlus -latestTime"
    res_yplus = subprocess.run(cmd_yplus, shell=True, executable="/bin/bash", capture_output=True, text=True, env=current_env)
    
    matches_y = re.findall(r"average\s*=\s*([\d\.\-eE]+)", res_yplus.stdout)
    yplus_avg = float(matches_y[-1]) if matches_y else 0.0

    # 2. Extrai a pressão no inlet e no outlet
    cmd_pin = f"{OF_ENV} mpirun -np 10 postProcess -parallel -case {case_dir} -func 'patchAverage(name=inlet, field=p_rgh)' -latestTime"
    cmd_pout = f"{OF_ENV} mpirun -np 10 postProcess -parallel -case {case_dir} -func 'patchAverage(name=outlet, field=p_rgh)' -latestTime"

    res_pin = subprocess.run(cmd_pin, shell=True, executable="/bin/bash", capture_output=True, text=True, env=current_env)
    res_pout = subprocess.run(cmd_pout, shell=True, executable="/bin/bash", capture_output=True, text=True, env=current_env)

    # O OpenFOAM imprime a média no terminal com este padrão exato:
    # "areaAverage(inlet) of p_rgh = 12.345" ou "average(inlet) = 12.345"
    p_in_match = re.findall(r"(?:average|areaAverage)\([^)]+\)\s*(?:of\s+\w+\s*)?=\s*([\d\.\-eE]+)", res_pin.stdout)
    p_out_match = re.findall(r"(?:average|areaAverage)\([^)]+\)\s*(?:of\s+\w+\s*)?=\s*([\d\.\-eE]+)", res_pout.stdout)

    if p_in_match and p_out_match:
        p_in = float(p_in_match[-1])
        p_out = float(p_out_match[-1])
        delta_p = abs(p_in - p_out)
    else:
        # Se falhar via CLI paralelo, tenta ler a pasta postProcessing como fallback
        delta_p = read_dp_from_postprocessing_files(case_dir)

    return delta_p, yplus_avg


def read_dp_from_postprocessing_files(case_dir: Path) -> float:
    """Procura recursivamente por qualquer arquivo .dat gerado pelo patchAverage"""
    post_dir = case_dir / "postProcessing"
    if not post_dir.exists():
        return 0.0

    p_in, p_out = None, None
    
    # Procura arquivos de superfície dentro de postProcessing
    for dat_file in post_dir.rglob("*.dat"):
        file_str = str(dat_file).lower()
        if "inlet" in file_str:
            with open(dat_file, "r") as f:
                lines = [l.strip() for l in f.readlines() if l.strip() and not l.startswith("#")]
                if lines:
                    p_in = float(lines[-1].split()[-1])
        elif "outlet" in file_str:
            with open(dat_file, "r") as f:
                lines = [l.strip() for l in f.readlines() if l.strip() and not l.startswith("#")]
                if lines:
                    p_out = float(lines[-1].split()[-1])

    if p_in is not None and p_out is not None:
        return abs(p_in - p_out)
    
    return 0.0

def update_simulation_config_factor(recommended_factor: float):
    """Atualiza a linha 'mesh_factor' no simulation_config.py com o fator ideal."""
    config_path = ROOT_DIR / "config" / "simulation_config.py"
    
    if not config_path.exists():
        print(f"[-] Arquivo não encontrado: {config_path}")
        return

    content = config_path.read_text(encoding="utf-8")
    
    # Substitui a linha mesh_factor no arquivo de configuração
    updated_content = re.sub(
        r"(mesh_factor\s*:\s*float\s*=\s*|mesh_factor\s*=\s*)([\d\.]+)",
        rf"\g<1>{recommended_factor:.3f}",
        content
    )
    
    config_path.write_text(updated_content, encoding="utf-8")
    print(f"\n[+] Sucesso! 'mesh_factor = {recommended_factor:.3f}' atualizado em config/simulation_config.py!")

GRID_FACTORS = {
        "Grossa": 0.707,
        "Média":  1.000,
        "Fina":   1.414
        }

def update_simulation_config_factor(recommended_factor: float):
    """Atualiza a linha 'mesh_factor' no simulation_config.py com o fator ideal."""
    config_path = ROOT_DIR / "config" / "simulation_config.py"
    
    if not config_path.exists():
        print(f"[-] Arquivo não encontrado: {config_path}")
        return

    content = config_path.read_text(encoding="utf-8")
    
    # Substitui a atribuição do mesh_factor no arquivo de configuração
    updated_content = re.sub(
        r"(mesh_factor\s*:\s*float\s*=\s*|mesh_factor\s*=\s*)([\d\.]+)",
        rf"\g<1>{recommended_factor:.3f}",
        content
    )
    
    config_path.write_text(updated_content, encoding="utf-8")
    print(f"\n[+] Sucesso! 'mesh_factor = {recommended_factor:.3f}' atualizado em config/simulation_config.py!")

def run_grid_study():

    case_dir = ROOT_DIR / "template_case"
    cfg = SimulationConfig()
    
    SHORT_END_TIME = 1.5 
    base_nx, base_ny, base_nz = cfg.nx, cfg.ny, cfg.nz  # Ex: Malha base do generate_mesh.py
    r = GRID_FACTORS["Fina"]

    # Força valores inteiros diferentes para cada malha
    nx_grossa, ny_grossa = max(1, int(round(base_nx / r))), max(1, int(round(base_ny / r)))
    nx_media,  ny_media  = base_nx, base_ny
    nx_fina,   ny_fina   = int(round(base_nx * r)), int(round(base_ny * r))

    grids = {
        "Grossa": (nx_grossa, ny_grossa, base_nz),
        "Média":  (nx_media,  ny_media,  base_nz),
        "Fina":   (nx_fina,   ny_fina,   base_nz)
    }

    results = []
    total_start_time = time.time()  # Marca início do teste completo

    print("=" * 80)
    print("PIPELINE DEDICADO: TESTE DE INDEPENDÊNCIA DE MALHA (GCI)")
    print("=" * 80)

    for name, (nx, ny, nz) in grids.items():
        print(f"\n[+] Processando Malha {name} ({nx}x{ny}x{nz})...")
        grid_start_time = time.time()
        
        # Limpa o caso antigo
        subprocess.run(
            "rm -rf processor* postProcessing [0-9]* log.* template_case/processor*",
            shell=True, cwd=case_dir, stderr=subprocess.DEVNULL
        )
        
        # A) Atualiza objeto de configuração
        cfg = cfg.model_copy(update={"nx": nx, "ny": ny, "nz": nz})
        
        # B) Executa setups PRIMEIRO
        subprocess.run(f"python3 {ROOT_DIR}/scripts/setup_0.py", shell=True, check=True)
        subprocess.run(f"python3 {ROOT_DIR}/scripts/setup_constant.py", shell=True, check=True)
        subprocess.run(f"python3 {ROOT_DIR}/scripts/setup_system.py", shell=True, check=True)

        # C) Regera o blockMeshDict COM AS NOVAS DIMENSÕES POR ÚLTIMO
        blockmesh_path = case_dir / "system" / "blockMeshDict"
        gm.generate_blockmesh_dict(cfg, blockmesh_path)
        
        # D) Executa simulação
        run_cmd("blockMesh", case_dir)
        run_cmd("setFields", case_dir)
        run_cmd("decomposePar", case_dir)
        run_cmd(f"foamDictionary -entry endTime -set {SHORT_END_TIME} system/controlDict", case_dir)
        run_cmd("mpirun -np 10 interFoam -parallel", case_dir)

        # E) Captura métricas
        grid_elapsed_time = time.time() - grid_start_time
        delta_p, yplus = extract_dp_and_yplus(case_dir)
        n_cells = nx * ny * nz

        results.append({
            "name": name, "cells": n_cells, "dp": delta_p, 
            "yplus": yplus, "nx": nx, "ny": ny, "elapsed_time": grid_elapsed_time
        })

    total_elapsed_time = time.time() - total_start_time  # Tempo total do estudo

    # Cálculo dos erros relativos
    dp_g, dp_m, dp_f = results[0]["dp"], results[1]["dp"], results[2]["dp"]
    err_m_g = abs((dp_m - dp_g) / dp_m) * 100 if dp_m != 0 else 0
    err_f_m = abs((dp_f - dp_m) / dp_f) * 100 if dp_f != 0 else 0

    print("\n" + "=" * 85)
    print("RESULTADO DA CONVERGÊNCIA DE MALHA E TEMPO DE EXECUÇÃO")
    print("=" * 85)
    print(f"{'Malha':<8} | {'Células':<10} | {'y+ Médio':<10} | {'ΔP (Pa)':<12} | {'Erro Rel.':<12} | {'Tempo Sim.':<12}")
    print("-" * 85)
    print(f"{results[0]['name']:<8} | {results[0]['cells']:<10} | {results[0]['yplus']:<10.2f} | {dp_g:<12.4f} | {'-':<12} | {results[0]['elapsed_time']:<10.2f}s")
    print(f"{results[1]['name']:<8} | {results[1]['cells']:<10} | {results[1]['yplus']:<10.2f} | {dp_m:<12.4f} | {err_m_g:<11.2f}% | {results[1]['elapsed_time']:<10.2f}s")
    print(f"{results[2]['name']:<8} | {results[2]['cells']:<10} | {results[2]['yplus']:<10.2f} | {dp_f:<12.4f} | {err_f_m:<11.2f}% | {results[2]['elapsed_time']:<10.2f}s")
    print("=" * 85)
    
    # Formata o tempo total em Minutos:Segundos
    mins, secs = divmod(total_elapsed_time, 60)
    print(f"TEMPO TOTAL DO TESTE DE INDEPENDÊNCIA: {int(mins)}m {secs:.2f}s ({total_elapsed_time:.2f}s)")
    
    best_mesh = results[1] if err_f_m < 2.0 else results[2]
    print(f"\n RECOMMENDED MESH FOR FULL PIPELINE: Malha '{best_mesh['name']}' ({best_mesh['nx']}x{best_mesh['ny']}x{cfg.nz})")

    best_config = {"nx": best_mesh["nx"], "ny": best_mesh["ny"], "nz": cfg.nz}
    with open(ROOT_DIR / "config" / "optimal_mesh.json", "w") as f:
        json.dump(best_config, f, indent=4)

    # 1. Avalia o erro correto (err_f_m)
    if err_f_m < 0.1:
        recommended_mesh = "Média"
    else:
        recommended_mesh = "Fina"

    # 2. Resgata o fator no dicionário
    recommended_factor = GRID_FACTORS[recommended_mesh]
    print(f"\n RECOMMENDED MESH FOR FULL PIPELINE: Malha '{recommended_mesh}' (Factor: {recommended_factor})")

    # 3. Chama a função para reescrever o arquivo do simulation_config.py
    update_simulation_config_factor(recommended_factor)

if __name__ == "__main__":
    run_grid_study()