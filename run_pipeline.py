import os
import subprocess
import sys
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
sys.path.append(str(ROOT_DIR))

from config.simulation_config import SimulationConfig

CASE_DIR = ROOT_DIR / "template_case"

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

def reset_case_directory():
    print("Limpando diretórios antigos e preparando estrutura...")
    if CASE_DIR.exists():
        shutil.rmtree(CASE_DIR)
    
    (CASE_DIR / "0").mkdir(parents=True, exist_ok=True)
    (CASE_DIR / "constant").mkdir(parents=True, exist_ok=True)
    (CASE_DIR / "system").mkdir(parents=True, exist_ok=True)

def run_step(description: str, command: list[str], log_file_path: Path = None):
    print(f"\n[Executando]: {description}")
    current_env = os.environ.copy()
    
    if command[0] == sys.executable or command[0].endswith("python3") or command[0].endswith("python"):
        result = subprocess.run(command, capture_output=False, text=True, env=current_env)
    else:
        full_cmd_str = OF_ENV + " " + " ".join(command)
        if log_file_path:
            full_cmd_str += f" > {log_file_path} 2>&1"

        result = subprocess.run(
            full_cmd_str,
            shell=True,
            executable="/bin/bash",
            capture_output=False,
            text=True,
            env=current_env
        )
    
    if result.returncode != 0:
        print(f"\n[ERRO]: Falha na etapa -> {description}")
        sys.exit(1)

def main():
    print("=" * 60)
    print("INICIANDO PIPELINE CFD - MULTIFÁSICO (ÁGUA + ÓLEO)")
    print("=" * 60)

    cfg = SimulationConfig()

    # 1. Limpeza total da pasta do caso
    reset_case_directory()

    # 2. Geração dos dicionários Python -> OpenFOAM
    run_step("Criando condições iniciais e de contorno (0/)", [sys.executable, "scripts/setup_0.py"])
    run_step("Criando propriedades físicas dos fluidos (constant/)", [sys.executable, "scripts/setup_constant.py"])
    run_step("Criando esquemas numéricos e de controle (system/)", [sys.executable, "scripts/setup_system.py"])
    
    # Gerar a malha DEPOIS de preparar o diretório system/
    run_step("Gerando arquivo blockMeshDict", [sys.executable, "scripts/generate_mesh.py"])

    # 3. Construção da Malha e Inicialização de Fases
    run_step("Gerando malha 3D com blockMesh", ["blockMesh", "-case", str(CASE_DIR)])
    run_step("Validando malha pré-simulação", [sys.executable, "scripts/post_process.py", "--pre"])
    run_step("Inicializando fração de água/óleo com setFields", ["setFields", "-case", str(CASE_DIR)])

    # 4. Decomposição e Execução em Paralelo (interFoam)
    run_step("Decompondo domínio com decomposePar", ["decomposePar", "-case", str(CASE_DIR)])

    log_file = CASE_DIR / "interFoam.log"
    num_procs = str(cfg.num_processors)

    run_step(
        f"Rodando interFoam em paralelo ({num_procs} cores)",
        ["mpirun", "-np", num_procs, "interFoam", "-parallel", "-case", str(CASE_DIR)],
        log_file_path=log_file
    )

    # 5. Reconstrução e Pós-Processamento
    run_step("Reconstruindo domínio paralelo", ["reconstructPar", "-latestTime", "-case", str(CASE_DIR)])
    run_step("Processando resultados finais", [sys.executable, "scripts/post_process.py"])

    print("=" * 60)
    print("PIPELINE MULTIFÁSICO EXECUTADO COM SUCESSO!")
    print("=" * 60)

if __name__ == "__main__":
    main()