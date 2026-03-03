import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getResults, downloadCAM } from '../api/client.js'
import { Download, BarChart2, CheckCircle, XCircle, AlertTriangle } from 'lucide-react'

export default function ReportPage() {
    const { id } = useParams()
    const navigate = useNavigate()
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        getResults(id).then(({ data: d }) => setData(d)).catch(console.error).finally(() => setLoading(false))
    }, [id])

    if (loading) return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '50vh', flexDirection: 'column', gap: '1rem' }}>
            <div className="spinner" style={{ width: 40, height: 40, borderWidth: 3 }} />
        </div>
    )

    if (!data) return <div className="alert alert-danger">Application not found.</div>
    if (data.status !== 'completed') return (
        <div className="alert alert-info"><AlertTriangle size={16} /> Analysis not yet complete. Status: {data.status}</div>
    )

    const camUrl = downloadCAM(id)
    const approved = data.recommended_loan_amount > 0
    const fmt = (n) => n != null ? `₹${Number(n).toLocaleString('en-IN')}` : '—'

    return (
        <div>
            <div className="flex items-center justify-between mb-4" style={{ marginBottom: '1.5rem' }}>
                <div>
                    <div className="page-title">Credit Appraisal Memo</div>
                    <div className="page-sub" style={{ marginBottom: 0 }}>{data.company_name} — {id.slice(0, 8)}</div>
                </div>
                <div className="flex gap-3">
                    <button className="btn btn-outline" onClick={() => navigate(`/applications/${id}/dashboard`)}>
                        <BarChart2 size={14} /> Dashboard
                    </button>
                    <a href={camUrl} download className="btn btn-primary">
                        <Download size={14} /> Download CAM
                    </a>
                </div>
            </div>

            {/* Decision Banner */}
            <div className={`alert ${approved ? 'alert-success' : 'alert-danger'}`} style={{ marginBottom: '1.5rem', fontSize: '1rem', fontWeight: 600 }}>
                {approved
                    ? <><CheckCircle size={20} /> Application APPROVED — Loan Limit {fmt(data.recommended_loan_amount)} @ {data.interest_rate}% p.a.</>
                    : <><XCircle size={20} /> Application DECLINED — {data.loan_decision_reasons?.[0] || data.rule_flags?.[0] || 'Credit criteria not met.'}</>
                }
            </div>

            <div className="grid-2" style={{ gap: '1.25rem', alignItems: 'start' }}>

                {/* Summary card */}
                <div className="card">
                    <div className="card-header"><div className="card-title"><span className="icon">📋</span> Executive Summary</div></div>
                    {[
                        ['Company', data.company_name],
                        ['GSTIN', data.gstin || '—'],
                        ['CIN', data.cin || '—'],
                        ['Credit Score', `${Math.round(data.credit_score || 0)} / 1000`],
                        ['Risk Grade', `Grade ${data.risk_grade || '—'}`],
                        ['Recommended Limit', fmt(data.recommended_loan_amount)],
                        ['Interest Rate', data.interest_rate ? `${data.interest_rate}%` : '—'],
                    ].map(([label, value]) => (
                        <div key={label} className="flex justify-between" style={{ padding: '0.5rem 0', borderBottom: '1px solid rgba(42,53,82,0.4)', fontSize: '0.8125rem' }}>
                            <span className="text-muted">{label}</span>
                            <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>{value}</span>
                        </div>
                    ))}
                </div>

                {/* Decision rationale */}
                <div className="card">
                    <div className="card-header"><div className="card-title"><span className="icon">📝</span> Decision Rationale</div></div>
                    {(data.loan_decision_reasons || []).map((r, i) => (
                        <div key={i} className="flex items-center gap-2" style={{ marginBottom: '0.625rem', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                            <span style={{ color: r.startsWith('⚠') ? 'var(--warning)' : 'var(--accent)', fontSize: '0.7rem', flexShrink: 0 }}>►</span>
                            {r}
                        </div>
                    ))}
                    {(data.rule_flags || []).length > 0 && (
                        <div style={{ marginTop: '0.875rem' }}>
                            <div className="text-xs text-muted" style={{ marginBottom: '0.5rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Rule Flags</div>
                            {data.rule_flags.map((f, i) => (
                                <div key={i} className="alert alert-warn" style={{ marginBottom: '0.5rem', padding: '0.5rem 0.75rem', fontSize: '0.75rem' }}>
                                    <AlertTriangle size={13} /> {f}
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Five Cs */}
                <div className="card" style={{ gridColumn: '1 / span 2' }}>
                    <div className="card-header"><div className="card-title"><span className="icon">⚖️</span> The Five Cs of Credit</div></div>
                    <div className="grid-3" style={{ gap: '1rem' }}>
                        {[
                            { c: 'Character', icon: '🧑‍💼', content: `Research risk: ${((data.research_data?.overall_research_risk || 0) * 100).toFixed(0)}%. Court cases: ${data.research_data?.court_cases?.length || 0}. MCA status: ${data.research_data?.mca?.status || 'N/A'}.` },
                            { c: 'Capacity', icon: '💪', content: `DSCR: ${data.financial_ratios?.dscr?.toFixed(2) || '—'}. Interest Coverage: ${data.financial_ratios?.interest_coverage?.toFixed(2) || '—'}. Avg monthly credits: ${fmt(data.bank_data?.average_monthly_credit)}.` },
                            { c: 'Capital', icon: '💹', content: `D/E Ratio: ${data.financial_ratios?.de_ratio?.toFixed(2) || '—'}. Net profit (ITR): ${fmt(data.itr_data?.net_profit)}. Gross Margin: ${data.financial_ratios?.gross_margin != null ? (data.financial_ratios.gross_margin * 100).toFixed(1) + '%' : '—'}.` },
                            { c: 'Collateral', icon: '🏠', content: `Value: ${fmt(data.collateral_value)}. LTV limit: ${fmt(data.recommended_loan_amount)}.` },
                            { c: 'Conditions', icon: '📈', content: `Reconciliation mismatch: ${data.reconciliation_data?.overall_mismatch_ratio != null ? (data.reconciliation_data.overall_mismatch_ratio * 100).toFixed(1) + '%' : '—'}. Anomalous months: ${data.reconciliation_data?.anomaly_months?.length || 0}.` },
                        ].map(({ c, icon, content }) => (
                            <div key={c} style={{ background: 'var(--bg-primary)', borderRadius: 8, padding: '1rem' }}>
                                <div style={{ fontSize: '1.25rem', marginBottom: '0.375rem' }}>{icon}</div>
                                <div className="font-semibold" style={{ fontSize: '0.875rem', marginBottom: '0.375rem', color: 'var(--text-primary)' }}>{c}</div>
                                <div className="text-xs text-secondary">{content}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Download section */}
            <div className="card" style={{ marginTop: '1.25rem', textAlign: 'center' }}>
                <div style={{ fontSize: '2rem', marginBottom: '0.75rem' }}>📄</div>
                <div style={{ fontWeight: 700, fontSize: '1rem', marginBottom: '0.375rem' }}>Credit Appraisal Memo (CAM)</div>
                <div className="text-muted text-sm" style={{ marginBottom: '1.25rem' }}>
                    Full CAM document with Five Cs, financial tables, SHAP chart, and recommendation ready for download.
                </div>
                <a href={camUrl} download className="btn btn-primary" style={{ fontSize: '1rem', padding: '0.75rem 2rem' }}>
                    <Download size={18} /> Download CAM (PDF/DOCX)
                </a>
            </div>
        </div>
    )
}
