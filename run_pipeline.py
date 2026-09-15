import subprocess
import sys
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Importa os módulos de setup
sys.path.append(str(BASE_DIR))
from scripts.setup_0 import setup_zero_files
from scripts.setup_constant import setup_constant_files
from config.simulation_config import SimulationConfig

def run_cmd(cmd, desc):
    print(f"   • {desc}...", end="", flush=True)
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, executable='/bin/bash')
    if res.returncode != 0:
        print(" [ERRO]")
        print(f"\n[ERRO CRÍTICO] Falha ao executar: {cmd}")
        print(f"STDERR:\n{res.stderr}")
        sys.exit(1)
    print(" [OK]")

def main():
    print("=" * 50)
    print(" PIPELINE CFD PARALELA (interFoam - OpenFOAM v2606)")
    print("=" * 50)

    FOAM_ENV = "source /usr/lib/openfoam/openfoam2606/etc/bashrc"
    cfg = SimulationConfig()
    cases_models = {
        "run_kEpsilon": "kEpsilon",
        "run_kOmegaSST": "kOmegaSST"
    }

    # [1/4] Preparação, Limpeza e Malha
    print("\n[1/4] Preparando Geometria e Configurações")
    
    # Limpeza total das pastas de simulação antigas
    runs_dir = BASE_DIR / "runs"
    if runs_dir.exists():
        shutil.rmtree(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)

    run_cmd("python3 scripts/setup_system.py", "Gerando dicionarios de configuracao")
    run_cmd("python3 scripts/generate_mesh.py", "Gerando malhas")

    # Identifica de onde vem o system e a malha gerada
    root_system = BASE_DIR / "system"
    if not root_system.exists() and (BASE_DIR / "template_case" / "system").exists():
        root_system = BASE_DIR / "template_case" / "system"

    root_polymesh = BASE_DIR / "constant" / "polyMesh"
    if not root_polymesh.exists() and (BASE_DIR / "template_case" / "constant" / "polyMesh").exists():
        root_polymesh = BASE_DIR / "template_case" / "constant" / "polyMesh"

    # Popula a estrutura completa em runs/run_kEpsilon e runs/run_kOmegaSST
    for case, model in cases_models.items():
        case_dir = BASE_DIR / "runs" / case
        case_dir.mkdir(parents=True, exist_ok=True)

        # 1. Copia system/
        target_sys = case_dir / "system"
        target_sys.mkdir(parents=True, exist_ok=True)
        if root_system.exists():
            for item in root_system.iterdir():
                if item.is_file():
                    shutil.copy(item, target_sys / item.name)

        # 2. Copia constant/polyMesh
        target_mesh = case_dir / "constant" / "polyMesh"
        if root_polymesh.exists():
            if target_mesh.exists():
                shutil.rmtree(target_mesh)
            shutil.copytree(root_polymesh, target_mesh)

        # 3. Gerador nativo dos arquivos da pasta 0/ e constant/ no diretório do caso
        setup_zero_files(cfg, case_dir)
        try:
            setup_constant_files(cfg, case_dir, model_name=model)
        except TypeError:
            setup_constant_files(cfg, case_dir)

    # [2/4] Simulações RANS
    print("\n[2/4] Executando Simulações RANS em Paralelo")
    for case in cases_models.keys():
        case_path = (BASE_DIR / "runs" / case).resolve()
        
        # Gera a malha física no diretório atual do caso a partir do system/blockMeshDict
        run_cmd(f"{FOAM_ENV} && cd {case_path} && blockMesh > log.blockMesh 2>&1", f"Gerando malha blockMesh [{case}]")

        # Decompõe a malha gerada para os núcleos
        run_cmd(f"{FOAM_ENV} && cd {case_path} && decomposePar -force > log.decomposePar 2>&1", f"Decompondo {case}")
        
        # Executa a simulação em paralelo
        run_cmd(f"{FOAM_ENV} && cd {case_path} && mpirun -np {cfg.num_processors} interFoam -parallel > log.interFoam 2>&1", f"Simulando interFoam {case}")
        
        # Recontrói os resultados
        run_cmd(f"{FOAM_ENV} && cd {case_path} && reconstructPar > log.reconstructPar 2>&1", f"Reconstruindo todos os tempos [{case}]")

    # [3/4] Pós-Processamento OpenFOAM
    print("\n[3/4] Processando Dados da Malha")
    for case in cases_models.keys():
        case_path = (BASE_DIR / "runs" / case).resolve()
        
        run_cmd(f"{FOAM_ENV} && cd {case_path} && interFoam -postProcess -func yPlus -time {cfg.end_time} > log.yPlus 2>&1", f"Calculando y+ [{case}]")
        run_cmd(f"{FOAM_ENV} && cd {case_path} && postProcess -func sets -time {cfg.end_time} > log.sampleDict 2>&1", f"Amostrando perfis [{case}]")

    # [4/4] Métricas e Gráficos Python
    print("\n[4/4] Gerando Relatórios e Gráficos")
    run_cmd("python3 scripts/post_process.py", "Extraindo metricas (results.csv)")
    run_cmd("python3 scripts/compare_rans.py", "Gerando grafico comparativo")

    print("\nPipeline concluído com sucesso!")

if __name__ == "__main__":
    main()