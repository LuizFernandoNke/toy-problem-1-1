import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from config.simulation_config import SimulationConfig

def plot_comparison():
    cfg = SimulationConfig()
    fig, ax = plt.subplots(figsize=(9.5, 6))
    z_pos = cfg.length * 0.875

    cases = {
        'kEpsilon': BASE_DIR / "runs" / "run_kEpsilon",
        'kOmegaSST': BASE_DIR / "runs" / "run_kOmegaSST"
    }
    colors = {'kEpsilon': '#1f77b4', 'kOmegaSST': '#d62728'}
    has_data = False

    for label, case_dir in cases.items():
        base_post = case_dir / "postProcessing"
        if not base_post.exists():
            continue
        
        profile_files = sorted([f for f in base_post.rglob("*profile_mid*") if f.is_file()])
        
        for target_file in reversed(profile_files):
            try:
                df = pd.read_csv(target_file, sep=r'\s+', comment='#', header=None, engine='python')
                if not df.empty and df.shape[1] >= 2:
                    y = df.iloc[:, 0]
                    uz = df.iloc[:, -1]
                    ax.plot(uz, y, label=f'Modelo {label}', color=colors.get(label, 'black'), linewidth=2)
                    has_data = True
                    break
            except Exception:
                pass

    # Apontado corretamente para results.csv
    metrics_file = BASE_DIR / "results.csv"
    if metrics_file.exists():
        try:
            df_m = pd.read_csv(metrics_file)
            cells = int(df_m['Mesh_Cells'].iloc[0]) if 'Mesh_Cells' in df_m.columns else "N/A"
            
            dp_b = df_m['Delta_P_Blasius_Pa'].iloc[0] if 'Delta_P_Blasius_Pa' in df_m.columns else "N/A"
            dp_blasius = f"{float(dp_b):.2f}" if isinstance(dp_b, (int, float)) else str(dp_b)

            info_text = (
                rf"$U_{{in}} = {cfg.velocity_inlet:.2f}\text{{ m/s}}$ | $t_{{sim}} = {cfg.end_time:.1f}\text{{ s}}$" + "\n"
                rf"Malha: {cells} cél. | $\Delta P_{{Blasius}} = {dp_blasius}\text{{ Pa}}$" + "\n"
                + "-"*35 + "\n"
            )

            for _, row in df_m.iterrows():
                model = row.get('Model', 'N/A')
                yplus_val = row.get('yPlus_Avg', 'N/A')
                dp_val = row.get('Delta_P_Pa', 'N/A')
                err_val = row.get('Error_Rel_Pct', 'N/A')

                yplus = f"{float(yplus_val):.2f}" if isinstance(yplus_val, (int, float)) else str(yplus_val)
                dp = f"{float(dp_val):.2f}" if isinstance(dp_val, (int, float)) else str(dp_val)
                err = f"{float(err_val):.1f}" if isinstance(err_val, (int, float)) else str(err_val)

                info_text += (
                    f"[{model}]\n"
                    rf" • $y^+_{{avg}}$: {yplus}" + "\n"
                    rf" • $\Delta P$: {dp} Pa (Erro: {err}%)" + "\n\n"
                )

            ax.text(
                0.03, 0.50, info_text.strip(),
                transform=ax.transAxes,
                fontsize=8,
                verticalalignment='center',
                horizontalalignment='left',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.9, edgecolor='#cccccc')
            )
        except Exception as e:
            print(f"[Aviso] Erro ao carregar caixa de texto: {e}")
    else:
        print(f"[Aviso] Arquivo de métricas ({metrics_file.name}) não foi encontrado!")

    ax.set_xlabel('Velocidade Perpendicular $U_z$ [m/s]', fontsize=11)
    ax.set_ylabel('Posição Vertical $y$ [m]', fontsize=11)
    ax.set_title(rf'Perfil Comparativo de Velocidade $U_z$ em $z = {z_pos:.2f}\text{{ m}}$', fontsize=12, pad=12)
    ax.grid(True, linestyle='--', alpha=0.6)
    
    if has_data:
        ax.legend(frameon=True, facecolor='white', framealpha=0.9, loc='upper right')

    out_img = BASE_DIR / "rans_velocity_comparison.png"
    plt.savefig(out_img, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[GRÁFICO] Imagem atualizada com sucesso em: {out_img}")

if __name__ == "__main__":
    plot_comparison()