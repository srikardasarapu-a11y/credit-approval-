import { Routes, Route, NavLink, useNavigate } from 'react-router-dom'
import { UploadCloud, BarChart2, FileText, Search, Home } from 'lucide-react'
import UploadPage from './pages/UploadPage.jsx'
import ReviewPage from './pages/ReviewPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import ReportPage from './pages/ReportPage.jsx'
import ApplicationsPage from './pages/ApplicationsPage.jsx'

const navItems = [
    { to: '/', icon: Home, label: 'Applications' },
    { to: '/upload', icon: UploadCloud, label: 'New Application' },
]

export default function App() {
    return (
        <div className="app-shell">
            {/* Sidebar */}
            <aside className="sidebar">
                <div className="sidebar-logo">
                    <div className="logo-icon">CS</div>
                    <div>
                        <div className="logo-text">CreditSight</div>
                        <span className="logo-sub">AI APPRAISAL ENGINE</span>
                    </div>
                </div>
                <nav className="sidebar-nav">
                    {navItems.map(({ to, icon: Icon, label }) => (
                        <NavLink
                            key={to}
                            to={to}
                            end={to === '/'}
                            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                        >
                            <Icon size={16} />
                            <span>{label}</span>
                        </NavLink>
                    ))}
                </nav>
            </aside>

            {/* Main content */}
            <main className="main-content">
                <Routes>
                    <Route path="/" element={<ApplicationsPage />} />
                    <Route path="/upload" element={<UploadPage />} />
                    <Route path="/applications/:id/review" element={<ReviewPage />} />
                    <Route path="/applications/:id/dashboard" element={<DashboardPage />} />
                    <Route path="/applications/:id/report" element={<ReportPage />} />
                </Routes>
            </main>
        </div>
    )
}
