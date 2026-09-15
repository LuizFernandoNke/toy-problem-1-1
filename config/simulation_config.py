import math
from pydantic import BaseModel, Field

class FluidProps(BaseModel):
    rho: float = Field(..., gt=0, description="Densidade em kg/m3")
    nu: float = Field(..., gt=0, description="Viscosidade cinemática em m2/s")

class SimulationConfig(BaseModel):
    case_name: str = "PipeFlow_Water_Oil_KH"

    # Controle de Tempo e Estabilidade Numérica (Ajustados para KH)
    end_time: float = Field(default=5.0, gt=0, description="Tempo final de simulação em segundos")
    delta_t: float = Field(default=0.01, gt=0, description="Passo de tempo inicial em segundos")
    max_co: float = Field(default=1, gt=0, le=1.0, description="Número de Courant máximo para capturar KH")
    max_alpha_co: float = Field(default=0.5, gt=0, le=1.0, description="Courant máximo da interface (maxAlphaCo)")
    max_delta_t: float = Field(default=0.01, gt=0, description="Passo de tempo máximo permitido em segundos")
    write_interval: float = Field(default=0.05, gt=0, description="Frequência alta de gravação para animação das ondas")
    
    # Geometria do duto
    diameter: float = Field(default=0.05, gt=0, description="Diâmetro em metros")
    length: float = Field(default=2.0, gt=0, description="Comprimento em metros")
    
    # Condições de Entrada - Kelvin-Helmholtz (Cisalhamento Elevado ΔU = 1.0 m/s)
    velocity_water: float = Field(default=0.5, gt=0, description="Velocidade da fase água (fundo) em m/s")
    velocity_oil: float = Field(default=0.3, gt=0, description="Velocidade da fase óleo (topo) em m/s")
    velocity_inlet: float = Field(default=0.70, gt=0, description="Velocidade média equivalente de entrada em m/s")
    
    initial_velocity_x: float = Field(default=1e-6, ge=0, description="Velocidade inicial em X")
    inlet_alpha_water: float = Field(default=0.5, ge=0.0, le=1.0, description="Fração de água na entrada (interface no meio)")

    # Modelo de Turbulência
    turbulence_model: str = Field(default="kOmegaSST", description="Modelo RAS de turbulência")
    
    # Propriedades dos Fluidos (Água e Óleo)
    water: FluidProps = Field(default_factory=lambda: FluidProps(rho=998.2, nu=1e-6))
    oil: FluidProps = Field(default_factory=lambda: FluidProps(rho=890.0, nu=1e-5))
    
    # Tensão superficial entre água e óleo
    sigma: float = Field(default=0.03, ge=0, description="Tensão superficial N/m")

    # Malha e Paralelismo
    mesh_factor: float = 1
    num_processors: int = 10

    # Atalhos e Retrocompatibilidade
    @property
    def delta_u(self) -> float:
        """Diferença de velocidade interfacial que alimenta a instabilidade de KH."""
        return abs(self.velocity_water - self.velocity_oil)

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
    def water_density(self) -> float:
        return self.water.rho

    @property
    def water_viscosity(self) -> float:
        return self.water.nu

    @property
    def oil_density(self) -> float:
        return self.oil.rho

    @property
    def oil_viscosity(self) -> float:
        return self.oil.nu

    @property
    def inlet_flow_rate(self) -> float:
        area = math.pi * (self.diameter / 2.0) ** 2
        return self.velocity_inlet * area

    @property
    def reynolds_water(self) -> float:
        return (self.velocity_water * self.diameter) / self.water.nu

    @property
    def surface_tension(self) -> float:
        return self.sigma