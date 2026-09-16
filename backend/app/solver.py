"""
solver.py - SQLM solver for Williamson hybrid nanofluid
with dual-phase thermal and solutal relaxation (Cattaneo-Christov flux)
"""

import numpy as np
import scipy.linalg as la
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import spsolve


def chebyshev_collocation(N, L=12):
    """Compute Chebyshev collocation points and differentiation matrices."""
    if N == 0:
        return np.array([1.0]), csc_matrix(0.0)

    n = np.arange(N + 1)
    x = np.cos(np.pi * n / N)
    c = np.ones(N + 1)
    c[0], c[-1] = 2.0, 2.0
    c *= (-1) ** n
    X = np.outer(x, np.ones(N + 1))
    dX = X - X.T
    D = np.outer(c, 1.0 / c) / (dX + np.eye(N + 1))
    D -= np.diag(np.sum(D, axis=1))

    D = csc_matrix(-D * (2 / L))
    D2 = D @ D
    D3 = D2 @ D
    eta = L * (1 - x) / 2

    return eta, D.toarray(), D2.toarray(), D3.toarray()


class SQLMSolver:
    def __init__(self, params):
        self.N = params["N"]
        self.N_total = self.N + 1
        self.ms = params["ms"]
        self.tol = params["tol"]
        self.params = params
        self.omega = params.get("omega", 0.6)
        self.convergence_type = params.get("convergence_type", "l2")

        self.eta, self.D, self.D2, self.D3 = chebyshev_collocation(self.N, params["L"])
        self.initialize_arrays()

    def initialize_arrays(self):
        total_size = 3 * self.N_total
        self.u = np.zeros((self.ms, total_size))
        self.ud = np.zeros((self.ms, total_size))
        self.udd = np.zeros((self.ms, total_size))
        self.uddd = np.zeros((self.ms, total_size))

    def initialize_guess(self, A_ratios):
        A1, A2, A3, A4, A5 = A_ratios
        p = self.params
        eta = self.eta

        Bi_T = p["Bi"]
        f0 = p["S"] + p["A"] * eta + (1 - p["A"]) * (1 - np.exp(-eta))
        theta0 = (Bi_T / (Bi_T + A4)) * np.exp(-eta)
        phi0 = np.exp(-eta)

        self.u[0, : self.N_total] = f0
        self.u[0, self.N_total : 2 * self.N_total] = theta0
        self.u[0, 2 * self.N_total :] = phi0

        self.update_derivatives(0)

    def update_derivatives(self, r):
        N = self.N_total
        u = self.u[r]

        f_slice = slice(0, N)
        theta_slice = slice(N, 2 * N)
        phi_slice = slice(2 * N, 3 * N)

        self.ud[r, f_slice] = self.D @ u[f_slice]
        self.udd[r, f_slice] = self.D2 @ u[f_slice]
        self.uddd[r, f_slice] = self.D3 @ u[f_slice]

        self.ud[r, theta_slice] = self.D @ u[theta_slice]
        self.udd[r, theta_slice] = self.D2 @ u[theta_slice]

        self.ud[r, phi_slice] = self.D @ u[phi_slice]
        self.udd[r, phi_slice] = self.D2 @ u[phi_slice]

    def compute_coefficients(self, r, A_ratios):
        A1, A2, A3, A4, A5 = A_ratios
        p = self.params
        N = self.N_total

        f = self.u[r, :N]
        theta = self.u[r, N : 2 * N]
        phi = self.u[r, 2 * N :]

        fd = self.ud[r, :N]
        fdd = self.udd[r, :N]
        fddd = self.uddd[r, :N]
        thetad = self.ud[r, N : 2 * N]
        thetadd = self.udd[r, N : 2 * N]
        phid = self.ud[r, 2 * N :]
        phidd = self.udd[r, 2 * N :]

        f = np.clip(f, -100, 100)
        fd = np.clip(fd, -50, 50)
        fdd = np.clip(fdd, -100, 100)
        fddd = np.clip(fddd, -500, 500)
        theta = np.clip(theta, -10, 10)
        thetad = np.clip(thetad, -10, 10)
        phi = np.clip(phi, -5, 5)
        phid = np.clip(phid, -10, 10)
        phidd = np.clip(phidd, -50, 50)

        eps = 1e-12
        Nb = max(p["Nb"], eps)
        Nt = max(p["Nt"], eps)
        We = max(p["We"], eps)
        Sc = max(p["Sc"], eps)

        a1 = (A1 / A2) * (1 + We * fdd)
        a2 = (A1 / A2) * We * fddd + f
        a3 = -(2 * fd + (A3 / A2) * p["M"]) * np.ones_like(f)
        a4 = fdd
        a5 = (A1 / A2) * We * fdd * fddd + f * fdd - fd**2 - p["A"]**2 - (A3 / A2) * p["M"] * p["A"]

        b1 = 2 * p["Pr"] * A1 * p["Ec"] * fdd + (3 / 2) * A1 * p["Pr"] * p["Ec"] * We * (fdd**2)
        b2 = -A5 * p["Pr"] * p["beta_T"] * f * thetad + 2 * A3 * p["Pr"] * p["M"] * p["Ec"] * (fd - p["A"])
        b3 = A5 * p["Pr"] * thetad - A5 * p["Pr"] * p["beta_T"] * fd * thetad - 2 * A5 * p["Pr"] * p["beta_T"] * f * thetadd
        b4 = (A4 + (4.0 / 3.0) * p["Rd"]) - A5 * p["Pr"] * p["beta_T"] * f**2
        b5 = A5 * p["Pr"] * f - A5 * p["Pr"] * p["beta_T"] * f * fd + A5 * p["Pr"] * Nb * phid + 2 * A5 * p["Pr"] * Nt * thetad
        b6 = p["Pr"] * p["Q"] * np.ones_like(f)
        b7 = A5 * p["Pr"] * Nb * thetad
        b8 = (
            -2 * A5 * p["Pr"] * p["beta_T"] * f**2 * thetadd
            + A5 * p["Pr"] * f * thetad
            - 2 * A5 * p["Pr"] * p["beta_T"] * f * fd * thetad
            + A5 * p["Pr"] * Nb * phid * thetad
            + A5 * p["Pr"] * Nt * (thetad**2)
            + A1 * p["Pr"] * p["Ec"] * (fdd**2)
            + A1 * p["Pr"] * p["Ec"] * We * (fdd**3)
            + A3 * p["M"] * p["Ec"] * (fd**2 - p["A"]**2)
        )

        c1 = -p["Sc"] * p["beta_C"] * f * phid
        c2 = p["Sc"] * phid - p["Sc"] * p["beta_C"] * fd * phid - 2 * p["Sc"] * p["beta_C"] * f * phidd
        c3 = (Nt / Nb) * np.ones_like(f)
        c4 = 1.0 * np.ones_like(f) - p["Sc"] * p["beta_C"] * f**2
        c5 = p["Sc"] * f - p["Sc"] * p["beta_C"] * f * fd
        c6 = -p["Sc"] * p["K1"] * np.ones_like(f)
        c7 = p["Sc"] * f * phid - 2 * p["Sc"] * p["beta_C"] * f**2 * phidd - 2 * p["Sc"] * p["beta_C"] * f * fd * phid

        return (
            (a1, a2, a3, a4, a5),
            (b1, b2, b3, b4, b5, b6, b7, b8),
            (c1, c2, c3, c4, c5, c6, c7),
        )

    def assemble_system(self, coefficients, A_ratios):
        A1, A2, A3, A4, A5 = A_ratios
        p = self.params
        N = self.N_total

        (a1, a2, a3, a4, a5), (b1, b2, b3, b4, b5, b6, b7, b8), (c1, c2, c3, c4, c5, c6, c7) = coefficients

        Lambda11 = np.dot(np.diag(a1), self.D3) + np.dot(np.diag(a2), self.D2) + np.dot(np.diag(a3), self.D) + np.diag(a4)
        Lambda12 = np.zeros((N, N))
        Lambda13 = np.zeros((N, N))
        R1 = a5

        Lambda21 = np.dot(np.diag(b1), self.D2) + np.dot(np.diag(b2), self.D) + np.diag(b3)
        Lambda22 = np.dot(np.diag(b4), self.D2) + np.dot(np.diag(b5), self.D) + np.diag(b6)
        Lambda23 = np.dot(np.diag(b7), self.D)
        R2 = b8

        Lambda31 = np.dot(np.diag(c1), self.D) + np.diag(c2)
        Lambda32 = np.dot(np.diag(c3), self.D2)
        Lambda33 = np.dot(np.diag(c4), self.D2) + np.dot(np.diag(c5), self.D) + np.diag(c6)
        R3 = c7

        Lambda11[0, :] = 0
        Lambda11[0, 0] = 1
        Lambda12[0, :] = 0
        Lambda13[0, :] = 0
        R1[0] = p["S"]

        Lambda11[1, :] = 0
        Lambda11[1, :] = self.D[1, :]
        Lambda12[1, :] = 0
        Lambda13[1, :] = 0
        R1[1] = 1

        Lambda11[-1, :] = 0
        Lambda11[-1, :] = self.D[-1, :]
        Lambda12[-1, :] = 0
        Lambda13[-1, :] = 0
        R1[-1] = p["A"]

        fac_T = p["Bi"] / A4
        Lambda22[0, :] = 0.0
        Lambda22[0, :] = self.D[0, :]
        Lambda22[0, 0] -= fac_T
        Lambda21[0, :] = 0.0
        Lambda23[0, :] = 0.0
        R2[0] = -fac_T

        Lambda22[-1, :] = 0
        Lambda22[-1, -1] = 1
        Lambda21[-1, :] = 0
        Lambda23[-1, :] = 0
        R2[-1] = 0

        Lambda33[0, :] = 0
        Lambda33[0, 0] = 1
        Lambda31[0, :] = 0
        Lambda32[0, :] = 0
        R3[0] = 1

        Lambda33[-1, :] = 0
        Lambda33[-1, -1] = 1
        Lambda31[-1, :] = 0
        Lambda32[-1, :] = 0
        R3[-1] = 0

        AA = np.vstack(
            [
                np.hstack([Lambda11, Lambda12, Lambda13]),
                np.hstack([Lambda21, Lambda22, Lambda23]),
                np.hstack([Lambda31, Lambda32, Lambda33]),
            ]
        )
        R = np.hstack([R1, R2, R3])

        return AA, R

    def solve(self, A_ratios):
        self.initialize_guess(A_ratios)
        N = self.N_total
        Resf, Res_theta, Res_phi = [], [], []

        for r in range(self.ms - 1):
            try:
                coeffs = self.compute_coefficients(r, A_ratios)
                A_mat, R = self.assemble_system(coeffs, A_ratios)

                Acsc = csc_matrix(A_mat)
                sol = spsolve(Acsc, R)

                self.u[r + 1] = self.omega * sol + (1 - self.omega) * self.u[r]
                self.update_derivatives(r + 1)

                if np.any(np.isnan(self.u[r + 1])):
                    print(f"    NaN detected at iteration {r + 1}. Stopping.")
                    break

                if r > 0:
                    u_new, u_prev = self.u[r + 1], self.u[r]
                    f_res = np.max(np.abs(u_new[:N] - u_prev[:N]))
                    theta_res = np.max(np.abs(u_new[N : 2 * N] - u_prev[N : 2 * N]))
                    phi_res = np.max(np.abs(u_new[2 * N :] - u_prev[2 * N :]))

                    Resf.append(f_res)
                    Res_theta.append(theta_res)
                    Res_phi.append(phi_res)

                    residual = (
                        np.sqrt(f_res**2 + theta_res**2 + phi_res**2)
                        if self.convergence_type == "l2"
                        else np.max([f_res, theta_res, phi_res])
                    )

                    if residual < self.tol and not self.params["res"]:
                        break

                if r % 5 == 0:
                    theta = self.u[r + 1, N : 2 * N]
                    current_res = residual if r > 0 else np.inf
                    print(
                        f"    Iter {r + 1}: theta(0)={theta[0]:.4f}, "
                        f"max(theta)={np.max(theta):.4f}, residual={current_res:.2e}"
                    )

            except Exception as e:
                print(f"    Error at iteration {r + 1}: {str(e)}")
                import traceback

                traceback.print_exc()
                break

        r_final = min(r + 1, self.ms - 1)

        return (
            self.eta,
            self.u[r_final, :N],
            self.ud[r_final, :N],
            self.udd[r_final, :N],
            self.uddd[r_final, :N],
            self.u[r_final, N : 2 * N],
            self.ud[r_final, N : 2 * N],
            self.udd[r_final, N : 2 * N],
            self.u[r_final, 2 * N :],
            self.ud[r_final, 2 * N :],
            self.udd[r_final, 2 * N :],
            Resf,
            Res_theta,
            Res_phi,
        )

    def compute_stability(self, A_ratios):
        r_final = self.ms - 1
        coeffs = self.compute_coefficients(r_final, A_ratios)
        AA, _ = self.assemble_system(coeffs, A_ratios)

        N = self.N_total
        D = self.D
        I = np.eye(N)

        B = np.zeros((3 * N, 3 * N))
        B[0:N, 0:N] = D
        B[N : 2 * N, N : 2 * N] = I
        B[2 * N : 3 * N, 2 * N : 3 * N] = I

        bc_rows = [0, 1, N - 1, N, 2 * N - 1, 2 * N, 3 * N - 1]
        for row in bc_rows:
            B[row, :] = 0

        try:
            eig_values = la.eigvals(AA, B)
            real_eigs = [ev.real for ev in eig_values if abs(ev.imag) < 1e-8 and np.isfinite(ev)]
            min_gamma = min(real_eigs) if real_eigs else np.nan
        except Exception as e:
            print(f"Stability computation failed: {str(e)}")
            min_gamma = np.nan

        return min_gamma
