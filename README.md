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

---

## Simulação da Instabilidade de Kelvin-Helmholtz (KH)

O projeto também permite simular o regime transitório de cisalhamento interfacial e a formação de ondas de Kelvin-Helmholtz entre a água e o óleo.

### Como Ativar a Instabilidade de KH
Para induzir a instabilidade, basta configurar velocidades de entrada distintas ($\Delta U \neq 0$) para as fases no arquivo `config/simulation_config.py`:

```python
# Exemplo de configuração para Instabilidade de KH:
velocity_water: float = 0.5  # Velocidade da água (fase inferior)
velocity_oil: float = 0.3    # Velocidade do óleo (fase superior)

### Implementação Técnica: `codedFixedValue` vs. `fixedValue`

Para a simulação da Instabilidade de Kelvin-Helmholtz (KH), a condição de contorno padrão `fixedValue` do OpenFOAM **não é adequada**:

O arquivo `0/U` foi parametrizado via Python com um bloco C++ compilado em tempo de execução (*on-the-fly*). A velocidade escalar de referência `velocity_inlet` é ignorada pelo solver na entrada, dando lugar ao perfil suavizado via tangente hiperbólica ($\tanh$):

* **Superfície de Entradas:** Varre as coordenadas geométricas $y$ da entrada.
* **Transição Suave (Camada de 2mm):** Aplica a transição contínua entre `velocity_water` e `velocity_oil`:
  $$\mathbf{U}(y) = \mathbf{U}_{\text{water}} \cdot (1 - b(y)) + \mathbf{U}_{\text{oil}} \cdot b(y), \quad \text{onde } b(y) = \frac{1}{2}\left(1 + \tanh\left(\frac{y}{\delta}\right)\right)$$
* **Impacto no Pós-processamento:** A variável `velocity_inlet` é mantida no `simulation_config.py` como parâmetro escalar global apenas para estimativas analíticas ($Re$ e $\Delta P_{\text{Blasius}}$) executadas pelo Python.