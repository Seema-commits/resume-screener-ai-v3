import { Navigate, Route, Routes } from 'react-router'

import { RequireAuth, RequirePermission } from './auth/guards'
import { AppShell } from './components/AppShell'
import { ChangePasswordPage } from './pages/ChangePasswordPage'
import { LoginPage } from './pages/LoginPage'
import { ScanDetailPage } from './pages/ScanDetailPage'
import { ScanHistoryPage } from './pages/ScanHistoryPage'
import { ScreenResumesPage } from './pages/ScreenResumesPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/change-password"
             element={<RequireAuth passwordChangePage><ChangePasswordPage /></RequireAuth>} />
      <Route element={<RequireAuth><AppShell /></RequireAuth>}>
        <Route index element={<Navigate to="/screen" replace />} />
        <Route path="screen"
               element={<RequirePermission permission="run_scan"><ScreenResumesPage /></RequirePermission>} />
        <Route path="scans"
               element={<RequirePermission permission="view_own_scans"><ScanHistoryPage /></RequirePermission>} />
        <Route path="scans/:id"
               element={<RequirePermission permission="view_own_scans"><ScanDetailPage /></RequirePermission>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
