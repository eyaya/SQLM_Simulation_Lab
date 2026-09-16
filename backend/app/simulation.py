from __future__ import annotations

import contextlib
import io
import math
import re
import time
import unicodedata
import warnings
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib import colors as mcolors
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .schemas import (
    NanofluidPayload,
    PairStudyRequest,
    PairStudyResponse,
    ProfileStudyRequest,
    ProfileStudyResponse,
    ResidualNanofluidStudy,
    ResidualStudyRequest,
    ResidualStudyResponse,
)
from .nanofluids import FluidProperties, HybridNanofluid
from .solver import SQLMSolver


PROJECT_ROOT = Path(__file__).resolve().parents[2]

OUTPUT_DIR = PROJECT_ROOT / "ep_results"
OUTPUT_DIR.mkdir(exist_ok=True)

PAIR_SURFACE_COLORS = {
    "MoS2/EG": "#2563eb",
    "Cu/EG": "#dc2626",
    "MoS2-Cu/EG": "#059669",
}
PAIR_CONTOUR_STYLES = {
    "MoS2/EG": {"color": "#ff4d6d", "linestyle": "-"},
    "Cu/EG": {"color": "#f4a261", "linestyle": "--"},
    "MoS2-Cu/EG": {"color": "#9b5cff", "linestyle": "-."},
}
HYBRID_SURFACE_COLORS = ["#1d4ed8", "#16a34a", "#dc2626", "#60a5fa", "#9333ea", "#f59e0b"]
PROFILE_PARAM_COLORS = ["#7f1d1d", "#0f766e", "#ef4444", "#1d4ed8", "#7c3aed", "#ea580c"]
PROFILE_LINE_STYLES = ["-", "--", ":", "-.", (0, (5, 1)), (0, (3, 1, 1, 1))]
PARAMETER_PLOT_LABELS = {
    "A": r"$A$",
    "Bi": r"$Bi$",
    "Bi_m": r"$Bi_m$",
    "Ec": r"$Ec$",
    "K1": r"$K_1$",
    "M": r"$M$",
    "Nb": r"$Nb$",
    "Nt": r"$Nt$",
    "Pr": r"$Pr$",
    "Q": r"$Q$",
    "Rd": r"$Rd$",
    "S": r"$S$",
    "Sc": r"$Sc$",
    "We": r"$We$",
    "beta_C": r"$\beta_C$",
    "beta_T": r"$\beta_T$",
}
QUANTITY_PLOT_LABELS = {
    "skin_friction": r"$\sqrt{Re_x} C_f$",
    "nusselt": r"$\frac{Nu_x}{\sqrt{Re_x}}$",
    "sherwood": r"$\frac{Sh_x}{\sqrt{Re_x}}$",
}
QUANTITY_FILE_TOKENS = {
    "skin_friction": "Cfx",
    "nusselt": "Nux",
    "sherwood": "Shx",
}
PROFILE_PLOT_LABELS = {
    "velocity": r"$f'$",
    "temperature": r"$\theta$",
    "concentration": r"$\phi$",
}
PROFILE_FILE_TOKENS = {
    "velocity": "fprime",
    "temperature": "theta",
    "concentration": "phi",
}
RESIDUAL_CURVE_STYLES = {
    "f": {"label": r"$f$", "color": "#2563eb", "linestyle": "--", "marker": "o"},
    "theta": {"label": r"$\theta$", "color": "#dc2626", "linestyle": "--", "marker": "o"},
    "phi": {"label": r"$\phi$", "color": "#0f8b8d", "linestyle": "--", "marker": "o"},
}
PLOT_THEMES = {
    "light": {
        "figure_face": "#ffffff",
        "axes_face": "#ffffff",
        "text": "#0f172a",
        "edge": "#334155",
        "grid": "#cbd5e1",
        "legend_face": "#ffffff",
        "legend_edge": "#dbe4f0",
        "table_header": "#f8fbff",
        "table_body": "#ffffff",
    },
    "dark": {
        "figure_face": "#111827",
        "axes_face": "#0f172a",
        "text": "#e2e8f0",
        "edge": "#cbd5e1",
        "grid": "#334155",
        "legend_face": "#111827",
        "legend_edge": "#334155",
        "table_header": "#172033",
        "table_body": "#0f172a",
    },
}


def _make_parameter_values(spec: list[float], n_points: int) -> np.ndarray:
    values = np.asarray(spec, dtype=float)
    if values.ndim != 1:
        raise ValueError("Parameter specification must be one-dimensional.")
    if values.size == 2:
        return np.linspace(values[0], values[1], n_points)
    return values


def _make_fluid(payload: dict) -> FluidProperties:
    return FluidProperties(
        rho=payload["rho"],
        mu=payload["mu"],
        k=payload["k"],
        sigma=payload["sigma"],
        Cp=payload["cp"],
        is_base_fluid=payload["is_base_fluid"],
    )


def _build_nanofluids(components: dict, nanofluids: list[NanofluidPayload]) -> list[dict]:
    base_fluid = _make_fluid(components["base_fluid"])
    mos2 = _make_fluid(components["mos2"])
    cu = _make_fluid(components["cu"])

    configured = []
    for item in nanofluids:
        if not item.enabled:
            continue
        configured.append(
            {
                "name": item.name,
                "display_name": item.display_name or item.name,
                "phi1": item.phi1,
                "phi2": item.phi2,
                "model": HybridNanofluid(base_fluid, mos2, cu, item.phi1, item.phi2),
            }
        )
    return configured


def _run_simulation_quiet(params: dict, nanofluid: HybridNanofluid, max_attempts: int = 2):
    for attempt in range(max_attempts):
        trial = params.copy()
        if attempt:
            trial["omega"] = max(0.5, float(trial.get("omega", 1.0)) * (0.8 ** attempt))
            trial["ms"] = int(trial["ms"]) + 10 * attempt

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with contextlib.redirect_stdout(io.StringIO()):
                    solver = SQLMSolver(trial)
                    ratios = nanofluid.compute_ratios()
                    solution = solver.solve(ratios)
            if solution is not None:
                return solution, ratios, trial
        except Exception:
            continue

    return None, nanofluid.compute_ratios(), params.copy()


def _compute_quantities(solution, params: dict, ratios: tuple[float, ...]) -> dict[str, float]:
    (
        _eta,
        _f,
        _fd,
        fdd,
        _fddd,
        _theta,
        thetad,
        _thetadd,
        _phi,
        phid,
        _phidd,
        _res_f,
        _res_theta,
        _res_phi,
    ) = solution

    return {
        "skin_friction": float(ratios[0] * (fdd[0] + (params["We"] / 2.0) * (fdd[0] ** 2))),
        "nusselt": float(-ratios[3] * (1.0 + (4.0 / 3.0) * params["Rd"]) * thetad[0]),
        "sherwood": float(-phid[0]),
    }


def _extract_profile(solution, profile_key: str) -> tuple[np.ndarray, np.ndarray]:
    (
        eta,
        _f,
        fd,
        _fdd,
        _fddd,
        theta,
        _thetad,
        _thetadd,
        phi,
        _phid,
        _phidd,
        _res_f,
        _res_theta,
        _res_phi,
    ) = solution

    if profile_key == "velocity":
        return np.asarray(eta, dtype=float), np.asarray(fd, dtype=float)
    if profile_key == "temperature":
        return np.asarray(eta, dtype=float), np.asarray(theta, dtype=float)
    if profile_key == "concentration":
        return np.asarray(eta, dtype=float), np.asarray(phi, dtype=float)
    raise ValueError(f"Unsupported profile key: {profile_key}")


def _extract_residuals(solution) -> dict[str, np.ndarray]:
    (
        _eta,
        _f,
        _fd,
        _fdd,
        _fddd,
        _theta,
        _thetad,
        _thetadd,
        _phi,
        _phid,
        _phidd,
        res_f,
        res_theta,
        res_phi,
    ) = solution

    return {
        "f": np.asarray(res_f, dtype=float),
        "theta": np.asarray(res_theta, dtype=float),
        "phi": np.asarray(res_phi, dtype=float),
    }


def _serialize_grid(grid: np.ndarray) -> list[list[float | None]]:
    serialized = []
    for row in grid:
        serialized.append(
            [float(value) if math.isfinite(float(value)) else None for value in row]
        )
    return serialized


def _summarize_grid(grid: np.ndarray) -> dict[str, float | int | None]:
    valid = grid[np.isfinite(grid)]
    if valid.size == 0:
        return {"count": 0, "min": None, "max": None, "mean": None}
    return {
        "count": int(valid.size),
        "min": float(np.min(valid)),
        "max": float(np.max(valid)),
        "mean": float(np.mean(valid)),
    }


def _grid_from_serialized(grid: list[list[float | None]]) -> np.ndarray:
    return np.asarray(
        [[np.nan if value is None else float(value) for value in row] for row in grid],
        dtype=float,
    )


def _relative_output_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _slugify_token(value: str) -> str:
    replacements = {
        "φ": "phi",
        "θ": "theta",
        "′": "prime",
        "₂": "2",
        "₁": "1",
        "√": "sqrt",
        "/": "_",
        " ": "_",
    }
    token = value
    for source, target in replacements.items():
        token = token.replace(source, target)
    token = unicodedata.normalize("NFKD", token)
    token = token.encode("ascii", "ignore").decode("ascii")
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", token)
    token = re.sub(r"_+", "_", token).strip("_")
    return token or "figure"


def _value_token(value: float) -> str:
    token = f"{float(value):.3f}".rstrip("0").rstrip(".")
    token = token.replace("-", "m").replace(".", "p")
    return token


def _pair_param_token(meta: dict) -> str:
    return "_".join(sorted([meta["x_param"], meta["y_param"]]))


def _get_plot_theme(theme_mode: str | None) -> dict[str, str]:
    return PLOT_THEMES.get(theme_mode or "light", PLOT_THEMES["light"])


def _style_legend(legend, theme: dict[str, str]) -> None:
    if legend is None:
        return
    frame = legend.get_frame()
    frame.set_facecolor(theme["legend_face"])
    frame.set_edgecolor(theme["legend_edge"])
    for text in legend.get_texts():
        text.set_color(theme["text"])
    if legend.get_title() is not None:
        legend.get_title().set_color(theme["text"])


def _apply_axes_theme(fig, ax, theme: dict[str, str]) -> None:
    fig.patch.set_facecolor(theme["figure_face"])
    if hasattr(ax, "set_facecolor"):
        ax.set_facecolor(theme["axes_face"])
    for spine in getattr(ax, "spines", {}).values():
        spine.set_color(theme["edge"])
    ax.tick_params(colors=theme["text"])
    if getattr(ax, "xaxis", None) is not None and ax.xaxis.label is not None:
        ax.xaxis.label.set_color(theme["text"])
    if getattr(ax, "yaxis", None) is not None and ax.yaxis.label is not None:
        ax.yaxis.label.set_color(theme["text"])
    if hasattr(ax, "zaxis"):
        ax.zaxis.label.set_color(theme["text"])
        ax.zaxis.set_tick_params(colors=theme["text"])
        for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
            if hasattr(axis, "pane"):
                axis.pane.set_facecolor(mcolors.to_rgba(theme["axes_face"], alpha=1.0))
                axis.pane.set_edgecolor(theme["edge"])


def _build_output_path(*parts: str) -> Path:
    stem = "_".join(_slugify_token(part) for part in parts if part)
    return OUTPUT_DIR / f"{stem}.png"


def _detect_hybrid_fraction_study(surfaces: list[dict]) -> str | None:
    if not surfaces:
        return None

    labels = [item["display_name"].lower() for item in surfaces]
    if all("φ1=" in label or "phi1=" in label for label in labels):
        return "phi1"
    if all("φ2=" in label or "phi2=" in label for label in labels):
        return "phi2"
    return None


def _pair_surface_color(surface_name: str, index: int, hybrid_fraction_key: str | None = None) -> str:
    if hybrid_fraction_key:
        return HYBRID_SURFACE_COLORS[index % len(HYBRID_SURFACE_COLORS)]
    return PAIR_SURFACE_COLORS.get(surface_name, "#6b7280")


def _pair_contour_style(surface_name: str, index: int) -> dict[str, str]:
    return PAIR_CONTOUR_STYLES.get(
        surface_name,
        {
            "color": "#6b7280",
            "linestyle": "-",
        },
    )


def _save_pair_surface_figure(meta: dict, surfaces: list[dict]) -> str | None:
    x_values = np.asarray(meta["x_values"], dtype=float)
    y_values = np.asarray(meta["y_values"], dtype=float)
    x_grid, y_grid = np.meshgrid(x_values, y_values)
    hybrid_fraction_key = _detect_hybrid_fraction_study(surfaces)
    theme = _get_plot_theme(meta.get("theme_mode"))

    fig = plt.figure(figsize=(8.5, 6.5))
    ax = fig.add_subplot(111, projection="3d")
    _apply_axes_theme(fig, ax, theme)
    handles = []
    plotted_any = False

    for index, surface in enumerate(surfaces):
        z_grid = _grid_from_serialized(surface["grid"])
        if not np.isfinite(z_grid).any():
            continue
        color = _pair_surface_color(surface["name"], index, hybrid_fraction_key)
        ax.plot_surface(
            x_grid,
            y_grid,
            z_grid,
            color=color,
            alpha=0.78,
            edgecolor="none",
            linewidth=0,
            antialiased=True,
        )
        handles.append(Patch(facecolor=color, edgecolor="none", label=surface["display_name"]))
        plotted_any = True

    if not plotted_any:
        plt.close(fig)
        return None

    ax.set_xlabel(PARAMETER_PLOT_LABELS.get(meta["x_param"], meta["x_param"]), labelpad=10)
    ax.set_ylabel(PARAMETER_PLOT_LABELS.get(meta["y_param"], meta["y_param"]), labelpad=10)
    ax.set_zlabel(QUANTITY_PLOT_LABELS.get(meta["quantity_key"], meta["quantity_key"]), labelpad=10)
    if handles:
        legend = fig.legend(handles=handles, loc="upper right", bbox_to_anchor=(0.98, 0.98))
        _style_legend(legend, theme)
    fig.tight_layout()

    output_path = _build_output_path(
        "comparision",
        _pair_param_token(meta),
        QUANTITY_FILE_TOKENS.get(meta["quantity_key"], meta["quantity_key"]),
    )
    fig.savefig(output_path, bbox_inches="tight", dpi=200)
    plt.close(fig)
    return _relative_output_path(output_path)


def _save_pair_contour_figure(meta: dict, surfaces: list[dict]) -> str | None:
    x_values = np.asarray(meta["x_values"], dtype=float)
    y_values = np.asarray(meta["y_values"], dtype=float)
    x_grid, y_grid = np.meshgrid(x_values, y_values)
    theme = _get_plot_theme(meta.get("theme_mode"))

    fig, ax = plt.subplots(figsize=(8.2, 5.8))
    _apply_axes_theme(fig, ax, theme)
    handles = []
    plotted_any = False

    for index, surface in enumerate(surfaces):
        z_grid = _grid_from_serialized(surface["grid"])
        if not np.isfinite(z_grid).any():
            continue
        style = _pair_contour_style(surface["name"], index)
        contour = ax.contour(
            x_grid,
            y_grid,
            z_grid,
            colors=[style["color"]],
            linestyles=[style["linestyle"]],
            linewidths=2,
        )
        ax.clabel(contour, inline=True, fmt="%.2f", fontsize=8, colors=[style["color"]])
        handles.append(
            Line2D(
                [0],
                [0],
                color=style["color"],
                linestyle=style["linestyle"],
                linewidth=2,
                label=surface["display_name"],
            )
        )
        plotted_any = True

    if not plotted_any:
        plt.close(fig)
        return None

    ax.set_xlabel(PARAMETER_PLOT_LABELS.get(meta["x_param"], meta["x_param"]))
    ax.set_ylabel(PARAMETER_PLOT_LABELS.get(meta["y_param"], meta["y_param"]))
    if handles:
        legend = ax.legend(handles=handles, loc="upper right")
        _style_legend(legend, theme)
    ax.grid(True, alpha=0.2, color=theme["grid"])
    fig.tight_layout()

    output_path = _build_output_path(
        "comparision",
        _pair_param_token(meta),
        QUANTITY_FILE_TOKENS.get(meta["quantity_key"], meta["quantity_key"]),
        "contour",
    )
    fig.savefig(output_path, bbox_inches="tight", dpi=200)
    plt.close(fig)
    return _relative_output_path(output_path)


def _save_hybrid_table_figure(meta: dict, surfaces: list[dict], fraction_key: str) -> str | None:
    if not surfaces:
        return None

    table_rows = []
    for y_index, y_value in enumerate(meta["y_values"]):
        for x_index, x_value in enumerate(meta["x_values"]):
            row = [f"{float(x_value):.3f}", f"{float(y_value):.3f}"]
            for surface in surfaces:
                value = surface["grid"][y_index][x_index]
                row.append("n/a" if value is None else f"{float(value):.5f}")
            table_rows.append(row)

    fig_width = max(8.0, 2.5 + 1.4 * (2 + len(surfaces)))
    fig_height = max(4.0, 1.5 + 0.33 * len(table_rows))
    theme = _get_plot_theme(meta.get("theme_mode"))
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    fig.patch.set_facecolor(theme["figure_face"])
    ax.axis("off")

    table = ax.table(
        cellText=table_rows,
        colLabels=[
            meta["x_param"],
            meta["y_param"],
            *[surface["display_name"] for surface in surfaces],
        ],
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1.0, 1.18)
    for (row, _col), cell in table.get_celld().items():
        cell.set_edgecolor(theme["legend_edge"])
        cell.set_facecolor(theme["table_header"] if row == 0 else theme["table_body"])
        cell.get_text().set_color(theme["text"])
    fig.tight_layout()

    output_path = _build_output_path(
        "table",
        _pair_param_token(meta),
        QUANTITY_FILE_TOKENS.get(meta["quantity_key"], meta["quantity_key"]),
        fraction_key,
    )
    fig.savefig(output_path, bbox_inches="tight", dpi=200)
    plt.close(fig)
    return _relative_output_path(output_path)


def _save_pair_artifacts(meta: dict, surfaces: list[dict]) -> list[str]:
    saved_files = []

    surface_path = _save_pair_surface_figure(meta, surfaces)
    if surface_path:
        saved_files.append(surface_path)

    hybrid_fraction_key = _detect_hybrid_fraction_study(surfaces)
    if hybrid_fraction_key:
        table_path = _save_hybrid_table_figure(meta, surfaces, hybrid_fraction_key)
        if table_path:
            saved_files.append(table_path)
    else:
        contour_path = _save_pair_contour_figure(meta, surfaces)
        if contour_path:
            saved_files.append(contour_path)

    return saved_files


def _save_profile_artifacts(meta: dict, curves: list[dict]) -> list[str]:
    eta_values = np.asarray(meta["eta_values"], dtype=float)
    if eta_values.size == 0:
        return []

    theme = _get_plot_theme(meta.get("theme_mode"))
    x_limit = float(meta.get("x_limit", eta_values[-1]))
    param_index_map = {float(value): index for index, value in enumerate(meta["param_values"])}
    style_index_map = {float(value): index for index, value in enumerate(meta["style_param_values"])}
    grouped: dict[str, dict] = {}

    for curve in curves:
        if not curve["success"] or curve["values"] is None:
            continue
        item = grouped.setdefault(
            curve["name"],
            {
                "display_name": curve["display_name"],
                "curves": [],
            },
        )
        item["curves"].append(curve)

    saved_files: list[str] = []

    for group_name, group_data in grouped.items():
        fig, ax = plt.subplots(figsize=(7.4, 4.8))
        _apply_axes_theme(fig, ax, theme)
        param_handles = []
        seen_param_values: set[float] = set()

        for curve in sorted(
            group_data["curves"],
            key=lambda item: (
                param_index_map.get(float(item["param_value"]), 0),
                style_index_map.get(float(item["style_param_value"]), 0)
                if item["style_param_value"] is not None
                else 0,
            ),
        ):
            param_value = float(curve["param_value"])
            color = PROFILE_PARAM_COLORS[param_index_map.get(param_value, 0) % len(PROFILE_PARAM_COLORS)]
            style_index = (
                style_index_map.get(float(curve["style_param_value"]), 0)
                if curve["style_param_value"] is not None
                else 0
            )
            line_style = PROFILE_LINE_STYLES[style_index % len(PROFILE_LINE_STYLES)]
            ax.plot(
                eta_values,
                np.asarray(curve["values"], dtype=float),
                color=color,
                linestyle=line_style,
                linewidth=2,
            )
            if param_value not in seen_param_values:
                param_handles.append(
                    Line2D(
                        [0],
                        [0],
                        color=color,
                        linestyle="-",
                        linewidth=2,
                        label=f"{meta['param_key']}={param_value:g}",
                    )
                )
                seen_param_values.add(param_value)

        param_legend = ax.legend(handles=param_handles, loc="upper right")
        _style_legend(param_legend, theme)
        if meta["style_param_key"] and meta["style_param_values"]:
            style_handles = []
            for value in meta["style_param_values"]:
                style_index = style_index_map.get(float(value), 0)
                style_handles.append(
                    Line2D(
                        [0],
                        [0],
                        color=theme["text"],
                        linestyle=PROFILE_LINE_STYLES[style_index % len(PROFILE_LINE_STYLES)],
                        linewidth=2,
                        label=f"{meta['style_param_key']}={float(value):g}",
                    )
                )
            ax.add_artist(param_legend)
            style_legend = ax.legend(handles=style_handles, loc="lower left")
            _style_legend(style_legend, theme)

        ax.set_xlabel(r"$\eta$")
        ax.set_ylabel(PROFILE_PLOT_LABELS.get(meta["profile_key"], meta["profile_key"]))
        ax.set_xlim(0.0, x_limit)
        ax.grid(True, alpha=0.2, color=theme["grid"])
        fig.tight_layout()

        output_path = _build_output_path(
            PROFILE_FILE_TOKENS.get(meta["profile_key"], meta["profile_key"]),
            group_data["display_name"],
            meta["param_key"],
        )
        fig.savefig(output_path, bbox_inches="tight", dpi=200)
        plt.close(fig)
        saved_files.append(_relative_output_path(output_path))

    if len(grouped) > 1 and meta["param_values"]:
        comparison_value = sorted(float(value) for value in meta["param_values"])[
            (len(meta["param_values"]) - 1) // 2
        ]
        fig, ax = plt.subplots(figsize=(7.4, 4.8))
        _apply_axes_theme(fig, ax, theme)
        fluid_handles = []

        for curve in curves:
            if (
                not curve["success"]
                or curve["values"] is None
                or float(curve["param_value"]) != comparison_value
            ):
                continue

            color = PAIR_SURFACE_COLORS.get(curve["name"], "#2563eb")
            style_index = (
                style_index_map.get(float(curve["style_param_value"]), 0)
                if curve["style_param_value"] is not None
                else 0
            )
            ax.plot(
                eta_values,
                np.asarray(curve["values"], dtype=float),
                color=color,
                linestyle=PROFILE_LINE_STYLES[style_index % len(PROFILE_LINE_STYLES)],
                linewidth=2,
            )
            if style_index == 0:
                fluid_handles.append(
                    Line2D(
                        [0],
                        [0],
                        color=color,
                        linestyle="-",
                        linewidth=2,
                        label=curve["display_name"],
                    )
                )

        if fluid_handles:
            fluid_legend = ax.legend(handles=fluid_handles, loc="upper right")
            _style_legend(fluid_legend, theme)
            if meta["style_param_key"] and meta["style_param_values"]:
                style_handles = []
                for value in meta["style_param_values"]:
                    style_index = style_index_map.get(float(value), 0)
                    style_handles.append(
                        Line2D(
                            [0],
                            [0],
                            color=theme["text"],
                            linestyle=PROFILE_LINE_STYLES[style_index % len(PROFILE_LINE_STYLES)],
                            linewidth=2,
                            label=f"{meta['style_param_key']}={float(value):g}",
                        )
                    )
                ax.add_artist(fluid_legend)
                style_legend = ax.legend(handles=style_handles, loc="lower left")
                _style_legend(style_legend, theme)

            ax.set_xlabel(r"$\eta$")
            ax.set_ylabel(PROFILE_PLOT_LABELS.get(meta["profile_key"], meta["profile_key"]))
            ax.set_xlim(0.0, x_limit)
            ax.grid(True, alpha=0.2, color=theme["grid"])
            fig.tight_layout()

            output_path = _build_output_path(
                PROFILE_FILE_TOKENS.get(meta["profile_key"], meta["profile_key"]),
                "comparision",
                meta["param_key"],
                _value_token(comparison_value),
            )
            fig.savefig(output_path, bbox_inches="tight", dpi=200)
            plt.close(fig)
            saved_files.append(_relative_output_path(output_path))
        else:
            plt.close(fig)

    return saved_files


def _save_residual_artifacts(meta: dict, curves: list[dict]) -> list[str]:
    iterations = np.asarray(meta["iterations"], dtype=int)
    if iterations.size == 0:
        return []

    theme = _get_plot_theme(meta.get("theme_mode"))
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    _apply_axes_theme(fig, ax, theme)
    plotted_any = False

    for curve in curves:
        if not curve["values"]:
            continue
        style = RESIDUAL_CURVE_STYLES.get(curve["key"], {"label": curve["label"], "color": "#6b7280"})
        ax.semilogy(
            iterations,
            np.asarray(curve["values"], dtype=float),
            color=style["color"],
            linewidth=2.2,
            label=style["label"],
            linestyle=style.get("linestyle", "--"),
            marker=style.get("marker", "o"),
            markersize=6.5,
        )
        plotted_any = True

    if not plotted_any:
        plt.close(fig)
        return []

    ax.set_xlabel("Iterations")
    ax.set_ylabel("Residuals")
    ax.grid(True, which="both", alpha=0.2, color=theme["grid"])
    legend = ax.legend(loc="upper right")
    _style_legend(legend, theme)
    fig.tight_layout()

    output_path = _build_output_path(
        "residual",
        meta["display_name"],
        f"phi1_{_value_token(meta['phi1'])}",
        f"phi2_{_value_token(meta['phi2'])}",
    )
    fig.savefig(output_path, bbox_inches="tight", dpi=200)
    plt.close(fig)

    return [_relative_output_path(output_path)]


def run_pair_study(request: PairStudyRequest) -> PairStudyResponse:
    configured_nanofluids = _build_nanofluids(
        request.components.model_dump(), request.nanofluids
    )
    x_values = _make_parameter_values(request.x_spec, request.n_points)
    y_values = _make_parameter_values(request.y_spec, request.n_points)
    x_grid, y_grid = np.meshgrid(x_values, y_values)

    surfaces = []
    total_runs = len(configured_nanofluids) * len(x_values) * len(y_values)
    successful_runs = 0
    started = time.perf_counter()

    for item in configured_nanofluids:
        z_grid = np.full(x_grid.shape, np.nan, dtype=float)
        for y_index, y_value in enumerate(y_values):
            for x_index, x_value in enumerate(x_values):
                params = dict(request.base_params)
                params[request.x_param] = float(x_value)
                params[request.y_param] = float(y_value)
                solution, ratios, used_params = _run_simulation_quiet(params, item["model"])
                if solution is None:
                    continue
                successful_runs += 1
                quantities = _compute_quantities(solution, used_params, ratios)
                z_grid[y_index, x_index] = quantities[request.quantity_key]

        surfaces.append(
            {
                "name": item["name"],
                "display_name": item["display_name"],
                "phi1": item["phi1"],
                "phi2": item["phi2"],
                "grid": _serialize_grid(z_grid),
                "summary": _summarize_grid(z_grid),
            }
        )

    elapsed_seconds = time.perf_counter() - started
    meta = {
        "quantity_key": request.quantity_key,
        "x_param": request.x_param,
        "x_values": [float(value) for value in x_values],
        "y_param": request.y_param,
        "y_values": [float(value) for value in y_values],
        "n_points": request.n_points,
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "failed_runs": total_runs - successful_runs,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "theme_mode": request.theme_mode,
    }
    meta["saved_files"] = _save_pair_artifacts(meta, surfaces)

    return PairStudyResponse(
        meta=meta,
        surfaces=surfaces,
    )


def run_profile_study(request: ProfileStudyRequest) -> ProfileStudyResponse:
    configured_nanofluids = _build_nanofluids(
        request.components.model_dump(), request.nanofluids
    )
    style_values = (
        sorted(float(value) for value in request.style_param_values)
        if request.style_param_values
        else [None]
    )
    total_runs = len(configured_nanofluids) * len(request.param_values) * len(style_values)
    successful_runs = 0
    eta_values: list[float] = []
    curves = []
    started = time.perf_counter()

    for item in configured_nanofluids:
        for param_value in request.param_values:
            for style_value in style_values:
                params = dict(request.base_params)
                params[request.param_key] = float(param_value)
                if request.style_param_key is not None and style_value is not None:
                    params[request.style_param_key] = float(style_value)
                solution, _ratios, _used_params = _run_simulation_quiet(params, item["model"])

                if solution is None:
                    curves.append(
                        {
                            "name": item["name"],
                            "display_name": item["display_name"],
                            "phi1": item["phi1"],
                            "phi2": item["phi2"],
                            "param_value": float(param_value),
                            "style_param_value": style_value,
                            "success": False,
                            "values": None,
                        }
                    )
                    continue

                eta, profile_values = _extract_profile(solution, request.profile_key)
                successful_runs += 1
                if not eta_values:
                    eta_values = [float(value) for value in eta]

                curves.append(
                    {
                        "name": item["name"],
                        "display_name": item["display_name"],
                        "phi1": item["phi1"],
                        "phi2": item["phi2"],
                        "param_value": float(param_value),
                        "style_param_value": style_value,
                        "success": True,
                        "values": [float(value) for value in profile_values],
                    }
                )

    elapsed_seconds = time.perf_counter() - started
    meta = {
        "profile_key": request.profile_key,
        "param_key": request.param_key,
        "param_values": [float(value) for value in request.param_values],
        "style_param_key": request.style_param_key,
        "style_param_values": [value for value in style_values if value is not None],
        "eta_values": eta_values,
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "failed_runs": total_runs - successful_runs,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "theme_mode": request.theme_mode,
        "x_limit": float(request.base_params.get("L", eta_values[-1] if eta_values else 0.0)),
    }
    meta["saved_files"] = _save_profile_artifacts(meta, curves)

    return ProfileStudyResponse(
        meta=meta,
        curves=curves,
    )


def run_residual_study(request: ResidualStudyRequest) -> ResidualStudyResponse:
    configured_nanofluids = _build_nanofluids(
        request.components.model_dump(), request.nanofluids
    )
    started = time.perf_counter()
    successful_runs = 0
    studies: list[dict] = []
    saved_files: list[str] = []

    for item in configured_nanofluids:
        item_started = time.perf_counter()
        solution, _ratios, _used_params = _run_simulation_quiet(
            dict(request.base_params),
            item["model"],
        )
        item_elapsed_seconds = time.perf_counter() - item_started

        if solution is None:
            studies.append(
                {
                    "name": item["name"],
                    "display_name": item["display_name"],
                    "phi1": item["phi1"],
                    "phi2": item["phi2"],
                    "success": False,
                    "iterations": [],
                    "total_iterations": 0,
                    "elapsed_seconds": round(item_elapsed_seconds, 3),
                    "curves": [],
                    "saved_files": [],
                }
            )
            continue

        residuals = _extract_residuals(solution)
        total_iterations = max((len(values) for values in residuals.values()), default=0)
        iterations = list(range(2, 2 + total_iterations))
        curves = []
        for key in ("f", "theta", "phi"):
            values = residuals[key]
            curves.append(
                {
                    "key": key,
                    "label": RESIDUAL_CURVE_STYLES[key]["label"],
                    "values": [float(value) for value in values],
                }
            )

        study = {
            "name": item["name"],
            "display_name": item["display_name"],
            "phi1": item["phi1"],
            "phi2": item["phi2"],
            "success": True,
            "iterations": iterations,
            "total_iterations": total_iterations,
            "elapsed_seconds": round(item_elapsed_seconds, 3),
            "curves": curves,
            "theme_mode": request.theme_mode,
        }
        study["saved_files"] = _save_residual_artifacts(study, curves)
        saved_files.extend(study["saved_files"])
        successful_runs += 1
        studies.append(study)

    elapsed_seconds = time.perf_counter() - started
    meta = {
        "total_runs": len(configured_nanofluids),
        "successful_runs": successful_runs,
        "failed_runs": len(configured_nanofluids) - successful_runs,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "saved_files": saved_files,
    }

    return ResidualStudyResponse(
        meta=meta,
        studies=[ResidualNanofluidStudy(**study) for study in studies],
    )
