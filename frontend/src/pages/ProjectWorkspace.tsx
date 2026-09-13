import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { open } from '@tauri-apps/plugin-dialog'
import { readFile } from '@tauri-apps/plugin-fs'

interface ProjectData {
  columns: string[]
  rows: any[][]
}

interface ColumnStats {
  mean: number
  std: number
  min: number
  max: number
  skewness: number
  kurtosis: number
  non_normal_flag: boolean
}

interface MissingInfo {
  missing_count: number
  missing_pct: number
}

interface Diagnostics {
  row_count: number
  descriptive_stats: Record<string, ColumnStats>
  missing_report: Record<string, MissingInfo>
}

function ProjectWorkspace() {
  const [searchParams] = useSearchParams()
  const projectPath = searchParams.get('path')
  const navigate = useNavigate()

  const [data, setData] = useState<ProjectData | null>(null)
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [treating, setTreating] = useState(false)

  if (!projectPath) {
    return <p>No project loaded.</p>
  }

  async function handleImport() {
    setError(null)
    const filePath = await open({
      multiple: false,
      filters: [{ name: 'Data', extensions: ['csv', 'xlsx', 'xls'] }],
    })
    if (!filePath || typeof filePath !== 'string') return

    setLoading(true)
    try {
      const bytes = await readFile(filePath)
      const fileName = filePath.split('/').pop() ?? 'upload.csv'
      const blob = new Blob([bytes])
      const formData = new FormData()
      formData.append('file', blob, fileName)

      const saveRes = await fetch(
        `http://127.0.0.1:8721/project/save-data?path=${encodeURIComponent(projectPath!)}`,
        { method: 'POST', body: formData }
      )
      const saveData = await saveRes.json()
      if (saveData.error) {
        setError(saveData.error)
        return
      }

      await loadData()
      setDiagnostics(null) // clear stale diagnostics from any previous dataset
    } catch (err) {
      setError('Failed to import file')
    } finally {
      setLoading(false)
    }
  }

  async function loadData() {
    const res = await fetch(
      `http://127.0.0.1:8721/project/load-data?path=${encodeURIComponent(projectPath!)}`
    )
    const result = await res.json()
    if (result.error) {
      setError(result.error)
      setData(null)
    } else {
      setData(result)
    }
  }

  async function runDiagnostics() {
    setError(null)
    const res = await fetch(
      `http://127.0.0.1:8721/project/diagnostics?path=${encodeURIComponent(projectPath!)}`
    )
    const result = await res.json()
    if (result.error) {
      setError(result.error)
      setDiagnostics(null)
    } else {
      setDiagnostics(result)
    }
  }

  async function handleTreatMissing(method: 'listwise' | 'mean') {
  setError(null)
  setTreating(true)
  try {
    const res = await fetch(
      `http://127.0.0.1:8721/project/treat-missing?path=${encodeURIComponent(projectPath!)}&method=${method}`,
      { method: 'POST' }
    )
    const result = await res.json()
    if (result.error) {
      setError(result.error)
      return
    }

    alert(
      `${result.method} applied: ${result.original_row_count} → ${result.cleaned_row_count} rows (${result.rows_dropped} dropped)`
    )

    // refresh both data preview and diagnostics to reflect the change
    await loadData()
    await runDiagnostics()
  } catch (err) {
    setError('Failed to apply treatment')
  } finally {
    setTreating(false)
  }
}

  return (
    <div style={{ padding: 20 }}>
      <p>Project open: {projectPath}</p>
      <button onClick={() => navigate('/')}>← Back to Projects</button>

      <div style={{ marginTop: 20 }}>
        <button onClick={handleImport} disabled={loading}>
          {loading ? 'Importing...' : 'Import Data File'}
        </button>
        <button onClick={loadData} style={{ marginLeft: 10 }}>
          Reload Saved Data
        </button>
        <button onClick={runDiagnostics} style={{ marginLeft: 10 }}>
          Run Diagnostics
        </button>
      </div>

      {error && <p style={{ color: 'red' }}>{error}</p>}

      {data && (
        <div style={{ marginTop: 20, overflowX: 'auto' }}>
          <p>{data.rows.length} rows loaded</p>
          <table border={1} cellPadding={4}>
            <thead>
              <tr>
                {data.columns.map((col) => (
                  <th key={col}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.slice(0, 20).map((row, i) => (
                <tr key={i}>
                  {row.map((val, j) => (
                    <td key={j}>{val === null ? '—' : String(val)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {data.rows.length > 20 && <p>Showing first 20 of {data.rows.length} rows</p>}
        </div>
      )}

      {diagnostics && (
        <div style={{ marginTop: 30 }}>
          <h3>Descriptive Statistics</h3>
          <div style={{ overflowX: 'auto' }}>
            <table border={1} cellPadding={4}>
              <thead>
                <tr>
                  <th>Column</th>
                  <th>Mean</th>
                  <th>Std</th>
                  <th>Min</th>
                  <th>Max</th>
                  <th>Skewness</th>
                  <th>Kurtosis</th>
                  <th>Normality</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(diagnostics.descriptive_stats).map(([col, s]) => (
                  <tr key={col} style={{ background: s.non_normal_flag ? '#fff3cd' : undefined }}>
                    <td>{col}</td>
                    <td>{s.mean.toFixed(3)}</td>
                    <td>{s.std.toFixed(3)}</td>
                    <td>{s.min}</td>
                    <td>{s.max}</td>
                    <td>{s.skewness.toFixed(3)}</td>
                    <td>{s.kurtosis.toFixed(3)}</td>
                    <td>{s.non_normal_flag ? '⚠️ Non-normal' : 'OK'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 style={{ marginTop: 20 }}>Missing Values</h3>
          <div style={{ overflowX: 'auto' }}>
            <table border={1} cellPadding={4}>
              <thead>
                <tr>
                  <th>Column</th>
                  <th>Missing Count</th>
                  <th>Missing %</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(diagnostics.missing_report).map(([col, m]) => (
                  <tr key={col} style={{ background: m.missing_count > 0 ? '#f8d7da' : undefined }}>
                    <td>{col}</td>
                    <td>{m.missing_count}</td>
                    <td>{m.missing_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ marginTop: 20 }}>
            <h3>Treat Missing Values</h3>
            <p style={{ color: '#856404' }}>
                ⚠️ This permanently modifies the saved dataset in this project.
            </p>
            <button onClick={() => handleTreatMissing('listwise')} disabled={treating}>
                {treating ? 'Applying...' : 'Apply Listwise Deletion'}
            </button>
            <button
                onClick={() => handleTreatMissing('mean')}
                disabled={treating}
                style={{ marginLeft: 10 }}
            >
                {treating ? 'Applying...' : 'Apply Mean Imputation'}
            </button>
            </div>
        </div>
      )}
    </div>
  )
}

export default ProjectWorkspace