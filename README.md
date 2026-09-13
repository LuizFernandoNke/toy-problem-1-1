# toy-problem-1-1
Refatoração do toy-problem-1 para uso de templates funcionais do OpenFOAM parametrizados via Python e Pydantic.

# Toy Problem 1-1: Automação e Validação RANS Bifásica no OpenFOAM

Refatoração do caso de teste multifásico para automação via Python, parametrização via Pydantic e validação de modelos RANS com OpenFOAM.

---

## Principais Características

* **Arquitetura Paramétrica (Pydantic):** Todas as variáveis centrais da simulação (propriedades dos fluidos, geometria, condições de contorno e esquemas numéricos) estão centralizadas e validadas no arquivo `config/simulation_config.py`.
* **Estudo de Independência de Malha Autônomo:** O script `run_grid_independence.py` funciona de forma 100% independente. Ele executa o teste variando os fatores de refino espacial:
  * **Grossa:** `0.707`
  * **Média:** `1.000`
  * **Fina:** `1.414`
  
  Ao final da execução, ele identifica o fator ótimo e atualiza automaticamente as configurações no `simulation_config.py`.
* **Geração de Saídas e Pipeline:** A execução da pipeline gera automaticamente:
  * Um arquivo `results.csv` consolidando métricas físicas e de desempenho ($y^+$, $\Delta P$, erro relativo e tempo de execução).
  * Um gráfico comparativo de velocidade (`rans_velocity_comparison.png`) confrontando os modelos simulados.

---

## Status Atual e Resultados de Validação

A validação da perda de carga ($\Delta P$) é realizada na **região com escoamento hidrodinamicamente desenvolvido** ($z = 1.2\text{m}$ a $1.9\text{m}$) e comparada com a solução analítica de Blasius/Poiseuille ponderada para misturas bifásicas:

| Modelo RANS | $\Delta P$ Simulado (Pa) | $\Delta P$ Teórico (Pa) | Erro Relativo (%) | $y^+$ Médio |
| :--- | :---: | :---: | :---: | :---: |
| **$k-\epsilon$** | 36.27 | 27.57 | **31.57%** | 9.53 |
| **$k-\omega$ SST** | 22.09 | 27.57 | **19.86%** | 8.19 |

> **Nota:** O modelo **$k-\omega$ SST** apresentou melhor aderência devido ao tratamento mais preciso na camada limite viscosa e na interface multifásica (VOF).