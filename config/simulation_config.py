import math
from pydantic import BaseModel, Field

class FluidProps(BaseModel):
    rho: float = Field(..., gt=0, description="Densidade em kg/m3")
    nu: float = Field(..., gt=0, description="Viscosidade cinemática em m2/s")

class SimulationConfig(BaseModel):
    case_name: str = "PipeFlow_Water_Oil"
    
    # Geometria do duto
    diameter: float = Field(default=0.05, gt=0, description="Diâmetro em metros")
    length: float = Field(default=2.0, gt=0, description="Comprimento em metros")
    
    # Condições do escoamento
    velocity_inlet: float = Field(default=0.2, gt=0, description="Velocidade de entrada em m/s")
    initial_velocity_x: float = Field(default=0.0, ge=0, description="Velocidade inicial em X")
    inlet_alpha_water: float = Field(default=0.5, ge=0.0, le=1.0, description="Fração de água na entrada")

    # Modelo de Turbulencia (ex: kEpsilon, kOmegaSST, laminar)
    turbulence_model: str = Field(default="kOmegaSST", description="Modelo RAS de turbulência")
    
    # Propriedades dos Fluidos (Água e Óleo)
    water: FluidProps = Field(default_factory=lambda: FluidProps(rho=998.2, nu=1e-6))
    oil: FluidProps = Field(default_factory=lambda: FluidProps(rho=890.0, nu=1e-5))
    
    # Tensao superficial entre agua e oleo (necessario para interFoam)
    sigma: float = Field(default=0.03, ge=0, description="Tensão superficial N/m")

    # Malha e Paralelismo
    mesh_factor: float = 1.000
    num_processors: int = 10

    # Atalhos/retrocompatibilidade para manter propriedades antigas funcionando
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
        return (self.velocity_inlet * self.diameter) / self.water.nu

    @property
    def surface_tension(self) -> float:
        return self.sigma