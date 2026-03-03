import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getResults } from '../api/client.js'
import { BarChart2, AlertTriangle } from 'lucide-react'

const Section = ({ title, icon, children }) => (
    <div className="card mb-4" style={{ marginBottom: '1.25rem' }}>
        <div className="card-header">
            <div className="card-title"><span className="icon">{icon}</span> {title}</div>
        </div>
        {children}
    </div>
)

const KV = ({ label, value }) => (
    <div className="flex justify-between" style={{ padding: '0.5rem 0', borderBottom: '1px solid rgba(42,53,82,0.4)', fontSize: '0.8125rem' }}>
        <span className="text-muted">{label}</span>
        <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>{value ?? '—'}</span>
    </div>
)

const fmt = (n) => n != null ? `₹${Number(n).toLocaleString('en-IN')}` : '—'
const pct = (n) => n != null ? `${(Number(n) * 100).toFixed(1)}%` : '—'

export default function ReviewPage() {
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

    if (!data) return <div className="alert alert-danger">Not found.</div>

    const gst = data.gst_data || {}
    const bank = data.bank_data || {}
    const itr = data.itr_data || {}
    const recon = data.reconciliation_data || {}

    return (
        <div>
            <div className="flex items-center justify-between mb-4" style={{ marginBottom: '1.5rem' }}>
                <div>
                    <div className="page-title">Data Review — {data.company_name}</div>
                    <div className="page-sub" style={{ marginBottom: 0 }}>Parsed financial data from uploaded documents</div>
                </div>
                <button className="btn btn-primary" onClick={() => navigate(`/applications/${id}/dashboard`)}>
                    <BarChart2 size={14} /> Risk Dashboard
                </button>
            </div>

            <div className="grid-2" style={{ gap: '1.25rem', alignItems: 'start' }}>
                {/* GST Summary */}
                <Section title="GST Returns Summary" icon="📊">
                    <KV label="GSTIN" value={gst.gstin} />
                    <KV label="Total Taxable Sales" value={fmt(gst.total_taxable_sales)} />
                    <KV label="Total IGST" value={fmt(gst.total_igst)} />
                    <KV label="Total CGST" value={fmt(gst.total_cgst)} />
                    <KV label="Total SGST" value={fmt(gst.total_sgst)} />
                    <KV label="Total Tax" value={fmt(gst.total_tax)} />
                    <KV label="Invoices / Rows" value={gst.num_invoices} />
                    {gst.monthly_sales && Object.keys(gst.monthly_sales).length > 0 && (
                        <>
                            <div className="text-xs text-muted" style={{ marginTop: '0.75rem', marginBottom: '0.375rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Monthly Sales Breakdown</div>
                            <div className="table-container">
                                <table>
                                    <thead><tr><th>Month</th><th>Sales (₹)</th></tr></thead>
                                    <tbody>
                                        {Object.entries(gst.monthly_sales).slice(0, 12).map(([m, v]) => (
                                            <tr key={m}><td>{m}</td><td>{Number(v).toLocaleString('en-IN')}</td></tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </>
                    )}
                </Section>

                {/* ITR Summary */}
                <Section title="Income Tax Return Summary" icon="🧾">
                    <KV label="PAN" value={itr.pan} />
                    <KV label="Assessment Year" value={itr.assessment_year} />
                    <KV label="Gross Total Income" value={fmt(itr.gross_total_income)} />
                    <KV label="Business Income" value={fmt(itr.business_income)} />
                    <KV label="Turnover" value={fmt(itr.turnover)} />
                    <KV label="Net Profit" value={fmt(itr.net_profit)} />
                    <KV label="Total Deductions" value={fmt(itr.total_deductions)} />
                    <KV label="Tax Paid" value={fmt(itr.tax_paid)} />
                    <KV label="Depreciation" value={fmt(itr.depreciation)} />
                </Section>

                {/* Bank Summary */}
                <Section title="Bank Statement Summary" icon="🏦">
                    <KV label="Total Credits" value={fmt(bank.total_credits)} />
                    <KV label="Total Debits" value={fmt(bank.total_debits)} />
                    <KV label="Avg Monthly Credit" value={fmt(bank.average_monthly_credit)} />
                    <KV label="Opening Balance" value={fmt(bank.opening_balance)} />
                    <KV label="Closing Balance" value={fmt(bank.closing_balance)} />
                    <KV label="Transactions Parsed" value={bank.transaction_count} />
                    {bank.transactions_sample?.length > 0 && (
                        <>
                            <div className="text-xs text-muted" style={{ marginTop: '0.75rem', marginBottom: '0.375rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Recent Transactions (sample)</div>
                            <div className="table-container">
                                <table>
                                    <thead><tr><th>Date</th><th>Narration</th><th>Type</th><th>Amount (₹)</th></tr></thead>
                                    <tbody>
                                        {bank.transactions_sample.slice(0, 10).map((t, i) => (
                                            <tr key={i}>
                                                <td className="text-xs">{t.date}</td>
                                                <td className="truncate" style={{ maxWidth: 180, fontSize: '0.75rem' }}>{t.narration}</td>
                                                <td>
                                                    <span className={`badge ${t.type === 'credit' ? 'badge-success' : 'badge-danger'}`} style={{ fontSize: '0.65rem' }}>
                                                        {t.type}
                                                    </span>
                                                </td>
                                                <td>{Number(t.amount).toLocaleString('en-IN')}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </>
                    )}
                </Section>

                {/* Reconciliation */}
                <Section title="GST-Bank Reconciliation" icon="⚖️">
                    {recon.risk_flag && (
                        <div className="alert alert-danger" style={{ marginBottom: '0.875rem' }}>
                            <AlertTriangle size={14} /> {recon.summary}
                        </div>
                    )}
                    {!recon.risk_flag && recon.summary && (
                        <div className="alert alert-success" style={{ marginBottom: '0.875rem', fontSize: '0.8rem' }}>
                            ✓ {recon.summary}
                        </div>
                    )}
                    <KV label="Total GST Sales" value={fmt(recon.total_gst_sales)} />
                    <KV label="Total Bank Credits" value={fmt(recon.total_bank_credits)} />
                    <KV label="Overall Mismatch" value={pct(recon.overall_mismatch_ratio)} />
                    <KV label="Anomalous Months" value={recon.anomaly_months?.join(', ') || 'None'} />
                    {recon.monthly_breakdown?.length > 0 && (
                        <>
                            <div className="text-xs text-muted" style={{ marginTop: '0.75rem', marginBottom: '0.375rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Monthly Breakdown</div>
                            <div className="table-container">
                                <table>
                                    <thead><tr><th>Month</th><th>GST (₹)</th><th>Bank (₹)</th><th>Mismatch</th><th>Flag</th></tr></thead>
                                    <tbody>
                                        {recon.monthly_breakdown.map((r) => (
                                            <tr key={r.month} className={r.is_anomaly ? 'row-anomaly' : ''}>
                                                <td>{r.month}</td>
                                                <td>{Number(r.gst_sales).toLocaleString('en-IN')}</td>
                                                <td>{Number(r.bank_credits).toLocaleString('en-IN')}</td>
                                                <td style={{ color: r.is_anomaly ? 'var(--danger)' : 'var(--text-muted)' }}>{pct(r.mismatch_ratio)}</td>
                                                <td>{r.is_anomaly ? <span className="badge badge-danger" style={{ fontSize: '0.65rem' }}>⚠</span> : <span className="text-muted">—</span>}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </>
                    )}
                </Section>
            </div>
        </div>
    )
}
