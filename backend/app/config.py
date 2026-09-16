from copy import deepcopy


DEFAULT_COMPONENTS = {
    "base_fluid": {
        "rho": 1114.0,
        "mu": 0.0152,
        "k": 0.252,
        "sigma": 1.07e-6,
        "cp": 2415.0,
        "is_base_fluid": True,
    },
    "mos2": {
        "rho": 5060.0,
        "mu": None,
        "k": 904.4,
        "sigma": 2.09e4,
        "cp": 397.21,
        "is_base_fluid": False,
    },
    "cu": {
        "rho": 8933.0,
        "mu": None,
        "k": 400.0,
        "sigma": 5.96e7,
        "cp": 385.0,
        "is_base_fluid": False,
    },
}

DEFAULT_BASE_PARAMS = {
    "N": 41,
    "ms": 60,
    "L": 8,
    "tol": 1e-10,
    "S": 0.1,
    "A": 0.1,
    "We": 0.1,
    "omega": 1.0,
    "Pr": 6.72,
    "Sc": 1.0,
    "Ec": 0.05,
    "M": 1.0,
    "Rd": 1.0,
    "beta_T": 0.05,
    "K1": 0.1,
    "beta_C": 0.05,
    "Nb": 0.1,
    "Nt": 0.1,
    "Bi": 2.0,
    "Bi_m": 2.0,
    "Q": 0.1,
    "convergence_type": "absolute",
    "res": True,
}

DEFAULT_NANOFLUIDS = [
    {
        "name": "MoS2/EG",
        "display_name": "MoS2/EG",
        "phi1": 0.01,
        "phi2": 0.0,
        "enabled": True,
    },
    {
        "name": "Cu/EG",
        "display_name": "Cu/EG",
        "phi1": 0.0,
        "phi2": 0.03,
        "enabled": True,
    },
    {
        "name": "MoS2-Cu/EG",
        "display_name": "MoS2-Cu/EG",
        "phi1": 0.01,
        "phi2": 0.03,
        "enabled": True,
    },
]

PARAMETER_CATALOG = {
    "Pr": {"label": "Pr", "description": "Prandtl number", "suggested_values": [4, 6, 8, 10]},
    "We": {"label": "We", "description": "Weissenberg number", "suggested_values": [0.0, 0.1, 0.2, 0.3]},
    "M": {"label": "M", "description": "Magnetic parameter", "suggested_values": [0.2, 0.5, 1.0, 2.0]},
    "Rd": {"label": "Rd", "description": "Radiation parameter", "suggested_values": [0.5, 1.0, 2.0, 3.0]},
    "Ec": {"label": "Ec", "description": "Eckert number", "suggested_values": [0.0, 0.01, 0.05, 0.1, 0.2]},
    "Q": {"label": "Q", "description": "Heat source parameter", "suggested_values": [-0.2, -0.1, 0.0, 0.1, 0.2]},
    "beta_T": {"label": "beta_T", "description": "Thermal relaxation parameter", "suggested_values": [0.0, 0.025, 0.05, 0.1]},
    "beta_C": {"label": "beta_C", "description": "Concentration relaxation parameter", "suggested_values": [0.0, 0.025, 0.05, 0.1]},
    "Bi": {"label": "Bi", "description": "Thermal Biot number", "suggested_values": [1.5, 2.0, 3.0, 4.0, 5.0]},
    "Bi_m": {"label": "Bi_m", "description": "Mass Biot number", "suggested_values": [1.5, 2.0, 3.0, 4.0, 5.0]},
    "Nb": {"label": "Nb", "description": "Brownian motion parameter", "suggested_values": [0.3, 0.5, 0.7, 1.0]},
    "Nt": {"label": "Nt", "description": "Thermophoresis parameter", "suggested_values": [0.3, 0.5, 0.7, 1.0]},
    "S": {"label": "S", "description": "Suction or injection parameter", "suggested_values": [-0.3, -0.1, 0.0, 0.1, 0.3]},
    "Sc": {"label": "Sc", "description": "Schmidt number", "suggested_values": [0.5, 1.0, 1.5, 2.0]},
    "K1": {"label": "K1", "description": "Chemical reaction parameter", "suggested_values": [0.1, 0.3, 0.5, 1.0]},
    "A": {"label": "A", "description": "Velocity ratio parameter", "suggested_values": [0.1, 0.2, 0.3, 0.4, 1.0, 1.5, 1.7, 1.8, 2.0]},
}

QUANTITY_CATALOG = {
    "skin_friction": {"label": "Skin friction", "symbol": "√(Re<sub>x</sub>) C<sub>f</sub>"},
    "nusselt": {"label": "Nusselt number", "symbol": "Nu<sub>x</sub>/√(Re<sub>x</sub>)"},
    "sherwood": {"label": "Sherwood number", "symbol": "Sh<sub>x</sub>/√(Re<sub>x</sub>)"},
}

PROFILE_CATALOG = {
    "velocity": {"label": "Velocity profile", "symbol": "f′"},
    "temperature": {"label": "Temperature profile", "symbol": "θ"},
    "concentration": {"label": "Concentration profile", "symbol": "φ"},
}

DEFAULT_PAIR_STUDY = {
    "quantity_key": "sherwood",
    "x_param": "Rd",
    "x_spec": [0.5, 3.0],
    "y_param": "M",
    "y_spec": [0.25, 2.0],
    "n_points": 7,
}

DEFAULT_PROFILE_STUDY = {
    "profile_key": "temperature",
    "param_key": "M",
    "param_values": [0.1, 1.0, 2.0, 3.0],
    "style_param_key": "beta_T",
    "style_param_values": [0.0, 0.1],
}

DEFAULT_RESIDUAL_STUDY = {
    "use_enabled_nanofluids": True,
}


def get_config_payload() -> dict:
    return {
        "components": deepcopy(DEFAULT_COMPONENTS),
        "base_params": deepcopy(DEFAULT_BASE_PARAMS),
        "nanofluids": deepcopy(DEFAULT_NANOFLUIDS),
        "parameter_catalog": deepcopy(PARAMETER_CATALOG),
        "quantity_catalog": deepcopy(QUANTITY_CATALOG),
        "profile_catalog": deepcopy(PROFILE_CATALOG),
        "default_pair_study": deepcopy(DEFAULT_PAIR_STUDY),
        "default_profile_study": deepcopy(DEFAULT_PROFILE_STUDY),
        "default_residual_study": deepcopy(DEFAULT_RESIDUAL_STUDY),
    }
