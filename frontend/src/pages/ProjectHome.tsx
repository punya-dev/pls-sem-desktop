import { useEffect, useState } from 'react'
import { save, open } from '@tauri-apps/plugin-dialog'

interface RecentProject {
  path: string
  name: string
  modified_at: string
}

function ProjectHome({ onProjectOpen }: { onProjectOpen: (path: string) => void }) {
  const [recentProjects, setRecentProjects] = useState<RecentProject[]>([])

  useEffect(() => {
    fetch('http://127.0.0.1:8721/project/recent')
      .then((res) => res.json())
      .then((data) => setRecentProjects(data))
      .catch(() => setRecentProjects([]))
  }, [])

  async function handleNewProject() {
    const filePath = await save({
      defaultPath: 'untitled.pls',
      filters: [{ name: 'PLS Project', extensions: ['pls'] }],
    })
    if (!filePath) return

    const name = filePath.split('/').pop()?.replace('.pls', '') ?? 'Untitled'

    const res = await fetch(
      `http://127.0.0.1:8721/project/create?path=${encodeURIComponent(filePath)}&name=${encodeURIComponent(name)}`,
      { method: 'POST' }
    )
    const data = await res.json()
    if (data.status === 'created') {
      onProjectOpen(filePath)
    } else {
      alert(data.error ?? 'Failed to create project')
    }
  }

  async function handleOpenProject() {
    const filePath = await open({
      multiple: false,
      filters: [{ name: 'PLS Project', extensions: ['pls'] }],
    })
    if (!filePath || typeof filePath !== 'string') return

    await fetch(`http://127.0.0.1:8721/project/open?path=${encodeURIComponent(filePath)}`, {
      method: 'POST',
    })
    onProjectOpen(filePath)
  }

  return (
    <div style={{ padding: 40 }}>
      <h1>PLS-SEM Desktop</h1>
      <button onClick={handleNewProject}>New Project</button>
      <button onClick={handleOpenProject} style={{ marginLeft: 10 }}>
        Open Project
      </button>

      <h2 style={{ marginTop: 30 }}>Recent Projects</h2>
      {recentProjects.length === 0 && <p>No recent projects</p>}
      <ul>
        {recentProjects.map((p) => (
          <li key={p.path}>
            <button onClick={() => onProjectOpen(p.path)}>
              {p.name} — {p.modified_at}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default ProjectHome