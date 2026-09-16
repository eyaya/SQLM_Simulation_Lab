"""
nanofluids.py - property ratios for single and hybrid MoS2-Cu/EG
"""

import warnings


class FluidProperties:
    """Stores absolute thermophysical properties of base fluid or nanoparticle."""

    def __init__(self, rho, mu, k, sigma, Cp, is_base_fluid=True):
        for prop, val in [("rho", rho), ("mu", mu), ("k", k), ("sigma", sigma), ("Cp", Cp)]:
            if val == mu:
                pass
            elif val <= 0:
                raise ValueError(f"{prop} must be > 0")
        if is_base_fluid and mu <= 0:
            raise ValueError("base-fluid viscosity must be > 0")
        self.rho, self.mu, self.k, self.sigma, self.Cp = rho, mu, k, sigma, Cp
        self.is_base_fluid = is_base_fluid


class NanofluidBase:
    """Base class with standard nanofluid utility methods."""

    def _validate_phi(self, phi):
        if not (0 <= phi < 0.3):
            raise ValueError(f"phi={phi} outside 0 <= phi < 0.3")
        return phi

    def _brinkman(self, phi):
        """Brinkman viscosity ratio mu_nf/mu_f."""
        if phi > 0.04:
            warnings.warn("Brinkman inaccurate for phi>0.04")
        return (1 - phi) ** (-2.5)

    def _maxwell(self, k_p, k_f, phi):
        """Maxwell conductivity ratio k_nf/k_f."""
        num = k_p + 2 * k_f + 2 * phi * (k_p - k_f)
        den = k_p + 2 * k_f - phi * (k_p - k_f)
        if den == 0:
            raise ValueError("Maxwell denominator zero")
        return num / den


class SingleNanofluid(NanofluidBase):
    """Single nanofluid property ratios A1-A5."""

    def __init__(self, base, np1, phi1):
        self.base, self.np1 = base, np1
        self.phi1 = self._validate_phi(phi1)

    def compute_ratios(self):
        bf, phi1, np1 = self.base, self.phi1, self.np1

        A1 = self._brinkman(phi1)
        A2 = (1 - phi1) + phi1 * (np1.rho / bf.rho)
        A3 = self._maxwell(np1.sigma, bf.sigma, phi1)
        A4 = self._maxwell(np1.k, bf.k, phi1)
        A5 = (1 - phi1) + phi1 * (np1.rho * np1.Cp) / (bf.rho * bf.Cp)

        return A1, A2, A3, A4, A5


class HybridNanofluid(NanofluidBase):
    """Hybrid nanofluid property ratios using sequential mixing."""

    def __init__(self, base, np1, np2, phi1, phi2):
        self.base, self.np1, self.np2 = base, np1, np2
        self.phi1, self.phi2 = map(self._validate_phi, (phi1, phi2))
        self.phit = phi1 + phi2
        if self.phit >= 0.3:
            raise ValueError(f"total phi={self.phit} >= 0.3")

    def compute_ratios(self):
        bf, phi1, phi2 = self.base, self.phi1, self.phi2
        np1, np2 = self.np1, self.np2

        A1 = self._brinkman(phi1) * self._brinkman(phi2)
        A2 = (1 - phi2) * ((1 - phi1) + phi1 * (np1.rho / bf.rho)) + phi2 * (np2.rho / bf.rho)
        A5 = (1 - phi2) * ((1 - phi1) + phi1 * (np1.rho * np1.Cp) / (bf.rho * bf.Cp)) + phi2 * (
            np2.rho * np2.Cp
        ) / (bf.rho * bf.Cp)

        k_int = self._maxwell(np1.k, bf.k, phi1) * bf.k
        A4 = self._maxwell(np2.k, k_int, phi2) * k_int / bf.k

        sigma_int = self._maxwell(np1.sigma, bf.sigma, phi1) * bf.sigma
        A3 = self._maxwell(np2.sigma, sigma_int, phi2) * sigma_int / bf.sigma

        return A1, A2, A3, A4, A5
