import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

# Importa a classe de configuração para ler os parâmetros reais usados
from config.simulation_config import SimulationConfig

def plot_comparison():
    cfg = SimulationConfig()
    fig, ax = plt.subplots(figsize=(9.5, 6))
    
    # Posição Z calculada dinamicamente com base no comprimento real do duto
    z_pos = cfg.length * 0.875 
    
    cases = {
        'kEpsilon': BASE_DIR / "runs" / "run_kEpsilon",
        'kOmegaSST': BASE_DIR / "runs" / "run_kOmegaSST"
    }
    
    colors = {'kEpsilon': '#1f77b4', 'kOmegaSST': '#d62728'}
    has_data = False
    
    print("=" * 60)
    print("GERANDO GRÁFICO COMPARATIVO DE VELOCIDADE COM MÉTRICAS DINÂMICAS")
    print("=" * 60)
    
    # 1. Leitura dos perfis de velocidade em postProcessing
    for label, case_dir in cases.items():
        base_post = case_dir / "postProcessing"
        if not base_post.exists():
            continue
            
        profile_files = sorted([f for f in base_post.rglob("*profile_mid*") if f.is_file()])
        
        if profile_files:
            target_file = profile_files[-1]
            try:
                df = pd.read_csv(target_file, sep=r'\s+', comment='#', header=None, engine='python')
                if not df.empty and df.shape[1] >= 2:
                    y = df.iloc[:, 0]
                    uz = df.iloc[:, -1]
                    
                    ax.plot(uz, y, label=f'Modelo {label}', color=colors.get(label, 'black'), linewidth=2)
                    has_data = True
                    print(f"[OK] Perfil lido para {label}")
            except Exception as e:
                print(f"[Aviso] Erro ao ler {target_file.name}: {e}")

    # 2. Leitura DINÂMICA das métricas registradas no CSV + Configuração
    metrics_file = BASE_DIR / "simulation_metrics.csv"
    if metrics_file.exists():
        try:
            df_m = pd.read_csv(metrics_file)
            
            # Puxa o número de células da malha (pega do primeiro registro já que é idêntica)
            total_cells = int(df_m['Mesh_Cells'].iloc[0]) if 'Mesh_Cells' in df_m.columns and not df_m.empty else "N/A"
            
            # Cabeçalho com Parâmetros Fixos Globais (incluindo a Malha)
            info_text = (
                f"$U_{{in}} = {cfg.velocity_inlet:.2f}$ m/s | $t_{{sim}} = {cfg.end_time:.1f}$ s\n"
                f"Malha: {total_cells} células\n"
                + "-"*35 + "\n"
            )
            
            # Métricas específicas calculadas por modelo (y+ e Delta P)
            for _, row in df_m.iterrows():
                model = row.get('Model', 'N/A')
                
                # Formatação tolerante para y+ e Delta P
                yplus_val = row.get('yPlus_Avg', 'N/A')
                yplus_str = f"{yplus_val:.2f}" if isinstance(yplus_val, (int, float)) else str(yplus_val)
                
                dp_val = row.get('Delta_P_Pa', 'N/A')
                dp_str = f"{dp_val:.2f}" if isinstance(dp_val, (int, float)) else str(dp_val)
                
                info_text += (
                    f"[{model}]\n"
                    f" • $y^+_{{avg}}$: {yplus_str}\n"
                    f" • $\Delta P$: {dp_str} Pa\n\n"
                )

            # Bloco de texto posicionado na margem esquerda, centralizado na vertical
            ax.text(
                0.03, 0.50, info_text.strip(),
                transform=ax.transAxes,
                fontsize=11,
                verticalalignment='center',
                horizontalalignment='left',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.9, edgecolor='#cccccc')
            )
            print("[OK] Bloco de métricas atualizado com a malha nos parâmetros globais.")
        except Exception as e:
            print(f"[Aviso] Não foi possível ler as métricas dinâmicas: {e}")

    # 3. Formatação final do gráfico
    ax.set_xlabel('Velocidade Perpendicular $U_z$ [m/s]', fontsize=11)
    ax.set_ylabel('Posição Vertical $y$ [m]', fontsize=11)
    ax.set_title(rf'Perfil Comparativo de Velocidade $U_z$ em $z = {z_pos:.2f}\text{{ m}}$', fontsize=13, pad=12)
    
    ax.grid(True, linestyle='--', alpha=0.6)
    if has_data:
        ax.legend(frameon=True, facecolor='white', framealpha=0.9, loc='upper right')
        
    out_img = BASE_DIR / "rans_velocity_comparison.png"
    plt.savefig(out_img, dpi=300, bbox_inches='tight')
    plt.close()
    print("=" * 60)
    print(f"[GRÁFICO] Imagem salva em: {out_img}")

if __name__ == "__main__":
    plot_comparison()