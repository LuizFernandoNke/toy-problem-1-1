import os
import subprocess
import sys
import shutil
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
sys.path.append(str(ROOT_DIR))

from config.simulation_config import SimulationConfig

# Pasta base para templates e pasta de execuções paralelas
TEMPLATE_CASE = ROOT_DIR / "template_case"
RUNS_DIR = ROOT_DIR / "runs"

# Modelos RANS que o professor pediu para comparar
RANS_MODELS = ["kEpsilon", "kOmegaSST"]

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

def reset_directory(dir_path: Path):
    """Limpa e cria a estrutura base de um diretório de simulação."""
    if dir_path.exists():
        shutil.rmtree(dir_path)
    (dir_path / "0").mkdir(parents=True, exist_ok=True)
    (dir_path / "constant").mkdir(parents=True, exist_ok=True)
    (dir_path / "system").mkdir(parents=True, exist_ok=True)

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

def set_ras_model(case_dir: Path, model_name: str):
    """Atualiza a propriedade RASModel no arquivo de turbulência do OpenFOAM."""
    mom_file = case_dir / "constant" / "momentumTransport"
    turb_file = case_dir / "constant" / "turbulenceProperties"
    target_file = mom_file if mom_file.exists() else turb_file

    if target_file.exists():
        with open(target_file, "r") as f:
            content = f.read()
        
        updated_content = re.sub(r'(RASModel\s+)[^;]+;', rf'\g<1>{model_name};', content)

        with open(target_file, "w") as f:
            f.write(updated_content)

def main():
    print("=" * 60)
    print("INICIANDO PIPELINE CFD - ESTUDO COMPARATIVO RANS (k-e vs k-w)")
    print("=" * 60)

    cfg = SimulationConfig()

    # ------------------------------------------------------------------
    # ETAPA 1: Construção da Pasta Modelo (Template)
    # ------------------------------------------------------------------
    print("\n--- PASSO 1: Gerando Arquivos Base no Template ---")
    reset_directory(TEMPLATE_CASE)

    run_step("Criando condições iniciais e de contorno (0/)", [sys.executable, "scripts/setup_0.py"])
    run_step("Criando propriedades físicas dos fluidos (constant/)", [sys.executable, "scripts/setup_constant.py"])
    run_step("Criando esquemas numéricos e de controle (system/)", [sys.executable, "scripts/setup_system.py"])
    run_step("Gerando arquivo blockMeshDict", [sys.executable, "scripts/generate_mesh.py"])

    # ------------------------------------------------------------------
    # ETAPA 2: Loop de Execução dos Modelos de Turbulência
    # ------------------------------------------------------------------
    RUNS_DIR.mkdir(exist_ok=True)

    for model in RANS_MODELS:
        print("\n" + "=" * 60)
        print(f"  INICIANDO SIMULAÇÃO PARA O MODELO: {model}")
        print("=" * 60)

        case_dir = RUNS_DIR / f"run_{model}"
        
        # 1. Copia o template pronto para a pasta da execução específica
        if case_dir.exists():
            shutil.rmtree(case_dir)
        shutil.copytree(TEMPLATE_CASE, case_dir)

        # 2. Ajusta o modelo RANS
        set_ras_model(case_dir, model)

        # 3. Construção da Malha e Inicialização de Fases
        run_step(f"[{model}] Gerando malha com blockMesh", ["blockMesh", "-case", str(case_dir)])
        run_step(f"[{model}] Validando malha pré-simulação", [sys.executable, "scripts/post_process.py", "--pre"])
        run_step(f"[{model}] Inicializando fração água/óleo (setFields)", ["setFields", "-case", str(case_dir)])

        # 4. Decomposição e Execução Paralela
        run_step(f"[{model}] Decompondo domínio (decomposePar)", ["decomposePar", "-case", str(case_dir)])

        log_file = case_dir / f"interFoam_{model}.log"
        num_procs = str(cfg.num_processors)

        run_step(
            f"[{model}] Rodando interFoam ({num_procs} cores)",
            ["mpirun", "-np", num_procs, "interFoam", "-parallel", "-case", str(case_dir)],
            log_file_path=log_file
        )

        # 5. Reconstrução e Arquivo para ParaView
        run_step(f"[{model}] Reconstruindo domínio (reconstructPar)", ["reconstructPar", "-latestTime", "-case", str(case_dir)])
        
        # Cria arquivo .foam para facilitar a abertura no ParaView
        (case_dir / f"{model}.foam").touch()

    # ------------------------------------------------------------------
    # ETAPA 3: Pós-Processamento dos Casos Executados
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PASSO 3: Pós-Processamento e Análise de Resultados")
    print("=" * 60)
    
    run_step("Processando resultados kEpsilon", [sys.executable, "scripts/post_process.py", "-case", str(RUNS_DIR / "run_kEpsilon")])
    run_step("Processando resultados kOmegaSST", [sys.executable, "scripts/post_process.py", "-case", str(RUNS_DIR / "run_kOmegaSST")])

    # ------------------------------------------------------------------
    # ETAPA 4: Comparação e Geração de Gráficos
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PASSO 4: Gerando Gráficos Comparativos RANS")
    print("=" * 60)

    run_step("Gerando comparações de gráficos e perfis", [sys.executable, "scripts/compare_rans.py"])

    print("\n" + "=" * 60)
    print("PIPELINE CFD FINALIZADO COM SUCESSO!")
    print("=" * 60)
    
if __name__ == "__main__":
    main()