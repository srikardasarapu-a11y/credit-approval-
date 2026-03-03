import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listApplications } from '../api/client.js'
import { PlusCircle, BarChart2, FileText, ChevronRight } from 'lucide-react'

const STATUS_COLORS = {
    pending: 'var(--text-muted)',
    processing: 'var(--accent)',
    completed: 'var(--success)',
    error: 'var(--danger)',
}

const GradeTag = ({ grade }) => grade
    ? <span className={`badge badge-${grade}`}>Grade {grade}</span>
    : <span className="text-muted text-xs">—</span>

export default function ApplicationsPage() {
    const navigate = useNavigate()
    const [apps, setApps] = useState([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        const load = async () => {
            try {
                const { data } = await listApplications()
                setApps(data)
            } catch (e) {
                console.error(e)
            } finally {
                setLoading(false)
            }
        }
        load()
        const interval = setInterval(load, 10000)
        return () => clearInterval(interval)
    }, [])

    const fmt = (n) => n ? `₹${Number(n).toLocaleString('en-IN')}` : '—'
    const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : ''

    if (loading) return (
        <div className="flex items-center justify-between" style={{ height: '50vh', justifyContent: 'center', flexDirection: 'column', gap: '1rem' }}>
            <div className="spinner" style={{ width: 40, height: 40, borderWidth: 3 }} />
            <span className="text-muted">Loading applications...</span>
        </div>
    )

    return (
        <div>
            <div className="flex items-center justify-between mb-4" style={{ marginBottom: '1.75rem' }}>
                <div>
                    <div className="page-title">Credit Applications</div>
                    <div className="page-sub" style={{ marginBottom: 0 }}>{apps.length} application{apps.length !== 1 ? 's' : ''} in system</div>
                </div>
                <button className="btn btn-primary" onClick={() => navigate('/upload')}>
                    <PlusCircle size={15} /> New Application
                </button>
            </div>

            {apps.length === 0 ? (
                <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
                    <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>📋</div>
                    <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>No applications yet</div>
                    <div className="text-muted text-sm mb-4">Submit your first credit application to get started</div>
                    <button className="btn btn-primary" onClick={() => navigate('/upload')}>
                        <PlusCircle size={15} /> Create First Application
                    </button>
                </div>
            ) : (
                <div className="card" style={{ padding: 0 }}>
                    <div className="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Company</th>
                                    <th>Date</th>
                                    <th>Status</th>
                                    <th>Score</th>
                                    <th>Grade</th>
                                    <th>Loan Limit</th>
                                    <th>Rate</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {apps.map(app => (
                                    <tr key={app.id}>
                                        <td>
                                            <div className="font-semibold" style={{ color: 'var(--text-primary)' }}>{app.company_name}</div>
                                            <div className="text-xs text-muted">{app.id.slice(0, 8)}</div>
                                        </td>
                                        <td className="text-sm">{fmtDate(app.created_at)}</td>
                                        <td>
                                            <span className={`status-pill status-${app.status}`}>
                                                <span className={`status-dot ${app.status === 'processing' ? 'pulse' : ''}`} />
                                                {app.status}
                                            </span>
                                        </td>
                                        <td>
                                            {app.credit_score != null
                                                ? <span style={{ fontWeight: 700, color: Number(app.credit_score) > 600 ? 'var(--success)' : Number(app.credit_score) > 400 ? 'var(--warning)' : 'var(--danger)' }}>
                                                    {Number(app.credit_score).toFixed(0)}
                                                </span>
                                                : '—'}
                                        </td>
                                        <td><GradeTag grade={app.risk_grade} /></td>
                                        <td className="text-sm">{fmt(app.recommended_loan_amount)}</td>
                                        <td className="text-sm">{app.interest_rate ? `${app.interest_rate}%` : '—'}</td>
                                        <td>
                                            {app.status === 'completed' && (
                                                <div className="flex gap-2">
                                                    <button className="btn btn-outline" style={{ padding: '0.35rem 0.625rem', fontSize: '0.75rem' }}
                                                        onClick={() => navigate(`/applications/${app.id}/dashboard`)}>
                                                        <BarChart2 size={12} /> Dashboard
                                                    </button>
                                                    <button className="btn btn-primary" style={{ padding: '0.35rem 0.625rem', fontSize: '0.75rem' }}
                                                        onClick={() => navigate(`/applications/${app.id}/report`)}>
                                                        <FileText size={12} /> CAM
                                                    </button>
                                                </div>
                                            )}
                                            {app.status === 'processing' && (
                                                <div className="flex items-center gap-2 text-sm text-muted"><div className="spinner" style={{ width: 14, height: 14 }} /> Analysing…</div>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    )
}
