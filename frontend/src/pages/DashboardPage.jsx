import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
    BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
    RadarChart, PolarGrid, PolarAngleAxis, Radar,
    AreaChart, Area, CartesianGrid,
} from 'recharts'
import { getResults } from '../api/client.js'
import { BarChart2, AlertTriangle, CheckCircle, FileText, TrendingUp, Shield } from 'lucide-react'

// ── Score Ring ──────────────────────────────────────────────────────────────
const ScoreRing = ({ score = 0, grade = 'C' }) => {
    const GRADE_COLORS = { A: '#10b981', B: '#22c55e', C: '#f59e0b', D: '#f97316', E: '#ef4444' }
    const pct = score / 1000
    const r = 48, cx = 60, cy = 60, circ = 2 * Math.PI * r
    const dash = pct * circ
    const color = GRADE_COLORS[grade] || '#60a5fa'

    return (
        <div style={{ textAlign: 'center' }}>
            <svg width={120} height={120} viewBox="0 0 120 120">
                <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--border)" strokeWidth={8} />
                <circle
                    cx={cx} cy={cy} r={r} fill="none"
                    stroke={color} strokeWidth={8}
                    strokeDasharray={`${dash} ${circ - dash}`}
                    strokeDashoffset={circ * 0.25}
                    strokeLinecap="round"
                    style={{ transition: 'stroke-dasharray 1s ease' }}
                />
                <text x={cx} y={cy - 6} textAnchor="middle" fill="var(--text-primary)" fontSize={20} fontWeight={800}>{Math.round(score)}</text>
                <text x={cx} y={cy + 12} textAnchor="middle" fill="var(--text-muted)" fontSize={9} fontWeight={600}>/ 1000</text>
            </svg>
            <span className={`badge badge-${grade}`} style={{ fontSize: '0.85rem', padding: '0.35rem 0.875rem' }}>Grade {grade}</span>
        </div>
    )
}

// ── Custom Tooltip ───────────────────────────────────────────────────────────
const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null
    return (
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, padding: '0.625rem 0.875rem', fontSize: '0.8rem' }}>
            <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
            {payload.map((p, i) => (
                <div key={i} style={{ color: p.color || 'var(--text-primary)', fontWeight: 600 }}>
                    {p.name}: {typeof p.value === 'number' ? p.value.toLocaleString('en-IN') : p.value}
                </div>
            ))}
        </div>
    )
}

// ── Main Dashboard ───────────────────────────────────────────────────────────
export default function DashboardPage() {
    const { id } = useParams()
    const navigate = useNavigate()
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [polling, setPolling] = useState(true)

    const load = useCallback(async () => {
        try {
            const { data: d } = await getResults(id)
            setData(d)
            if (d.status === 'completed' || d.status === 'error') setPolling(false)
        } catch (e) {
            console.error(e)
        } finally {
            setLoading(false)
        }
    }, [id])

    useEffect(() => {
        load()
        if (!polling) return
        const iv = setInterval(load, 3000)
        return () => clearInterval(iv)
    }, [load, polling])

    if (loading) return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '50vh', gap: '1rem', flexDirection: 'column' }}>
            <div className="spinner" style={{ width: 40, height: 40, borderWidth: 3 }} />
            <span className="text-muted">Loading dashboard...</span>
        </div>
    )

    if (!data) return <div className="alert alert-danger">Application not found.</div>

    if (data.status === 'processing' || data.status === 'pending') return (
        <div style={{ textAlign: 'center', padding: '4rem 2rem' }}>
            <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>⚙️</div>
            <div style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.5rem' }}>AI Analysis in Progress</div>
            <div className="text-muted text-sm mb-4">Running document ingestion, scoring, and research... this takes 30–60 seconds.</div>
            <div className="progress-bar" style={{ width: 300, margin: '0 auto' }}>
                <div className="progress-bar-fill" style={{ width: '60%', animation: 'none' }} />
            </div>
        </div>
    )

    if (data.status === 'error') return (
        <div className="alert alert-danger">
            <AlertTriangle size={16} /> Analysis failed: {data.error_message || 'Unknown error'}
        </div>
    )

    const ratios = data.financial_ratios || {}
    const shap = data.shap_values || {}
    const recon = data.reconciliation_data || {}
    const research = data.research_data || {}
    const loan = {
        recommended_loan_amount: data.recommended_loan_amount,
        interest_rate: data.interest_rate,
        reasons: data.loan_decision_reasons || [],
    }

    // SHAP chart data
    const shapData = Object.entries(shap)
        .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
        .map(([name, value]) => ({
            feature: name.replace(/_/g, ' '),
            value: +value.toFixed(2),
        }))

    // Ratio radar data
    const radarData = [
        { subject: 'DSCR', value: Math.min((ratios.dscr || 0) / 3, 1) * 100 },
        { subject: 'Liquidity', value: Math.min((ratios.current_ratio || 0) / 3, 1) * 100 },
        { subject: 'Int Cover', value: Math.min((ratios.interest_coverage || 0) / 8, 1) * 100 },
        { subject: 'Margin', value: Math.max((ratios.gross_margin || 0) * 100, 0) },
        { subject: 'Leverage', value: Math.max(100 - (ratios.de_ratio || 0) * 20, 0) },
    ]

    // Reconciliation chart
    const reconChart = (recon.monthly_breakdown || []).map(r => ({
        month: r.month,
        'GST Sales': r.gst_sales,
        'Bank Credits': r.bank_credits,
        anomaly: r.is_anomaly,
    }))

    const fmt = (n) => n != null ? `₹${Number(n).toLocaleString('en-IN')}` : '—'

    return (
        <div>
            {/* Header */}
            <div className="flex items-center justify-between mb-4" style={{ marginBottom: '1.5rem' }}>
                <div>
                    <div className="page-title">{data.company_name}</div>
                    <div className="page-sub" style={{ marginBottom: 0 }}>Risk Dashboard — Application {id.slice(0, 8)}</div>
                </div>
                <div className="flex gap-3">
                    <button className="btn btn-outline" onClick={() => navigate(`/applications/${id}/review`)}>
                        <BarChart2 size={14} /> Data Review
                    </button>
                    <button className="btn btn-primary" onClick={() => navigate(`/applications/${id}/report`)}>
                        <FileText size={14} /> Download CAM
                    </button>
                </div>
            </div>

            {/* Auto-reject banner */}
            {data.rule_flags?.some(f => f.includes('DSCR') || f.includes('equity')) && (
                <div className="alert alert-danger mb-6" style={{ marginBottom: '1.25rem' }}>
                    <AlertTriangle size={16} />
                    <div>
                        <strong>Auto-Reject:</strong>{' '}
                        {data.rule_flags.filter(f => f.includes('DSCR') || f.includes('equity'))[0]}
                    </div>
                </div>
            )}

            {/* Top KPIs */}
            <div className="grid-4 mb-6" style={{ marginBottom: '1.25rem' }}>
                {[
                    { label: 'Credit Score', value: `${Math.round(data.credit_score || 0)} / 1000`, color: data.credit_score > 600 ? 'var(--success)' : data.credit_score > 400 ? 'var(--warning)' : 'var(--danger)' },
                    { label: 'Risk Grade', value: `Grade ${data.risk_grade || '—'}` },
                    { label: 'Loan Limit', value: fmt(data.recommended_loan_amount) },
                    { label: 'Interest Rate', value: data.interest_rate ? `${data.interest_rate}% p.a.` : '—' },
                ].map(({ label, value, color }) => (
                    <div className="stat-card" key={label}>
                        <div className="stat-value" style={color ? { color } : {}}>{value}</div>
                        <div className="stat-label">{label}</div>
                    </div>
                ))}
            </div>

            {/* Row 1: Score + Financial Ratios */}
            <div className="grid-2 mb-6" style={{ marginBottom: '1.25rem' }}>
                <div className="card">
                    <div className="card-header"><div className="card-title"><span className="icon">🎯</span> Credit Score</div></div>
                    <div className="flex" style={{ gap: '2rem', alignItems: 'center', flexWrap: 'wrap' }}>
                        <ScoreRing score={data.credit_score || 0} grade={data.risk_grade || 'E'} />
                        <div style={{ flex: 1, minWidth: 180 }}>
                            {[
                                ['DSCR', ratios.dscr?.toFixed(2)],
                                ['D/E Ratio', ratios.de_ratio?.toFixed(2)],
                                ['Current Ratio', ratios.current_ratio?.toFixed(2)],
                                ['Interest Coverage', ratios.interest_coverage?.toFixed(2)],
                                ['Gross Margin', ratios.gross_margin != null ? `${(ratios.gross_margin * 100).toFixed(1)}%` : '—'],
                            ].map(([label, val]) => (
                                <div key={label} className="flex justify-between" style={{ marginBottom: '0.5rem', fontSize: '0.8125rem' }}>
                                    <span className="text-muted">{label}</span>
                                    <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>{val || '—'}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                <div className="card">
                    <div className="card-header"><div className="card-title"><span className="icon">🕸</span> Ratio Radar</div></div>
                    <ResponsiveContainer width="100%" height={200}>
                        <RadarChart data={radarData}>
                            <PolarGrid stroke="var(--border)" />
                            <PolarAngleAxis dataKey="subject" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                            <Radar name="Score" dataKey="value" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.2} strokeWidth={2} />
                        </RadarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Row 2: SHAP + Reconciliation */}
            <div className="grid-2 mb-6" style={{ marginBottom: '1.25rem' }}>
                <div className="card">
                    <div className="card-header"><div className="card-title"><span className="icon">🔬</span> SHAP — Score Drivers</div></div>
                    {shapData.length > 0 ? (
                        <ResponsiveContainer width="100%" height={220}>
                            <BarChart data={shapData} layout="vertical" margin={{ left: 10, right: 30 }}>
                                <XAxis type="number" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} />
                                <YAxis type="category" dataKey="feature" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} axisLine={false} tickLine={false} width={100} />
                                <Tooltip content={<CustomTooltip />} />
                                <ReferenceLine x={0} stroke="var(--border)" />
                                <Bar dataKey="value" radius={[0, 4, 4, 0]}
                                    fill="#3b82f6"
                                    label={false}
                                    isAnimationActive={true}
                                />
                            </BarChart>
                        </ResponsiveContainer>
                    ) : <div className="text-muted text-sm">No SHAP data available.</div>}
                </div>

                <div className="card">
                    <div className="card-header">
                        <div className="card-title"><span className="icon">📊</span> GST vs Bank Credits</div>
                        {recon.risk_flag && <span className="badge badge-danger">⚠ Risk Flag</span>}
                    </div>
                    {reconChart.length > 0 ? (
                        <ResponsiveContainer width="100%" height={220}>
                            <BarChart data={reconChart} barGap={2}>
                                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                                <XAxis dataKey="month" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} />
                                <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => `₹${(v / 100000).toFixed(0)}L`} />
                                <Tooltip content={<CustomTooltip />} />
                                <Bar dataKey="GST Sales" fill="#3b82f6" radius={[3, 3, 0, 0]} />
                                <Bar dataKey="Bank Credits" fill="#8b5cf6" radius={[3, 3, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    ) : <div className="text-muted text-sm">Upload both GST and bank statement to see reconciliation.</div>}
                    {recon.summary && <div className="text-xs text-muted" style={{ marginTop: '0.75rem' }}>{recon.summary}</div>}
                </div>
            </div>

            {/* Row 3: Research + Loan Decision */}
            <div className="grid-2">
                <div className="card">
                    <div className="card-header"><div className="card-title"><span className="icon">🔎</span> External Research</div></div>
                    <div className="flex justify-between mb-3" style={{ marginBottom: '1rem' }}>
                        {[
                            { label: 'News Risk', value: research.news_risk_score, color: research.news_risk_score > 0.5 ? 'var(--danger)' : 'var(--success)' },
                            { label: 'MCA Risk', value: research.mca_risk_score, color: research.mca_risk_score > 0.3 ? 'var(--warning)' : 'var(--success)' },
                            { label: 'Legal Risk', value: research.legal_risk_score, color: research.legal_risk_score > 0.3 ? 'var(--danger)' : 'var(--success)' },
                        ].map(({ label, value, color }) => (
                            <div key={label} style={{ textAlign: 'center' }}>
                                <div style={{ fontSize: '1.25rem', fontWeight: 800, color }}>{((value || 0) * 100).toFixed(0)}%</div>
                                <div className="text-xs text-muted">{label}</div>
                            </div>
                        ))}
                    </div>
                    {research.news_summary && <div className="text-sm text-secondary mb-2">{research.news_summary}</div>}
                    {research.legal_summary && <div className="text-sm text-secondary mb-2">{research.legal_summary}</div>}
                    {(research.mca_flags || []).map((f, i) => (
                        <div key={i} className="alert alert-warn" style={{ marginBottom: '0.5rem', padding: '0.5rem 0.75rem' }}>
                            <AlertTriangle size={13} />{f}
                        </div>
                    ))}
                    {/* News items */}
                    {(research.news || []).slice(0, 3).map((n, i) => (
                        <div key={i} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', fontSize: '0.75rem' }}>
                            <span style={{ color: n.sentiment === 'negative' ? 'var(--danger)' : n.sentiment === 'positive' ? 'var(--success)' : 'var(--text-muted)' }}>●</span>
                            <a href={n.url} target="_blank" rel="noreferrer" style={{ color: 'var(--text-secondary)', textDecoration: 'none', flex: 1 }} className="truncate">{n.title}</a>
                        </div>
                    ))}
                </div>

                <div className="card">
                    <div className="card-header">
                        <div className="card-title"><span className="icon">💰</span> Loan Decision</div>
                        <span className={`badge ${data.recommended_loan_amount > 0 ? 'badge-success' : 'badge-danger'}`}>
                            {data.recommended_loan_amount > 0 ? '✓ APPROVED' : '✗ DECLINED'}
                        </span>
                    </div>
                    <div className="grid-2" style={{ gap: '0.75rem', marginBottom: '1.25rem' }}>
                        {[
                            { label: 'Recommended Limit', value: fmt(data.recommended_loan_amount) },
                            { label: 'Interest Rate', value: data.interest_rate ? `${data.interest_rate}%` : '—' },
                        ].map(({ label, value }) => (
                            <div key={label} style={{ background: 'var(--bg-primary)', borderRadius: 8, padding: '0.875rem', textAlign: 'center' }}>
                                <div style={{ fontSize: '1.125rem', fontWeight: 800, color: 'var(--text-primary)' }}>{value}</div>
                                <div className="text-xs text-muted" style={{ marginTop: '0.25rem' }}>{label}</div>
                            </div>
                        ))}
                    </div>
                    {(loan.reasons || []).map((r, i) => (
                        <div key={i} className="flex items-center gap-2" style={{ marginBottom: '0.5rem', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                            <span style={{ color: r.startsWith('⚠') ? 'var(--warning)' : 'var(--accent)', fontSize: '0.7rem' }}>►</span>
                            {r}
                        </div>
                    ))}
                    {/* Rule flags */}
                    {(data.rule_flags || []).length > 0 && (
                        <div style={{ marginTop: '1rem' }}>
                            {data.rule_flags.map((f, i) => (
                                <div key={i} className="alert alert-warn" style={{ marginBottom: '0.5rem', padding: '0.5rem 0.75rem', fontSize: '0.75rem' }}>
                                    <AlertTriangle size={13} /> {f}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
