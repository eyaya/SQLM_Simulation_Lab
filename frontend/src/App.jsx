import { useEffect, useMemo, useRef, useState } from 'react'
import Plotly from 'plotly.js-dist-min'
import { fetchConfig, runPairStudy, runProfileStudy, runResidualStudy } from './api'
import './App.css'

const SURFACE_COLORS = {
  'MoS2/EG': '#2563eb',
  'Cu/EG': '#dc2626',
  'MoS2-Cu/EG': '#059669',
}

const CONTOUR_STYLES = {
  'MoS2/EG': { color: '#ff4d6d', dash: 'solid' },
  'Cu/EG': { color: '#f4a261', dash: 'dash' },
  'MoS2-Cu/EG': { color: '#9b5cff', dash: 'dashdot' },
}

const HYBRID_SURFACE_COLORS = ['#1d4ed8', '#16a34a', '#dc2626', '#60a5fa', '#9333ea', '#f59e0b']
const PROFILE_PARAM_COLORS = ['#7f1d1d', '#0f766e', '#ef4444', '#1d4ed8', '#7c3aed', '#ea580c']
const PROFILE_LINE_STYLES = ['solid', 'dash', 'dot', 'dashdot', 'longdash', 'longdashdot']
const RESIDUAL_CURVE_STYLES = {
  f: { label: 'Momentum residual', symbol: 'f', color: '#2563eb', dash: 'dash' },
  theta: { label: 'Energy residual', symbol: 'θ', color: '#dc2626', dash: 'dash' },
  phi: { label: 'Concentration residual', symbol: 'ϕ', color: '#0f8b8d', dash: 'dash' },
}

const FIELD_LABELS = {
  N: 'Collocation points',
  ms: 'Maximum iterations',
  L: 'Domain size',
  tol: 'Tolerance',
  omega: 'Relaxation factor',
  convergence_type: 'Convergence type',
  res: 'Residual iterations (res)',
  rho: 'Density',
  mu: 'Dynamic viscosity',
  k: 'Thermal conductivity',
  sigma: 'Electrical conductivity',
  cp: 'Specific heat',
  phi1: 'phi1 (MoS2)',
  phi2: 'phi2 (Cu)',
  display_name: 'Display name',
}

const COMPONENT_LABELS = {
  base_fluid: 'Base fluid',
  mos2: 'MoS2 particle',
  cu: 'Cu particle',
}

const CONVERGENCE_OPTIONS = ['absolute', 'l2']
const TAB_ITEMS = [
  { key: 'overview', label: 'Overview' },
  { key: 'pair', label: 'Engineering Quantities' },
  { key: 'profile', label: 'Profile Studies' },
  { key: 'hybrid', label: 'Hybrid Engineering' },
  { key: 'residual', label: 'Residual Analysis' },
]
const THEME_STORAGE_KEY = 'sqlm-theme'
const PLOT_THEMES = {
  light: {
    paperBg: '#ffffff',
    plotBg: '#ffffff',
    fontColor: '#0f172a',
    axisColor: '#334155',
    gridColor: 'rgba(148, 163, 184, 0.25)',
  },
  dark: {
    paperBg: '#111827',
    plotBg: '#0f172a',
    fontColor: '#e2e8f0',
    axisColor: '#cbd5e1',
    gridColor: 'rgba(148, 163, 184, 0.2)',
  },
}

function getInitialThemeMode() {
  if (typeof window === 'undefined') {
    return 'light'
  }
  return window.localStorage.getItem(THEME_STORAGE_KEY) === 'dark' ? 'dark' : 'light'
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="4.2" />
      <path d="M12 2.5v2.2M12 19.3v2.2M4.7 4.7l1.6 1.6M17.7 17.7l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.7 19.3l1.6-1.6M17.7 6.3l1.6-1.6" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20.2 14.6A8.8 8.8 0 0 1 9.4 3.8a8.9 8.9 0 1 0 10.8 10.8Z" />
    </svg>
  )
}

function numberOrNull(value) {
  if (value === '') {
    return null
  }
  return Number(value)
}

function toConstantSurfaceColor(grid) {
  return grid.map((row) => row.map(() => 1))
}

function parseNumericList(text) {
  return text
    .split(/[\s,]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const value = Number(item)
      if (Number.isNaN(value)) {
        throw new Error(`Invalid parameter value: ${item}`)
      }
      return value
    })
}

function formatParameterLabel(paramKey, value) {
  return `${paramKey}=${value}`
}

function formatHybridFractionLabel(fractionKey, value) {
  const label = fractionKey === 'phi1' ? 'φ1' : 'φ2'
  return `${label}=${Number(value).toFixed(2)}`
}

function getParameterAxisLabel(config, paramKey) {
  const meta = config?.parameter_catalog?.[paramKey]
  if (!meta) {
    return paramKey
  }
  return meta.label ?? paramKey
}

function getQuantityAxisLabel(config, quantityKey) {
  return config?.quantity_catalog?.[quantityKey]?.symbol ?? quantityKey
}

function getProfileAxisLabel(config, profileKey) {
  return config?.profile_catalog?.[profileKey]?.symbol ?? profileKey
}

function getHybridBaseNanofluid(nanofluids) {
  return (
    nanofluids.find((item) => item.name === 'MoS2-Cu/EG') ??
    nanofluids.find((item) => item.phi1 > 0 && item.phi2 > 0) ??
    null
  )
}

function pickComparisonValue(values) {
  if (!values || values.length === 0) {
    return null
  }

  const sortedValues = [...values].sort((left, right) => left - right)
  return sortedValues[Math.floor((sortedValues.length - 1) / 2)]
}

function describeLineStyles(meta) {
  if (!meta.style_param_key || meta.style_param_values.length === 0) {
    return 'Solid lines show the selected sweep curves.'
  }

  return meta.style_param_values
    .map((value, index) => {
      const styleName = index === 0 ? 'solid' : index === 1 ? 'dashed' : PROFILE_LINE_STYLES[index]
      return `${styleName}: ${meta.style_param_key}=${value}`
    })
    .join(' | ')
}

function withAxisTheme(axis, plotTheme) {
  if (!axis) {
    return axis
  }

  return {
    ...axis,
    color: plotTheme.axisColor,
    linecolor: plotTheme.axisColor,
    gridcolor: plotTheme.gridColor,
    zerolinecolor: plotTheme.gridColor,
  }
}

function withSceneAxisTheme(axis, plotTheme) {
  if (!axis) {
    return axis
  }

  return {
    ...axis,
    color: plotTheme.axisColor,
    linecolor: plotTheme.axisColor,
    gridcolor: plotTheme.gridColor,
    zerolinecolor: plotTheme.gridColor,
    backgroundcolor: plotTheme.plotBg,
  }
}

function withPlotTheme(layout, plotTheme) {
  const themedLayout = {
    ...layout,
    paper_bgcolor: plotTheme.paperBg,
    plot_bgcolor: plotTheme.plotBg,
    font: { color: plotTheme.fontColor },
    legend: layout.legend
      ? {
          ...layout.legend,
          bgcolor: plotTheme.paperBg,
          font: { color: plotTheme.fontColor },
          title: layout.legend.title
            ? {
                ...layout.legend.title,
                font: { color: plotTheme.fontColor },
              }
            : layout.legend.title,
        }
      : layout.legend,
  }

  if (layout.xaxis) {
    themedLayout.xaxis = withAxisTheme(layout.xaxis, plotTheme)
  }

  if (layout.yaxis) {
    themedLayout.yaxis = withAxisTheme(layout.yaxis, plotTheme)
  }

  if (layout.scene) {
    themedLayout.scene = {
      ...layout.scene,
      bgcolor: plotTheme.plotBg,
      xaxis: withSceneAxisTheme(layout.scene.xaxis, plotTheme),
      yaxis: withSceneAxisTheme(layout.scene.yaxis, plotTheme),
      zaxis: withSceneAxisTheme(layout.scene.zaxis, plotTheme),
    }
  }

  return themedLayout
}

function PlotlyChart({ data, layout, config, className, height = 520 }) {
  const plotRef = useRef(null)

  useEffect(() => {
    const plotNode = plotRef.current

    if (!plotNode) {
      return undefined
    }

    let cancelled = false

    async function renderPlot() {
      if (cancelled) {
        return
      }

      await Plotly.react(plotNode, data, layout, config)
    }

    renderPlot()

    const handleResize = () => {
      Plotly.Plots.resize(plotNode)
    }

    window.addEventListener('resize', handleResize)

    return () => {
      cancelled = true
      window.removeEventListener('resize', handleResize)
      Plotly.purge(plotNode)
    }
  }, [data, layout, config])

  return (
    <div
      ref={plotRef}
      className={className}
      style={{ width: '100%', height: `${height}px` }}
    />
  )
}

function App() {
  const [activeTab, setActiveTab] = useState('pair')
  const [themeMode, setThemeMode] = useState(getInitialThemeMode)
  const [config, setConfig] = useState(null)
  const [formState, setFormState] = useState(null)
  const [pairResult, setPairResult] = useState(null)
  const [profileResult, setProfileResult] = useState(null)
  const [hybridPairResult, setHybridPairResult] = useState(null)
  const [residualResult, setResidualResult] = useState(null)
  const [loadingConfig, setLoadingConfig] = useState(true)
  const [runningStudy, setRunningStudy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    async function loadConfig() {
      setLoadingConfig(true)
      setError('')
      try {
        const payload = await fetchConfig()
        const hybridPreset = getHybridBaseNanofluid(payload.nanofluids)
        setConfig(payload)
        setFormState({
          components: payload.components,
          base_params: payload.base_params,
          nanofluids: payload.nanofluids,
          pairStudy: {
            quantity_key: payload.default_pair_study.quantity_key,
            x_param: payload.default_pair_study.x_param,
            x_spec: payload.default_pair_study.x_spec,
            y_param: payload.default_pair_study.y_param,
            y_spec: payload.default_pair_study.y_spec,
            n_points: payload.default_pair_study.n_points,
          },
          profileStudy: {
            profile_key: payload.default_profile_study.profile_key,
            param_key: payload.default_profile_study.param_key,
            param_values_text: payload.default_profile_study.param_values.join(', '),
            style_param_key: payload.default_profile_study.style_param_key ?? '',
            style_param_values_text:
              payload.default_profile_study.style_param_values?.join(', ') ?? '',
          },
          hybridStudy: {
            quantity_key: 'skin_friction',
            x_param: 'A',
            x_spec: [0.0, 0.1],
            y_param: 'S',
            y_spec: [0.1, 0.3],
            n_points: 5,
            fraction_key: 'phi2',
            fixed_fraction_value:
              hybridPreset && typeof hybridPreset.phi1 === 'number' ? Number(hybridPreset.phi1) : 0.01,
            fraction_values_text:
              hybridPreset && typeof hybridPreset.phi2 === 'number'
                ? '0.01, 0.02, 0.03, 0.04'
                : '0.01, 0.02, 0.03, 0.04',
          },
          residualStudy: payload.default_residual_study,
        })
      } catch (loadError) {
        setError(loadError.message)
      } finally {
        setLoadingConfig(false)
      }
    }

    loadConfig()
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode
    window.localStorage.setItem(THEME_STORAGE_KEY, themeMode)
  }, [themeMode])

  const quantityOptions = useMemo(
    () => Object.entries(config?.quantity_catalog ?? {}),
    [config],
  )

  const parameterOptions = useMemo(
    () => Object.entries(config?.parameter_catalog ?? {}),
    [config],
  )

  const profileOptions = useMemo(
    () => Object.entries(config?.profile_catalog ?? {}),
    [config],
  )

  const enabledNanofluids = useMemo(
    () => (formState?.nanofluids ?? []).filter((item) => item.enabled),
    [formState],
  )

  const plotTheme = useMemo(() => PLOT_THEMES[themeMode] ?? PLOT_THEMES.light, [themeMode])
  const profileXRange = useMemo(() => {
    const domainSize = Number(formState?.base_params?.L)
    if (!Number.isFinite(domainSize) || domainSize <= 0) {
      return undefined
    }
    return [0, domainSize]
  }, [formState])

  const currentEndpointLabel = useMemo(() => {
    if (activeTab === 'profile') {
      return '/api/studies/profile'
    }
    if (activeTab === 'residual') {
      return '/api/studies/residual'
    }
    if (activeTab === 'overview') {
      return 'Dashboard'
    }
    return '/api/studies/pair'
  }, [activeTab])

  const currentStudyLabel = useMemo(() => {
    if (!formState) {
      return 'Loading study configuration...'
    }
    if (activeTab === 'pair') {
      return `${formState.pairStudy.quantity_key} vs ${formState.pairStudy.x_param}/${formState.pairStudy.y_param}`
    }
    if (activeTab === 'profile') {
      return `${formState.profileStudy.profile_key} vs ${formState.profileStudy.param_key}`
    }
    if (activeTab === 'hybrid') {
      return `${formState.hybridStudy.quantity_key} vs ${formState.hybridStudy.x_param}/${formState.hybridStudy.y_param}`
    }
    if (activeTab === 'residual') {
      return `Residuals for ${enabledNanofluids.length} enabled nanofluids`
    }
    return 'System overview dashboard'
  }, [activeTab, enabledNanofluids.length, formState])

  const surfacePlotData = useMemo(() => {
    if (!pairResult) {
      return []
    }

    return pairResult.surfaces.map((surface) => {
      const color = SURFACE_COLORS[surface.name] ?? '#6b7280'
      return {
        type: 'surface',
        name: surface.display_name,
        showlegend: true,
        x: pairResult.meta.x_values,
        y: pairResult.meta.y_values,
        z: surface.grid,
        surfacecolor: toConstantSurfaceColor(surface.grid),
        cmin: 0,
        cmax: 1,
        colorscale: [
          [0, color],
          [1, color],
        ],
        showscale: false,
        opacity: 0.72,
        hovertemplate:
          `${pairResult.meta.x_param}=%{x}<br>${pairResult.meta.y_param}=%{y}<br>` +
          `${pairResult.meta.quantity_key}=%{z}<extra>${surface.display_name}</extra>`,
      }
    })
  }, [pairResult])

  const contourPlotData = useMemo(() => {
    if (!pairResult) {
      return []
    }

    return pairResult.surfaces.map((surface) => {
      const contourStyle = CONTOUR_STYLES[surface.name] ?? {
        color: SURFACE_COLORS[surface.name] ?? '#6b7280',
        dash: 'solid',
      }
      return {
        type: 'contour',
        name: surface.display_name,
        showlegend: true,
        x: pairResult.meta.x_values,
        y: pairResult.meta.y_values,
        z: surface.grid,
        colorscale: [
          [0, contourStyle.color],
          [1, contourStyle.color],
        ],
        contours: {
          coloring: 'lines',
          showlabels: true,
          labelformat: '.2f',
          labelfont: {
            size: 11,
            color: contourStyle.color,
          },
        },
        line: {
          color: contourStyle.color,
          width: 2,
          dash: contourStyle.dash,
        },
        showscale: false,
        hovertemplate:
          `${pairResult.meta.x_param}=%{x}<br>${pairResult.meta.y_param}=%{y}<br>` +
          `${pairResult.meta.quantity_key}=%{z}<extra>${surface.display_name}</extra>`,
      }
    })
  }, [pairResult])

  const profilePlots = useMemo(() => {
    if (!profileResult) {
      return []
    }

    const paramIndexMap = new Map(
      profileResult.meta.param_values.map((value, index) => [String(value), index]),
    )
    const styleIndexMap = new Map(
      (profileResult.meta.style_param_values ?? []).map((value, index) => [String(value), index]),
    )
    const grouped = new Map()

    profileResult.curves
      .filter((curve) => curve.success && Array.isArray(curve.values))
      .forEach((curve) => {
        const traces = grouped.get(curve.name) ?? {
          name: curve.name,
          display_name: curve.display_name,
          phi1: curve.phi1,
          phi2: curve.phi2,
          traces: [],
        }

        const paramIndex = paramIndexMap.get(String(curve.param_value)) ?? 0
        const styleIndex =
          curve.style_param_value == null
            ? 0
            : styleIndexMap.get(String(curve.style_param_value)) ?? 0

        traces.traces.push({
          type: 'scatter',
          mode: 'lines',
          name: formatParameterLabel(profileResult.meta.param_key, curve.param_value),
          legendgroup: String(curve.param_value),
          showlegend: styleIndex === 0,
          x: profileResult.meta.eta_values,
          y: curve.values,
          line: {
            color: PROFILE_PARAM_COLORS[paramIndex % PROFILE_PARAM_COLORS.length],
            width: 2.5,
            dash: PROFILE_LINE_STYLES[styleIndex % PROFILE_LINE_STYLES.length],
          },
          hovertemplate:
            `eta=%{x}<br>${profileResult.meta.profile_key}=%{y}<br>` +
            `${profileResult.meta.param_key}=${curve.param_value}` +
            (curve.style_param_value == null || !profileResult.meta.style_param_key
              ? ''
              : `<br>${profileResult.meta.style_param_key}=${curve.style_param_value}`) +
            `<extra>${curve.display_name}</extra>`,
        })

        grouped.set(curve.name, traces)
      })

    return Array.from(grouped.values()).map((item) => ({
      ...item,
      traces: item.traces.sort((left, right) => {
        const leftParam = paramIndexMap.get(String(left.legendgroup)) ?? 0
        const rightParam = paramIndexMap.get(String(right.legendgroup)) ?? 0
        if (leftParam !== rightParam) {
          return leftParam - rightParam
        }
        const leftStyle = PROFILE_LINE_STYLES.indexOf(left.line.dash)
        const rightStyle = PROFILE_LINE_STYLES.indexOf(right.line.dash)
        return leftStyle - rightStyle
      }),
    }))
  }, [profileResult])

  const comparisonProfilePlot = useMemo(() => {
    if (!profileResult) {
      return null
    }

    const comparisonValue = pickComparisonValue(profileResult.meta.param_values)
    if (comparisonValue == null) {
      return null
    }

    const styleIndexMap = new Map(
      (profileResult.meta.style_param_values ?? []).map((value, index) => [String(value), index]),
    )

    const traces = profileResult.curves
      .filter(
        (curve) =>
          curve.success &&
          Array.isArray(curve.values) &&
          Number(curve.param_value) === Number(comparisonValue),
      )
      .map((curve) => {
        const styleIndex =
          curve.style_param_value == null
            ? 0
            : styleIndexMap.get(String(curve.style_param_value)) ?? 0

        return {
          type: 'scatter',
          mode: 'lines',
          name: curve.display_name,
          legendgroup: curve.name,
          showlegend: styleIndex === 0,
          x: profileResult.meta.eta_values,
          y: curve.values,
          line: {
            color: SURFACE_COLORS[curve.name] ?? '#6b7280',
            width: 2.5,
            dash: PROFILE_LINE_STYLES[styleIndex % PROFILE_LINE_STYLES.length],
          },
          hovertemplate:
            `eta=%{x}<br>${profileResult.meta.profile_key}=%{y}<br>` +
            `${profileResult.meta.param_key}=${curve.param_value}` +
            (curve.style_param_value == null || !profileResult.meta.style_param_key
              ? ''
              : `<br>${profileResult.meta.style_param_key}=${curve.style_param_value}`) +
            `<extra>${curve.display_name}</extra>`,
        }
      })

    return {
      value: comparisonValue,
      traces,
    }
  }, [profileResult])

  const profileSummary = useMemo(() => {
    if (!profileResult) {
      return []
    }

    const grouped = new Map()
    profileResult.curves.forEach((curve) => {
      const current = grouped.get(curve.name) ?? {
        name: curve.name,
        display_name: curve.display_name,
        phi1: curve.phi1,
        phi2: curve.phi2,
        total: 0,
        success: 0,
      }
      current.total += 1
      current.success += curve.success ? 1 : 0
      grouped.set(curve.name, current)
    })
    return Array.from(grouped.values())
  }, [profileResult])

  const hybridSurfacePlotData = useMemo(() => {
    if (!hybridPairResult) {
      return []
    }

    return hybridPairResult.surfaces.map((surface, index) => {
      const color = HYBRID_SURFACE_COLORS[index % HYBRID_SURFACE_COLORS.length]
      return {
        type: 'surface',
        name: surface.display_name,
        showlegend: true,
        x: hybridPairResult.meta.x_values,
        y: hybridPairResult.meta.y_values,
        z: surface.grid,
        surfacecolor: toConstantSurfaceColor(surface.grid),
        cmin: 0,
        cmax: 1,
        colorscale: [
          [0, color],
          [1, color],
        ],
        showscale: false,
        opacity: 0.76,
        hovertemplate:
          `${hybridPairResult.meta.x_param}=%{x}<br>${hybridPairResult.meta.y_param}=%{y}<br>` +
          `${hybridPairResult.meta.quantity_key}=%{z}<extra>${surface.display_name}</extra>`,
      }
    })
  }, [hybridPairResult])

  const hybridTableRows = useMemo(() => {
    if (!hybridPairResult) {
      return []
    }

    const rows = []
    hybridPairResult.meta.y_values.forEach((yValue, yIndex) => {
      hybridPairResult.meta.x_values.forEach((xValue, xIndex) => {
        rows.push({
          xValue,
          yValue,
          values: hybridPairResult.surfaces.map((surface) => surface.grid[yIndex]?.[xIndex] ?? null),
        })
      })
    })
    return rows
  }, [hybridPairResult])

  const residualPlots = useMemo(() => {
    if (!residualResult) {
      return []
    }

    return residualResult.studies
      .filter((study) => study.success)
      .map((study) => ({
        ...study,
        traces: study.curves.map((curve) => {
          const style = RESIDUAL_CURVE_STYLES[curve.key] ?? {
            label: curve.label,
            symbol: curve.label,
            color: '#6b7280',
            dash: 'dash',
          }
          return {
            type: 'scatter',
            mode: 'lines+markers',
            name: style.symbol,
            x: study.iterations.slice(0, curve.values.length),
            y: curve.values,
            line: {
              color: style.color,
              width: 2.5,
              dash: style.dash,
            },
            marker: {
              color: style.color,
              size: 9,
              symbol: 'circle',
            },
            hovertemplate: `iteration=%{x}<br>residual=%{y:.3e}<extra>${style.label}</extra>`,
          }
        }),
      }))
  }, [residualResult])

  const residualSummary = useMemo(() => {
    if (!residualResult) {
      return []
    }

    return residualResult.studies.map((study) => ({
      key: study.name,
      displayName: study.display_name,
      phi1: study.phi1,
      phi2: study.phi2,
      success: study.success,
      count: study.total_iterations,
    }))
  }, [residualResult])

  const overviewStudyCards = useMemo(
    () => [
      pairResult
        ? {
            key: 'pair',
            label: 'Engineering quantities',
            status: 'available',
            success: pairResult.meta.successful_runs,
            total: pairResult.meta.total_runs,
            elapsed: pairResult.meta.elapsed_seconds,
          }
        : {
            key: 'pair',
            label: 'Engineering quantities',
            status: 'pending',
          },
      profileResult
        ? {
            key: 'profile',
            label: 'Profile studies',
            status: 'available',
            success: profileResult.meta.successful_runs,
            total: profileResult.meta.total_runs,
            elapsed: profileResult.meta.elapsed_seconds,
          }
        : {
            key: 'profile',
            label: 'Profile studies',
            status: 'pending',
          },
      hybridPairResult
        ? {
            key: 'hybrid',
            label: 'Hybrid engineering',
            status: 'available',
            success: hybridPairResult.meta.successful_runs,
            total: hybridPairResult.meta.total_runs,
            elapsed: hybridPairResult.meta.elapsed_seconds,
          }
        : {
            key: 'hybrid',
            label: 'Hybrid engineering',
            status: 'pending',
          },
      residualResult
        ? {
            key: 'residual',
            label: 'Residual analysis',
            status: 'available',
            success: residualResult.meta.successful_runs,
            total: residualResult.meta.total_runs,
            elapsed: residualResult.meta.elapsed_seconds,
          }
        : {
            key: 'residual',
            label: 'Residual analysis',
            status: 'pending',
          },
    ],
    [pairResult, profileResult, hybridPairResult, residualResult],
  )

  const overviewMetrics = useMemo(
    () =>
      overviewStudyCards
        .filter((item) => item.status === 'available')
        .map((item) => ({
          label: item.label,
          success: item.success ?? 0,
          failed: Math.max((item.total ?? 0) - (item.success ?? 0), 0),
          elapsed: item.elapsed ?? 0,
        })),
    [overviewStudyCards],
  )

  const overviewCoverageData = useMemo(() => {
    if (overviewMetrics.length === 0) {
      return []
    }

    return [
      {
        type: 'bar',
        name: 'Successful',
        x: overviewMetrics.map((item) => item.label),
        y: overviewMetrics.map((item) => item.success),
        marker: { color: '#16a34a' },
      },
      {
        type: 'bar',
        name: 'Failed',
        x: overviewMetrics.map((item) => item.label),
        y: overviewMetrics.map((item) => item.failed),
        marker: { color: '#dc2626' },
      },
    ]
  }, [overviewMetrics])

  const overviewTimingData = useMemo(() => {
    if (overviewMetrics.length === 0) {
      return []
    }

    return [
      {
        type: 'bar',
        x: overviewMetrics.map((item) => item.label),
        y: overviewMetrics.map((item) => item.elapsed),
        marker: { color: '#2563eb' },
        name: 'Elapsed (s)',
      },
    ]
  }, [overviewMetrics])

  function updateStudyField(studyKey, field, value) {
    setFormState((current) => ({
      ...current,
      [studyKey]: {
        ...current[studyKey],
        [field]: value,
      },
    }))
  }

  function updatePairSpec(axis, index, value) {
    setFormState((current) => {
      const nextSpec = [...current.pairStudy[axis]]
      nextSpec[index] = Number(value)
      return {
        ...current,
        pairStudy: {
          ...current.pairStudy,
          [axis]: nextSpec,
        },
      }
    })
  }

  function updateHybridSpec(axis, index, value) {
    setFormState((current) => {
      const nextSpec = [...current.hybridStudy[axis]]
      nextSpec[index] = Number(value)
      return {
        ...current,
        hybridStudy: {
          ...current.hybridStudy,
          [axis]: nextSpec,
        },
      }
    })
  }

  function updateHybridFractionKey(value) {
    setFormState((current) => {
      const hybridPreset = getHybridBaseNanofluid(current.nanofluids ?? [])
      const fixedFractionValue =
        value === 'phi1'
          ? Number(hybridPreset?.phi2 ?? current.hybridStudy.fixed_fraction_value ?? 0.03)
          : Number(hybridPreset?.phi1 ?? current.hybridStudy.fixed_fraction_value ?? 0.01)

      return {
        ...current,
        hybridStudy: {
          ...current.hybridStudy,
          fraction_key: value,
          fixed_fraction_value: fixedFractionValue,
        },
      }
    })
  }

  function updateBaseParam(key, value) {
    setFormState((current) => ({
      ...current,
      base_params: {
        ...current.base_params,
        [key]: value,
      },
    }))
  }

  function updateComponent(componentKey, field, value) {
    setFormState((current) => ({
      ...current,
      components: {
        ...current.components,
        [componentKey]: {
          ...current.components[componentKey],
          [field]: value,
        },
      },
    }))
  }

  function updateNanofluid(index, field, value) {
    setFormState((current) => {
      const next = current.nanofluids.map((item, itemIndex) =>
        itemIndex === index ? { ...item, [field]: value } : item,
      )
      return {
        ...current,
        nanofluids: next,
      }
    })
  }

  async function handleRunPairStudy() {
    if (!formState) {
      return
    }

    setRunningStudy(true)
    setError('')

    try {
      const payload = {
        components: formState.components,
        base_params: formState.base_params,
        nanofluids: formState.nanofluids,
        theme_mode: themeMode,
        ...formState.pairStudy,
        n_points: Number(formState.pairStudy.n_points),
      }
      const studyResult = await runPairStudy(payload)
      setPairResult(studyResult)
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setRunningStudy(false)
    }
  }

  async function handleRunProfileStudy() {
    if (!formState) {
      return
    }

    setRunningStudy(true)
    setError('')

    try {
      const paramValues = parseNumericList(formState.profileStudy.param_values_text)
      const styleParamValues = parseNumericList(formState.profileStudy.style_param_values_text).sort(
        (left, right) => left - right,
      )
      const payload = {
        components: formState.components,
        base_params: formState.base_params,
        nanofluids: formState.nanofluids,
        theme_mode: themeMode,
        profile_key: formState.profileStudy.profile_key,
        param_key: formState.profileStudy.param_key,
        param_values: paramValues,
        style_param_key: formState.profileStudy.style_param_key || null,
        style_param_values: styleParamValues,
      }
      const studyResult = await runProfileStudy(payload)
      setProfileResult(studyResult)
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setRunningStudy(false)
    }
  }

  async function handleRunHybridStudy() {
    if (!formState) {
      return
    }

    setRunningStudy(true)
    setError('')

    try {
      const fractionValues = parseNumericList(formState.hybridStudy.fraction_values_text).sort(
        (left, right) => left - right,
      )
      const fractionKey = formState.hybridStudy.fraction_key
      const fixedFractionValue = Number(formState.hybridStudy.fixed_fraction_value)
      const hybridPreset = getHybridBaseNanofluid(formState.nanofluids)

      if (!hybridPreset) {
        throw new Error('A hybrid nanofluid preset with phi1 > 0 and phi2 > 0 is required.')
      }

      const payload = {
        components: formState.components,
        base_params: formState.base_params,
        theme_mode: themeMode,
        nanofluids: fractionValues.map((value, index) => ({
          name: `hybrid-${index}`,
          display_name: formatHybridFractionLabel(fractionKey, value),
          phi1: fractionKey === 'phi1' ? value : fixedFractionValue,
          phi2: fractionKey === 'phi2' ? value : fixedFractionValue,
          enabled: true,
        })),
        quantity_key: formState.hybridStudy.quantity_key,
        x_param: formState.hybridStudy.x_param,
        x_spec: formState.hybridStudy.x_spec,
        y_param: formState.hybridStudy.y_param,
        y_spec: formState.hybridStudy.y_spec,
        n_points: Number(formState.hybridStudy.n_points),
      }

      const studyResult = await runPairStudy(payload)
      setHybridPairResult(studyResult)
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setRunningStudy(false)
    }
  }

  async function handleRunResidualStudy() {
    if (!formState) {
      return
    }

    setRunningStudy(true)
    setError('')

    try {
      const payload = {
        components: formState.components,
        base_params: formState.base_params,
        nanofluids: formState.nanofluids,
        theme_mode: themeMode,
      }
      const studyResult = await runResidualStudy(payload)
      setResidualResult(studyResult)
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setRunningStudy(false)
    }
  }

  if (loadingConfig || !formState) {
    if (!loadingConfig && !formState) {
      return (
        <main className="app-shell">
          <section className="hero-card">
            <div>
              <h1>SQLM Simulation Studio</h1>
              <p className="hero-copy">
                The frontend could not load the backend configuration.
              </p>
              {error ? <div className="error-banner">{error}</div> : null}
            </div>
          </section>
        </main>
      )
    }

    return (
      <main className="app-shell">
        <section className="hero-card">
          <h1>SQLM Simulation Studio</h1>
          <p>Loading solver configuration...</p>
        </section>
      </main>
    )
  }

  return (
    <main className="app-shell">
      <section className="hero-card">
        <div>
          <h1>SQLM Simulation Studio</h1>
          <p className="hero-copy">
            Configure fluid properties, nanofluid presets, solver parameters, and
            pair studies for the Williamson hybrid nanofluid model.
          </p>
        </div>
        <div className="hero-side">
          <button
            className="theme-toggle"
            type="button"
            aria-label={themeMode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
            title={themeMode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
            onClick={() => setThemeMode((current) => (current === 'light' ? 'dark' : 'light'))}
          >
            {themeMode === 'light' ? <MoonIcon /> : <SunIcon />}
          </button>
          <div className="status-grid">
            <div className="status-card">
              <span>View</span>
              <strong>{currentEndpointLabel}</strong>
            </div>
            <div className="status-card">
              <span>Current study</span>
              <strong>{currentStudyLabel}</strong>
            </div>
          </div>
        </div>
      </section>

      {error ? <div className="error-banner">{error}</div> : null}

      <div className="tab-bar">
        {TAB_ITEMS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`tab-button ${activeTab === item.key ? 'active' : ''}`}
            onClick={() => setActiveTab(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className={`workspace-grid ${activeTab === 'overview' ? 'overview-grid' : ''}`}>
        {activeTab !== 'overview' ? (
        <section className="panel">
          <div className="panel-header">
            <h2>
              {activeTab === 'overview'
                ? 'Overview'
                : activeTab === 'pair'
                ? 'Pair variation setup'
                : activeTab === 'profile'
                  ? 'Profile study setup'
                  : activeTab === 'hybrid'
                    ? 'Hybrid engineering setup'
                    : 'Residual analysis setup'}
            </h2>
            {activeTab === 'overview' ? null : activeTab === 'pair' ? (
              <button
                className="primary-button"
                type="button"
                disabled={runningStudy}
                onClick={handleRunPairStudy}
              >
                {runningStudy ? 'Running study...' : 'Run pair study'}
              </button>
            ) : activeTab === 'profile' ? (
              <button
                className="primary-button"
                type="button"
                disabled={runningStudy}
                onClick={handleRunProfileStudy}
              >
                {runningStudy ? 'Running study...' : 'Run profile study'}
              </button>
            ) : activeTab === 'hybrid' ? (
              <button
                className="primary-button"
                type="button"
                disabled={runningStudy}
                onClick={handleRunHybridStudy}
              >
                {runningStudy ? 'Running study...' : 'Run hybrid study'}
              </button>
            ) : (
              <button
                className="primary-button"
                type="button"
                disabled={runningStudy}
                onClick={handleRunResidualStudy}
              >
                {runningStudy ? 'Running study...' : 'Run residual study'}
              </button>
            )}
          </div>

          {activeTab === 'pair' ? (
            <div className="field-grid compact-grid">
              <label>
                <span>Engineering quantity</span>
                <select
                  value={formState.pairStudy.quantity_key}
                  onChange={(event) =>
                    updateStudyField('pairStudy', 'quantity_key', event.target.value)
                  }
                >
                  {quantityOptions.map(([key, meta]) => (
                    <option key={key} value={key}>
                      {meta.label}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span>X parameter</span>
                <select
                  value={formState.pairStudy.x_param}
                  onChange={(event) =>
                    updateStudyField('pairStudy', 'x_param', event.target.value)
                  }
                >
                  {parameterOptions.map(([key, meta]) => (
                    <option key={key} value={key}>
                      {meta.label}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span>Y parameter</span>
                <select
                  value={formState.pairStudy.y_param}
                  onChange={(event) =>
                    updateStudyField('pairStudy', 'y_param', event.target.value)
                  }
                >
                  {parameterOptions.map(([key, meta]) => (
                    <option key={key} value={key}>
                      {meta.label}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span>Grid points</span>
                <input
                  type="number"
                  min="2"
                  max="41"
                  value={formState.pairStudy.n_points}
                  onChange={(event) =>
                    updateStudyField('pairStudy', 'n_points', Number(event.target.value))
                  }
                />
              </label>

              <label>
                <span>X start</span>
                <input
                  type="number"
                  step="any"
                  value={formState.pairStudy.x_spec[0]}
                  onChange={(event) => updatePairSpec('x_spec', 0, event.target.value)}
                />
              </label>

              <label>
                <span>X stop</span>
                <input
                  type="number"
                  step="any"
                  value={formState.pairStudy.x_spec[1]}
                  onChange={(event) => updatePairSpec('x_spec', 1, event.target.value)}
                />
              </label>

              <label>
                <span>Y start</span>
                <input
                  type="number"
                  step="any"
                  value={formState.pairStudy.y_spec[0]}
                  onChange={(event) => updatePairSpec('y_spec', 0, event.target.value)}
                />
              </label>

              <label>
                <span>Y stop</span>
                <input
                  type="number"
                  step="any"
                  value={formState.pairStudy.y_spec[1]}
                  onChange={(event) => updatePairSpec('y_spec', 1, event.target.value)}
                />
              </label>
            </div>
          ) : activeTab === 'profile' ? (
            <div className="field-grid compact-grid">
              <label>
                <span>Profile type</span>
                <select
                  value={formState.profileStudy.profile_key}
                  onChange={(event) =>
                    updateStudyField('profileStudy', 'profile_key', event.target.value)
                  }
                >
                  {profileOptions.map(([key, meta]) => (
                    <option key={key} value={key}>
                      {meta.label}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span>Vary parameter</span>
                <select
                  value={formState.profileStudy.param_key}
                  onChange={(event) =>
                    updateStudyField('profileStudy', 'param_key', event.target.value)
                  }
                >
                  {parameterOptions.map(([key, meta]) => (
                    <option key={key} value={key}>
                      {meta.label}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span>Line-style parameter</span>
                <select
                  value={formState.profileStudy.style_param_key}
                  onChange={(event) =>
                    updateStudyField('profileStudy', 'style_param_key', event.target.value)
                  }
                >
                  <option value="">None</option>
                  {parameterOptions.map(([key, meta]) => (
                    <option key={key} value={key}>
                      {meta.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="full-width">
                <span>Parameter values (comma separated)</span>
                <input
                  type="text"
                  value={formState.profileStudy.param_values_text}
                  onChange={(event) =>
                    updateStudyField('profileStudy', 'param_values_text', event.target.value)
                  }
                />
              </label>
              <label className="full-width">
                <span>Line-style values (comma separated)</span>
                <input
                  type="text"
                  value={formState.profileStudy.style_param_values_text}
                  onChange={(event) =>
                    updateStudyField(
                      'profileStudy',
                      'style_param_values_text',
                      event.target.value,
                    )
                  }
                />
              </label>
              <p className="inline-help">
                Example: vary `M` with `0.1, 1, 2, 3`, then compare `beta_T` with `0, 0.1`.
              </p>
            </div>
          ) : activeTab === 'hybrid' ? (
            <div className="field-grid compact-grid">
              <label>
                <span>Vary fraction</span>
                <select
                  value={formState.hybridStudy.fraction_key}
                  onChange={(event) => updateHybridFractionKey(event.target.value)}
                >
                  <option value="phi1">φ1</option>
                  <option value="phi2">φ2</option>
                </select>
              </label>

              <label>
                <span>Engineering quantity</span>
                <select
                  value={formState.hybridStudy.quantity_key}
                  onChange={(event) =>
                    updateStudyField('hybridStudy', 'quantity_key', event.target.value)
                  }
                >
                  {quantityOptions.map(([key, meta]) => (
                    <option key={key} value={key}>
                      {meta.label}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span>X parameter</span>
                <select
                  value={formState.hybridStudy.x_param}
                  onChange={(event) =>
                    updateStudyField('hybridStudy', 'x_param', event.target.value)
                  }
                >
                  {parameterOptions.map(([key, meta]) => (
                    <option key={key} value={key}>
                      {meta.label}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span>Y parameter</span>
                <select
                  value={formState.hybridStudy.y_param}
                  onChange={(event) =>
                    updateStudyField('hybridStudy', 'y_param', event.target.value)
                  }
                >
                  {parameterOptions.map(([key, meta]) => (
                    <option key={key} value={key}>
                      {meta.label}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span>Grid points</span>
                <input
                  type="number"
                  min="2"
                  max="41"
                  value={formState.hybridStudy.n_points}
                  onChange={(event) =>
                    updateStudyField('hybridStudy', 'n_points', Number(event.target.value))
                  }
                />
              </label>

              <label>
                <span>X start</span>
                <input
                  type="number"
                  step="any"
                  value={formState.hybridStudy.x_spec[0]}
                  onChange={(event) => updateHybridSpec('x_spec', 0, event.target.value)}
                />
              </label>

              <label>
                <span>X stop</span>
                <input
                  type="number"
                  step="any"
                  value={formState.hybridStudy.x_spec[1]}
                  onChange={(event) => updateHybridSpec('x_spec', 1, event.target.value)}
                />
              </label>

              <label>
                <span>Y start</span>
                <input
                  type="number"
                  step="any"
                  value={formState.hybridStudy.y_spec[0]}
                  onChange={(event) => updateHybridSpec('y_spec', 0, event.target.value)}
                />
              </label>

              <label>
                <span>Y stop</span>
                <input
                  type="number"
                  step="any"
                  value={formState.hybridStudy.y_spec[1]}
                  onChange={(event) => updateHybridSpec('y_spec', 1, event.target.value)}
                />
              </label>

              <label className="full-width">
                <span>
                  Fixed {formState.hybridStudy.fraction_key === 'phi1' ? 'φ2' : 'φ1'} value
                </span>
                <input
                  type="number"
                  step="any"
                  value={formState.hybridStudy.fixed_fraction_value}
                  onChange={(event) =>
                    updateStudyField(
                      'hybridStudy',
                      'fixed_fraction_value',
                      Number(event.target.value),
                    )
                  }
                />
              </label>
              <label className="full-width">
                <span>
                  Hybrid {formState.hybridStudy.fraction_key === 'phi1' ? 'φ1' : 'φ2'} values
                  (comma separated)
                </span>
                <input
                  type="text"
                  value={formState.hybridStudy.fraction_values_text}
                  onChange={(event) =>
                    updateStudyField('hybridStudy', 'fraction_values_text', event.target.value)
                  }
                />
              </label>
              <p className="inline-help">
                Uses the hybrid preset <code>MoS2-Cu/EG</code> and varies{' '}
                <code>{formState.hybridStudy.fraction_key === 'phi1' ? 'φ1' : 'φ2'}</code> while
                keeping{' '}
                <code>{formState.hybridStudy.fraction_key === 'phi1' ? 'φ2' : 'φ1'}</code> fixed at{' '}
                {Number(formState.hybridStudy.fixed_fraction_value).toFixed(2)}
                .
              </p>
            </div>
          ) : (
            <div className="field-grid compact-grid">
              <label className="checkbox-field full-width">
                <span>Enable residual iterations (`res`)</span>
                <input
                  type="checkbox"
                  checked={Boolean(formState.base_params.res)}
                  onChange={(event) => updateBaseParam('res', event.target.checked)}
                />
              </label>
              <p className="inline-help">
                Runs one residual solve for each enabled nanofluid preset and displays the
                momentum, energy, and concentration residuals in separate plots. Enabled presets:{' '}
                {enabledNanofluids.length > 0
                  ? enabledNanofluids.map((item) => item.display_name || item.name).join(', ')
                  : 'none'}
                .
              </p>
              <p className="inline-help">
                When <code>res=True</code>, the solver keeps iterating up to the maximum iteration
                count instead of stopping at the tolerance. This option defaults to{' '}
                <code>True</code>, but you can switch it off when needed.
              </p>
            </div>
          )}

          <details className="details-card" open>
            <summary>Base simulation parameters</summary>
            <div className="field-grid">
              {Object.entries(formState.base_params).map(([key, value]) => (
                <label key={key}>
                  <span>
                    {config.parameter_catalog[key]?.label ?? FIELD_LABELS[key] ?? key}
                  </span>
                  {typeof value === 'boolean' ? (
                    <input
                      type="checkbox"
                      checked={value}
                      onChange={(event) => updateBaseParam(key, event.target.checked)}
                    />
                  ) : key === 'convergence_type' ? (
                    <select
                      value={value}
                      onChange={(event) => updateBaseParam(key, event.target.value)}
                    >
                      {CONVERGENCE_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="number"
                      step="any"
                      value={value}
                      onChange={(event) => updateBaseParam(key, Number(event.target.value))}
                    />
                  )}
                </label>
              ))}
            </div>
          </details>

          <details className="details-card">
            <summary>Material properties</summary>
            <div className="stacked-groups">
              {Object.entries(formState.components).map(([componentKey, component]) => (
                <fieldset key={componentKey} className="sub-panel">
                  <legend>{COMPONENT_LABELS[componentKey] ?? componentKey}</legend>
                  <div className="field-grid compact-grid">
                    {Object.entries(component).map(([field, value]) => (
                      <label key={field}>
                        <span>{FIELD_LABELS[field] ?? field}</span>
                        {typeof value === 'boolean' ? (
                          <input
                            type="checkbox"
                            checked={value}
                            onChange={(event) =>
                              updateComponent(componentKey, field, event.target.checked)
                            }
                          />
                        ) : (
                          <input
                            type="number"
                            step="any"
                            value={value ?? ''}
                            onChange={(event) =>
                              updateComponent(
                                componentKey,
                                field,
                                numberOrNull(event.target.value),
                              )
                            }
                          />
                        )}
                      </label>
                    ))}
                  </div>
                </fieldset>
              ))}
            </div>
          </details>

          <details className="details-card">
            <summary>Nanofluid presets</summary>
            <div className="stacked-groups">
              {formState.nanofluids.map((nanofluid, index) => (
                <fieldset key={`${nanofluid.name}-${index}`} className="sub-panel">
                  <legend>{nanofluid.name}</legend>
                  <div className="field-grid compact-grid">
                    <label className="checkbox-field">
                      <span>Enabled</span>
                      <input
                        type="checkbox"
                        checked={nanofluid.enabled}
                        onChange={(event) =>
                          updateNanofluid(index, 'enabled', event.target.checked)
                        }
                      />
                    </label>
                    <label>
                      <span>{FIELD_LABELS.display_name}</span>
                      <input
                        type="text"
                        value={nanofluid.display_name ?? ''}
                        onChange={(event) =>
                          updateNanofluid(index, 'display_name', event.target.value)
                        }
                      />
                    </label>
                    <label>
                      <span>{FIELD_LABELS.phi1}</span>
                      <input
                        type="number"
                        step="any"
                        value={nanofluid.phi1}
                        onChange={(event) =>
                          updateNanofluid(index, 'phi1', Number(event.target.value))
                        }
                      />
                    </label>
                    <label>
                      <span>{FIELD_LABELS.phi2}</span>
                      <input
                        type="number"
                        step="any"
                        value={nanofluid.phi2}
                        onChange={(event) =>
                          updateNanofluid(index, 'phi2', Number(event.target.value))
                        }
                      />
                    </label>
                  </div>
                </fieldset>
              ))}
            </div>
          </details>
        </section>
        ) : null}

        <section className="panel results-panel">
          <div className="panel-header">
            <h2>{activeTab === 'overview' ? 'Overview dashboard' : 'Results'}</h2>
            {activeTab === 'overview' ? (
              <span className="meta-pill">
                {overviewMetrics.length}/{overviewStudyCards.length} study views available
              </span>
            ) : activeTab === 'pair' && pairResult ? (
              <span className="meta-pill">
                {pairResult.meta.successful_runs}/{pairResult.meta.total_runs} runs succeeded in{' '}
                {pairResult.meta.elapsed_seconds}s
              </span>
            ) : activeTab === 'profile' && profileResult ? (
              <span className="meta-pill">
                {profileResult.meta.successful_runs}/{profileResult.meta.total_runs} runs succeeded in{' '}
                {profileResult.meta.elapsed_seconds}s
              </span>
            ) : activeTab === 'hybrid' && hybridPairResult ? (
              <span className="meta-pill">
                {hybridPairResult.meta.successful_runs}/{hybridPairResult.meta.total_runs} runs
                succeeded in {hybridPairResult.meta.elapsed_seconds}s
              </span>
            ) : activeTab === 'residual' && residualResult ? (
              <span className="meta-pill">
                {residualResult.meta.successful_runs}/{residualResult.meta.total_runs} nanofluids
                converged in {residualResult.meta.elapsed_seconds}s
              </span>
            ) : (
              <span className="meta-pill muted">Run a study to populate the plots.</span>
            )}
          </div>

          {activeTab === 'overview' ? (
            overviewMetrics.length > 0 ? (
              <>
                <div className="summary-grid">
                  {overviewStudyCards.map((item) => (
                    <article className="summary-card" key={item.key}>
                      <h3>{item.label}</h3>
                      <p>status = {item.status}</p>
                      <p>
                        success = {item.status === 'available' ? `${item.success}/${item.total}` : 'n/a'}
                      </p>
                      <p>
                        elapsed ={' '}
                        {item.status === 'available' ? `${Number(item.elapsed).toFixed(3)}s` : 'n/a'}
                      </p>
                    </article>
                  ))}
                </div>

                <div className="overview-chart-grid">
                  <div className="plot-card">
                    <h3>Study coverage</h3>
                    <PlotlyChart
                      data={overviewCoverageData}
                      layout={withPlotTheme({
                        autosize: true,
                        margin: { l: 50, r: 10, t: 24, b: 60 },
                        barmode: 'group',
                        legend: { orientation: 'h', y: 1.12 },
                        xaxis: { title: { text: 'Study type' } },
                        yaxis: { title: { text: 'Runs' } },
                      }, plotTheme)}
                      config={{ responsive: true }}
                      height={420}
                    />
                  </div>

                  <div className="plot-card">
                    <h3>Elapsed time</h3>
                    <PlotlyChart
                      data={overviewTimingData}
                      layout={withPlotTheme({
                        autosize: true,
                        margin: { l: 50, r: 10, t: 24, b: 60 },
                        xaxis: { title: { text: 'Study type' } },
                        yaxis: { title: { text: 'Seconds' } },
                      }, plotTheme)}
                      config={{ responsive: true }}
                      height={420}
                    />
                  </div>
                </div>

                {pairResult ? (
                  <>
                    <div className="plot-card">
                      <h3>Engineering quantities overview</h3>
                      <PlotlyChart
                        data={surfacePlotData}
                        layout={withPlotTheme({
                          autosize: true,
                          margin: { l: 0, r: 0, t: 24, b: 0 },
                          legend: { orientation: 'h', y: 1.05 },
                          scene: {
                            xaxis: {
                              title: { text: getParameterAxisLabel(config, pairResult.meta.x_param) },
                            },
                            yaxis: {
                              title: { text: getParameterAxisLabel(config, pairResult.meta.y_param) },
                            },
                            zaxis: {
                              title: { text: getQuantityAxisLabel(config, pairResult.meta.quantity_key) },
                            },
                          },
                        }, plotTheme)}
                        config={{ responsive: true }}
                      />
                    </div>
                    <div className="plot-card">
                      <h3>Engineering contour overview</h3>
                      <PlotlyChart
                        data={contourPlotData}
                        layout={withPlotTheme({
                          autosize: true,
                          margin: { l: 50, r: 10, t: 24, b: 50 },
                          legend: { orientation: 'h', y: 1.08 },
                          xaxis: {
                            title: { text: getParameterAxisLabel(config, pairResult.meta.x_param) },
                          },
                          yaxis: {
                            title: { text: getParameterAxisLabel(config, pairResult.meta.y_param) },
                          },
                        }, plotTheme)}
                        config={{ responsive: true }}
                      />
                    </div>
                  </>
                ) : null}

                {comparisonProfilePlot ? (
                  <div className="plot-card">
                    <h3>Profile comparison overview</h3>
                    <PlotlyChart
                      data={comparisonProfilePlot.traces}
                      layout={withPlotTheme({
                        autosize: true,
                        margin: { l: 50, r: 10, t: 24, b: 50 },
                        legend: { orientation: 'h', y: 1.14 },
                        xaxis: {
                          title: { text: 'eta' },
                          range: profileXRange,
                        },
                        yaxis: {
                          title: {
                            text: getProfileAxisLabel(config, profileResult.meta.profile_key),
                          },
                        },
                      }, plotTheme)}
                      config={{ responsive: true }}
                    />
                  </div>
                ) : null}

                {hybridPairResult ? (
                  <div className="plot-card">
                    <h3>Hybrid engineering overview</h3>
                    <PlotlyChart
                      data={hybridSurfacePlotData}
                      layout={withPlotTheme({
                        autosize: true,
                        margin: { l: 0, r: 0, t: 24, b: 0 },
                        legend: { orientation: 'h', y: 1.05 },
                        scene: {
                          xaxis: {
                            title: { text: getParameterAxisLabel(config, hybridPairResult.meta.x_param) },
                          },
                          yaxis: {
                            title: { text: getParameterAxisLabel(config, hybridPairResult.meta.y_param) },
                          },
                          zaxis: {
                            title: {
                              text: getQuantityAxisLabel(config, hybridPairResult.meta.quantity_key),
                            },
                          },
                        },
                      }, plotTheme)}
                      config={{ responsive: true }}
                    />
                  </div>
                ) : null}

                {residualPlots.map((study) => (
                  <div className="plot-card" key={`overview-${study.name}`}>
                    <h3>{study.display_name} residual overview</h3>
                    <PlotlyChart
                      data={study.traces}
                      layout={withPlotTheme({
                        autosize: true,
                        margin: { l: 60, r: 10, t: 24, b: 50 },
                        legend: { orientation: 'h', y: 1.1 },
                        xaxis: { title: { text: 'Iterations' } },
                        yaxis: {
                          title: { text: 'Residuals' },
                          type: 'log',
                          exponentformat: 'power',
                          showexponent: 'all',
                        },
                      }, plotTheme)}
                      config={{ responsive: true }}
                    />
                  </div>
                ))}
              </>
            ) : (
              <div className="empty-state">
                <p>Run studies from the other tabs to populate the overview dashboard.</p>
              </div>
            )
          ) : activeTab === 'pair' && pairResult ? (
            <>
              <div className="summary-grid">
                {pairResult.surfaces.map((surface) => (
                  <article className="summary-card" key={surface.name}>
                    <h3>{surface.display_name}</h3>
                    <p>phi1 = {surface.phi1.toFixed(3)}</p>
                    <p>phi2 = {surface.phi2.toFixed(3)}</p>
                    <p>min = {surface.summary.min?.toFixed(5) ?? 'n/a'}</p>
                    <p>max = {surface.summary.max?.toFixed(5) ?? 'n/a'}</p>
                    <p>mean = {surface.summary.mean?.toFixed(5) ?? 'n/a'}</p>
                  </article>
                ))}
              </div>

              <div className="plot-card">
                <h3>3D comparison</h3>
                <PlotlyChart
                  data={surfacePlotData}
                  layout={withPlotTheme({
                    autosize: true,
                    margin: { l: 0, r: 0, t: 24, b: 0 },
                    legend: { orientation: 'h', y: 1.05 },
                    scene: {
                      xaxis: {
                        title: { text: getParameterAxisLabel(config, pairResult.meta.x_param) },
                      },
                      yaxis: {
                        title: { text: getParameterAxisLabel(config, pairResult.meta.y_param) },
                      },
                      zaxis: {
                        title: { text: getQuantityAxisLabel(config, pairResult.meta.quantity_key) },
                      },
                    },
                  }, plotTheme)}
                  config={{ responsive: true }}
                />
              </div>

              <div className="plot-card">
                <h3>Combined contour</h3>
                <PlotlyChart
                  data={contourPlotData}
                  layout={withPlotTheme({
                    autosize: true,
                    margin: { l: 50, r: 10, t: 24, b: 50 },
                    legend: { orientation: 'h', y: 1.08 },
                    xaxis: {
                      title: { text: getParameterAxisLabel(config, pairResult.meta.x_param) },
                    },
                    yaxis: {
                      title: { text: getParameterAxisLabel(config, pairResult.meta.y_param) },
                    },
                  }, plotTheme)}
                  config={{ responsive: true }}
                />
              </div>
            </>
          ) : activeTab === 'profile' && profileResult ? (
            <>
              <div className="summary-grid">
                {profileSummary.map((item) => (
                  <article className="summary-card" key={item.name}>
                    <h3>{item.display_name}</h3>
                    <p>phi1 = {item.phi1.toFixed(3)}</p>
                    <p>phi2 = {item.phi2.toFixed(3)}</p>
                    <p>successful curves = {item.success}</p>
                    <p>requested curves = {item.total}</p>
                  </article>
                ))}
              </div>

              {profilePlots.map((plotItem) => (
                <div className="plot-card" key={plotItem.name}>
                  <h3>
                    {plotItem.display_name} -{' '}
                    {config.profile_catalog[profileResult.meta.profile_key]?.label ??
                      profileResult.meta.profile_key}
                  </h3>
                  <PlotlyChart
                    data={plotItem.traces}
                    layout={withPlotTheme({
                      autosize: true,
                      margin: { l: 50, r: 10, t: 24, b: 50 },
                      legend: { orientation: 'h', y: 1.14 },
                      xaxis: {
                        title: { text: 'eta' },
                        range: profileXRange,
                      },
                      yaxis: {
                        title: {
                          text: getProfileAxisLabel(config, profileResult.meta.profile_key),
                        },
                      },
                    }, plotTheme)}
                    config={{ responsive: true }}
                  />
                  <p className="inline-help">
                    Legend entries show <code>{profileResult.meta.param_key}</code> values.{' '}
                    {describeLineStyles(profileResult.meta)}
                  </p>
                </div>
              ))}

              {comparisonProfilePlot ? (
                <div className="plot-card">
                  <h3>
                    Fluid comparison at{' '}
                    {formatParameterLabel(
                      profileResult.meta.param_key,
                      comparisonProfilePlot.value,
                    )}
                  </h3>
                  <PlotlyChart
                    data={comparisonProfilePlot.traces}
                    layout={withPlotTheme({
                      autosize: true,
                      margin: { l: 50, r: 10, t: 24, b: 50 },
                      legend: { orientation: 'h', y: 1.14 },
                      xaxis: {
                        title: { text: 'eta' },
                        range: profileXRange,
                      },
                      yaxis: {
                        title: {
                          text: getProfileAxisLabel(config, profileResult.meta.profile_key),
                        },
                      },
                    }, plotTheme)}
                    config={{ responsive: true }}
                  />
                  <p className="inline-help">
                    This comparison uses the middle sweep value, or the lower-middle value when the
                    number of parameter values is even. {describeLineStyles(profileResult.meta)}
                  </p>
                </div>
              ) : null}
            </>
          ) : activeTab === 'hybrid' && hybridPairResult ? (
            <>
              <div className="plot-card">
                <h3>Hybrid 3D comparison for MoS2-Cu/EG</h3>
                <PlotlyChart
                  data={hybridSurfacePlotData}
                  layout={withPlotTheme({
                    autosize: true,
                    margin: { l: 0, r: 0, t: 24, b: 0 },
                    legend: {
                      orientation: 'h',
                      y: 1.05,
                    },
                    scene: {
                      xaxis: {
                        title: { text: getParameterAxisLabel(config, hybridPairResult.meta.x_param) },
                      },
                      yaxis: {
                        title: { text: getParameterAxisLabel(config, hybridPairResult.meta.y_param) },
                      },
                      zaxis: {
                        title: {
                          text: getQuantityAxisLabel(config, hybridPairResult.meta.quantity_key),
                        },
                      },
                    },
                  }, plotTheme)}
                  config={{ responsive: true }}
                />
                <p className="inline-help">
                  Fixed hybrid fluid with{' '}
                  {formState.hybridStudy.fraction_key === 'phi1' ? 'φ2' : 'φ1'} ={' '}
                  {Number(formState.hybridStudy.fixed_fraction_value).toFixed(2)}{' '}
                  and varying {formState.hybridStudy.fraction_key === 'phi1' ? 'φ1' : 'φ2'} values.
                </p>
              </div>

              <div className="plot-card">
                <h3>{config.quantity_catalog[hybridPairResult.meta.quantity_key]?.label ?? 'Results'} table</h3>
                <div className="table-wrap">
                  <table className="results-table">
                    <thead>
                      <tr>
                        <th>{getParameterAxisLabel(config, hybridPairResult.meta.x_param)}</th>
                        <th>{getParameterAxisLabel(config, hybridPairResult.meta.y_param)}</th>
                        {hybridPairResult.surfaces.map((surface) => (
                          <th key={surface.name}>{surface.display_name}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {hybridTableRows.map((row, index) => (
                        <tr key={`${row.xValue}-${row.yValue}-${index}`}>
                          <td>{Number(row.xValue).toFixed(3)}</td>
                          <td>{Number(row.yValue).toFixed(3)}</td>
                          {row.values.map((value, valueIndex) => (
                            <td key={`${index}-${valueIndex}`}>
                              {value == null ? 'n/a' : Number(value).toFixed(5)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : activeTab === 'residual' && residualResult ? (
            <>
              <div className="summary-grid">
                {residualSummary.map((item) => (
                  <article className="summary-card" key={item.key}>
                    <h3>{item.displayName}</h3>
                    <p>phi1 = {Number(item.phi1).toFixed(3)}</p>
                    <p>phi2 = {Number(item.phi2).toFixed(3)}</p>
                    <p>iterations = {item.count}</p>
                    <p>status = {item.success ? 'ok' : 'failed'}</p>
                  </article>
                ))}
              </div>

              {residualPlots.map((study) => (
                <div className="plot-card" key={study.name}>
                  <h3>{study.display_name} residual analysis</h3>
                  <PlotlyChart
                    data={study.traces}
                    layout={withPlotTheme({
                      autosize: true,
                      margin: { l: 60, r: 10, t: 24, b: 50 },
                      legend: { orientation: 'h', y: 1.1 },
                      xaxis: { title: { text: 'Iterations' } },
                      yaxis: {
                        title: { text: 'Residuals' },
                        type: 'log',
                        exponentformat: 'power',
                        showexponent: 'all',
                      },
                    }, plotTheme)}
                    config={{ responsive: true }}
                  />
                  <p className="inline-help">
                    {study.display_name} with φ1 = {Number(study.phi1).toFixed(3)} and φ2 ={' '}
                    {Number(study.phi2).toFixed(3)}.
                  </p>
                </div>
              ))}
            </>
          ) : (
            <div className="empty-state">
              <p>
                {activeTab === 'pair'
                  ? 'The pair-variation surface and contour plots will appear here.'
                  : activeTab === 'profile'
                    ? 'The velocity, temperature, or concentration profile plots will appear here.'
                    : activeTab === 'hybrid'
                      ? 'The hybrid engineering 3D comparison and results table will appear here.'
                      : 'Separate residual plots for the enabled nanofluids will appear here.'}
              </p>
            </div>
          )}
        </section>
      </div>
    </main>
  )
}

export default App
