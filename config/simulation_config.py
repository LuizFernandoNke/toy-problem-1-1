import math
from typing import ClassVar
from pydantic import BaseModel, Field


class FluidProps(BaseModel):
    rho: float = Field(..., gt=0, description="Densidade em kg/m3")
    nu: float = Field(..., gt=0, description="Viscosidade cinemática em m2/s")


class SimulationConfig(BaseModel):
    case_name: str = "PipeFlow_Oil_Gas_Stratified"

    # Controle de Tempo e Estabilidade Numérica
    end_time: float = Field(default=8, gt=0, description="Tempo final de simulação em segundos")
    delta_t: float = Field(default=1e-5, gt=0, description="Passo de tempo inicial em segundos")
    max_co: float = Field(default=1.0, gt=0, le=1.0, description="Número de Courant máximo")
    max_alpha_co: float = Field(default=0.5, gt=0, le=1.0, description="Courant máximo da interface")
    max_delta_t: float = Field(default=0.01, gt=0, description="Passo de tempo máximo permitido em segundos")
    write_interval: float = Field(default=0.1, gt=0, description="Frequência de gravação")

    # ==========================================================================
    # DADOS EXPERIMENTAIS DO ENSAIO (MukherjeeHor 1979 - GLDataID = 26894)
    # ==========================================================================
    DIAMETER: ClassVar[float] = 0.0381             # Diâmetro interno (m)
    LENGTH: ClassVar[float] = 2.0                  # Comprimento do domínio (m)
    ALPHA_OIL: ClassVar[float] = 0.08              # Fração volumétrica do óleo (fundo)
    U_SUPERFICIAL_OIL: ClassVar[float] = 0.039624  # Velocidade superficial do óleo (m/s)
    U_SUPERFICIAL_GAS: ClassVar[float] = 3.483864  # Velocidade superficial do gás (m/s)

    AREA: ClassVar[float] = math.pi * (DIAMETER ** 2) / 4.0
    ALPHA_GAS: ClassVar[float] = 1.0 - ALPHA_OIL

    # ==========================================================================
    # GEOMETRIA E PAREDE
    # ==========================================================================
    diameter: float = Field(default=DIAMETER, gt=0, description="Diâmetro interno em metros")
    length: float = Field(default=LENGTH, gt=0, description="Comprimento do domínio em metros")
    roughness: float = Field(default=3.00228e-5, ge=0.0, description="Rugosidade absoluta Ks da parede em metros")

    # ==========================================================================
    # FRAÇÕES VOLUMÉTRICAS E VELOCIDADES REAIS DE ENTRADA
    # ==========================================================================
    inlet_alpha_oil: float = Field(
        default=ALPHA_OIL, ge=0.0, le=1.0, description="Fração volumétrica de óleo na entrada (fundo)"
    )
    inlet_alpha_gas: float = Field(
        default=ALPHA_GAS, ge=0.0, le=1.0, description="Fração volumétrica de gás na entrada (topo)"
    )

    velocity_oil: float = Field(
        default=U_SUPERFICIAL_OIL / ALPHA_OIL,
        gt=0,
        description="Velocidade real da fase óleo (fundo) em m/s"
    )
    velocity_gas: float = Field(
        default=U_SUPERFICIAL_GAS / ALPHA_GAS,
        gt=0,
        description="Velocidade real da fase gás (topo) em m/s"
    )
    velocity_inlet: float = Field(
        default=U_SUPERFICIAL_OIL + U_SUPERFICIAL_GAS,
        gt=0,
        description="Velocidade média equivalente de entrada (U_sl + U_sg) em m/s"
    )

    initial_velocity_x: float = Field(default=1e-6, ge=0, description="Velocidade inicial em X")

    # Modelo de Turbulência
    turbulence_model: str = Field(default="kOmegaSST", description="Modelo RAS de turbulência")

    # Propriedades dos Fluidos (nu = mu / rho da planilha)
    oil: FluidProps = Field(default_factory=lambda: FluidProps(rho=801.7835916, nu=1.696075e-6))
    gas: FluidProps = Field(default_factory=lambda: FluidProps(rho=2.376139379, nu=4.206921e-6))

    # Tensão superficial entre óleo e gás
    sigma: float = Field(default=0.024298, ge=0, description="Tensão superficial N/m")

    # Malha e Paralelismo
    mesh_factor: float = 1
    num_processors: int = 10

    # ==========================================================================
    # PROPRIEDADES DERIVADAS E RETROCOMPATIBILIDADE
    # ==========================================================================
    @property
    def delta_u(self) -> float:
        return abs(self.velocity_gas - self.velocity_oil)

    @property
    def nx(self) -> int:
        return int(20 * self.mesh_factor)

    @property
    def ny(self) -> int:
        return int(20 * self.mesh_factor)

    @property
    def nz(self) -> int:
        return int(100 * self.mesh_factor)

    @property
    def oil_density(self) -> float:
        return self.oil.rho

    @property
    def oil_viscosity(self) -> float:
        return self.oil.nu

    @property
    def gas_density(self) -> float:
        return self.gas.rho

    @property
    def gas_viscosity(self) -> float:
        return self.gas.nu

    @property
    def inlet_flow_rate(self) -> float:
        area = math.pi * (self.diameter / 2.0) ** 2
        return self.velocity_inlet * area

    @property
    def reynolds_oil(self) -> float:
        return (self.velocity_oil * self.diameter) / self.oil.nu

    @property
    def reynolds_gas(self) -> float:
        return (self.velocity_gas * self.diameter) / self.gas.nu

    @property
    def surface_tension(self) -> float:
        return self.sigma