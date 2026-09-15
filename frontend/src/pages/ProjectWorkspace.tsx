import { useState, useMemo } from 'react'
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

  // Missing values & Treatment options
  const [missingMarker, setMissingMarker] = useState<string>('')
  const [treatment, setTreatment] = useState<'none' | 'listwise' | 'mean'>('none')

  // Sorting state for data table
  const [sortCol, setSortCol] = useState<number | null>(null)
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')

  const sortedRows = useMemo(() => {
    if (!data) return []
    if (sortCol === null) return data.rows
    return [...data.rows].sort((a, b) => {
      const valA = a[sortCol]
      const valB = b[sortCol]
      if (valA === null || valA === undefined || valA === '') return 1
      if (valB === null || valB === undefined || valB === '') return -1
      const numA = Number(valA)
      const numB = Number(valB)
      if (!isNaN(numA) && !isNaN(numB)) {
        return sortDirection === 'asc' ? numA - numB : numB - numA
      }
      return sortDirection === 'asc'
        ? String(valA).localeCompare(String(valB))
        : String(valB).localeCompare(String(valA))
    })
  }, [data, sortCol, sortDirection])

  function handleSort(colIdx: number) {
    if (sortCol === colIdx) {
      setSortDirection(prev => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortCol(colIdx)
      setSortDirection('asc')
    }
  }

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

      let url = `http://127.0.0.1:8721/project/save-data?path=${encodeURIComponent(projectPath!)}`
      if (missingMarker.trim()) {
        url += `&missing_value=${encodeURIComponent(missingMarker.trim())}`
      }
      if (treatment !== 'none') {
        url += `&treatment=${encodeURIComponent(treatment)}`
      }

      const saveRes = await fetch(url, { method: 'POST', body: formData })
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
      let url = `http://127.0.0.1:8721/project/treat-missing?path=${encodeURIComponent(projectPath!)}&method=${method}`
      if (missingMarker.trim()) {
        url += `&missing_value=${encodeURIComponent(missingMarker.trim())}`
      }
      const res = await fetch(url, { method: 'POST' })
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

      {/* Missing Value & Treatment Configuration Strip */}
      <div style={{ marginTop: 20, padding: 15, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8 }}>
        <h4 style={{ margin: '0 0 10px 0', fontSize: 14 }}>Import / Missing Value Settings</h4>
        <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', alignItems: 'center' }}>
          <div>
            <label style={{ fontSize: 12, fontWeight: 500, color: '#475569', display: 'block', marginBottom: 4 }}>
              Missing Values Denoted As:
            </label>
            <input
              type="text"
              value={missingMarker}
              onChange={(e) => setMissingMarker(e.target.value)}
              placeholder="e.g. -99, 999 (blank by default)"
              style={{
                padding: '6px 10px',
                border: '1px solid #cbd5e1',
                borderRadius: 6,
                fontSize: 13,
                width: 220,
              }}
            />
            <span style={{ fontSize: 11, color: '#94a3b8', display: 'block', marginTop: 2 }}>
              Replaces matching values with NA / blank
            </span>
          </div>

          <div>
            <label style={{ fontSize: 12, fontWeight: 500, color: '#475569', display: 'block', marginBottom: 4 }}>
              Missing Value Treatment:
            </label>
            <select
              value={treatment}
              onChange={(e) => setTreatment(e.target.value as 'none' | 'listwise' | 'mean')}
              style={{
                padding: '6px 10px',
                border: '1px solid #cbd5e1',
                borderRadius: 6,
                fontSize: 13,
                background: 'white',
              }}
            >
              <option value="none">None (Keep as blank/NA)</option>
              <option value="listwise">Listwise Deletion (Drop rows with missing)</option>
              <option value="mean">Mean Imputation (Replace with column average)</option>
            </select>
          </div>
        </div>

        <div style={{ marginTop: 15, display: 'flex', gap: 10 }}>
          <button onClick={handleImport} disabled={loading} style={{ fontWeight: 600, padding: '6px 14px' }}>
            {loading ? 'Importing...' : 'Import Data File'}
          </button>
          <button onClick={loadData}>Reload Saved Data</button>
          <button onClick={runDiagnostics}>Run Diagnostics</button>
        </div>
      </div>

      {error && <p style={{ color: 'red', marginTop: 10 }}>{error}</p>}

      {data && (
        <div style={{ marginTop: 20, overflowX: 'auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <p style={{ margin: 0, fontWeight: 600 }}>
              {data.rows.length} rows &times; {data.columns.length} columns loaded
              {sortCol !== null && (
                <span style={{ marginLeft: 8, fontSize: 12, color: '#6366f1', fontWeight: 500 }}>
                  (Sorted by {data.columns[sortCol]} {sortDirection.toUpperCase()})
                </span>
              )}
            </p>
            {sortCol !== null && (
              <button
                onClick={() => setSortCol(null)}
                style={{ fontSize: 11, padding: '2px 8px', color: '#64748b' }}
              >
                Clear Sort
              </button>
            )}
          </div>
          <table border={1} cellPadding={6} style={{ borderCollapse: 'collapse', width: '100%', borderColor: '#cbd5e1' }}>
            <thead style={{ background: '#f1f5f9' }}>
              <tr>
                <th style={{ width: 50, textAlign: 'center', fontSize: 12 }}>#</th>
                {data.columns.map((col, idx) => (
                  <th
                    key={col}
                    onClick={() => handleSort(idx)}
                    style={{
                      cursor: 'pointer',
                      userSelect: 'none',
                      padding: '8px 12px',
                      background: sortCol === idx ? '#e2e8f0' : undefined,
                      textAlign: 'left',
                      fontSize: 12,
                    }}
                    title="Click to sort by this column"
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
                      <span>{col}</span>
                      <span style={{ fontSize: 10, color: '#64748b' }}>
                        {sortCol === idx ? (sortDirection === 'asc' ? '▲' : '▼') : '↕'}
                      </span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedRows.slice(0, 50).map((row, i) => (
                <tr key={i} style={{ background: i % 2 === 1 ? '#f8fafc' : 'white' }}>
                  <td style={{ textAlign: 'center', fontSize: 11, color: '#94a3b8' }}>{i + 1}</td>
                  {row.map((val, j) => {
                    const isMissing = val === null || val === undefined || val === ''
                    return (
                      <td
                        key={j}
                        style={{
                          fontSize: 12,
                          color: isMissing ? '#d97706' : '#1e293b',
                          background: isMissing ? '#fef3c7' : undefined,
                          fontWeight: isMissing ? 600 : 400,
                        }}
                      >
                        {isMissing ? 'NA' : String(val)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: 12, color: '#64748b', marginTop: 6 }}>
            Showing first {Math.min(50, sortedRows.length)} of {sortedRows.length} rows. Click any column header to sort.
          </p>
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