import { Routes, Route, useNavigate } from 'react-router-dom'
import ProjectHome from './pages/ProjectHome.tsx'
import ProjectWorkspace from './pages/ProjectWorkspace.tsx'

function App() {
  const navigate = useNavigate()

  function handleProjectOpen(path: string) {
    navigate(`/workspace?path=${encodeURIComponent(path)}`)
  }

  return (
    <Routes>
      <Route path="/" element={<ProjectHome onProjectOpen={handleProjectOpen} />} />
      <Route path="/workspace" element={<ProjectWorkspace />} />
    </Routes>
  )
}

export default App