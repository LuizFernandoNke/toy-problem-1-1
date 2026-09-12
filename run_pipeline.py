import subprocess
import os
import sys
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

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

    # [1/4] Preparação e Malha
    print("\n[1/4] Preparando Geometria e Configurações")
    run_cmd("python3 scripts/setup_system.py", "Gerando dicionarios de configuracao")
    run_cmd("python3 scripts/generate_mesh.py", "Gerando malhas")

    # Copia o dicionario de configuracao raiz para as pastas de execucao caso exista
    root_system = BASE_DIR / "system"
    if root_system.exists():
        for case in ["run_kEpsilon", "run_kOmegaSST"]:
            target_sys = BASE_DIR / "runs" / case / "system"
            target_sys.mkdir(parents=True, exist_ok=True)
            for item in root_system.iterdir():
                shutil.copy(item, target_sys / item.name)

    # [2/4] Simulações RANS
    # [2/4] Simulações RANS
    print("\n[2/4] Executando Simulações RANS em Paralelo")
    for case in ["run_kEpsilon", "run_kOmegaSST"]:
        run_cmd(f"{FOAM_ENV} && cd runs/{case} && decomposePar -force > log.decomposePar 2>&1", f"Decompondo {case}")
        run_cmd(f"{FOAM_ENV} && cd runs/{case} && mpirun -np 10 interFoam -parallel > log.interFoam 2>&1", f"Simulando interFoam {case}")
        run_cmd(f"{FOAM_ENV} && cd runs/{case} && reconstructPar -latestTime > log.reconstructPar 2>&1", f"Reconstruindo {case}")
    # [3/4] Pós-Processamento OpenFOAM
    print("\n[3/4] Processando Dados da Malha")
    for case in ["run_kEpsilon", "run_kOmegaSST"]:
        run_cmd(f"{FOAM_ENV} && cd runs/{case} && interFoam -postProcess -func yPlus -latestTime > log.yPlus 2>&1", f"Calculando y+ [{case}]")
        run_cmd(f"{FOAM_ENV} && cd runs/{case} && postProcess -func sets -latestTime > log.sampleDict 2>&1", f"Amostrando perfis [{case}]")

    # [4/4] Métricas e Gráficos Python
    print("\n[4/4] Gerando Relatórios e Gráficos")
    run_cmd("python3 scripts/post_process.py", "Extraindo metricas (simulation_metrics.csv)")
    run_cmd("python3 scripts/compare_rans.py", "Gerando grafico comparativo")

    print("\nPipeline concluído com sucesso!")

if __name__ == "__main__":
    main()