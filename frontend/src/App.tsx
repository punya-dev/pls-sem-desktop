import { useEffect, useState } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import { readFile } from '@tauri-apps/plugin-fs'


function App() {
  const [status, setStatus] = useState('checking...')
  const [preview, setPreview] = useState<any>(null)


  useEffect(() => {
    fetch('http://127.0.0.1:8721/health')
      .then((res) => res.json())
      .then((data) => setStatus(data.status))
      .catch(() => setStatus('backend not reachable'))
  }, [])

  async function handleImport() {
    const filePath = await open({
      multiple: false,
      filters: [{ name: 'Data', extensions: ['csv', 'xlsx', 'xls'] }],
    })
    if (!filePath || typeof filePath !== 'string') return

    const bytes = await readFile(filePath)
    const fileName = filePath.split('/').pop() ?? 'upload.csv'
    const blob = new Blob([bytes])
    const formData = new FormData()
    formData.append('file', blob, fileName)

    const res = await fetch('http://127.0.0.1:8721/data/import', {
      method: 'POST',
      body: formData,
    })
    const data = await res.json()
    setPreview(data)
  }


  return (
    <div>
      <div>Backend status: {status}</div>
      <button onClick={handleImport}>Import Data File</button>

      {preview && (
        <table>
          <thead>
            <tr>
              {preview.columns.map((col: string) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.preview.map((row: any, i: number) => (
              <tr key={i}>
                {preview.columns.map((col: string) => (
                  <td key={col}>{row[col]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default App