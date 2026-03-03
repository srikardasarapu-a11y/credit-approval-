import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { UploadCloud, FileText, CheckCircle, AlertCircle, Loader } from 'lucide-react'
import { uploadDocuments, triggerAnalysis } from '../api/client.js'

const FileDropZone = ({ label, accept, docType, file, onChange }) => {
    const [drag, setDrag] = useState(false)
    const inputRef = useRef()

    const handleDrop = (e) => {
        e.preventDefault()
        setDrag(false)
        const dropped = e.dataTransfer.files[0]
        if (dropped) onChange(docType, dropped)
    }

    return (
        <div
            className={`upload-zone ${drag ? 'drag-over' : ''} ${file ? 'has-file' : ''}`}
            onClick={() => inputRef.current.click()}
            onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
            onDragLeave={() => setDrag(false)}
            onDrop={handleDrop}
        >
            <input
                ref={inputRef}
                type="file"
                accept={accept}
                style={{ display: 'none' }}
                onChange={(e) => onChange(docType, e.target.files[0])}
            />
            <div className="upload-icon">
                {file ? '✅' : docType === 'gst_csv' ? '📊' : docType === 'itr_pdf' ? '🧾' : '🏦'}
            </div>
            <div className="upload-title">{label}</div>
            {file
                ? <div style={{ color: 'var(--success)', fontSize: '0.8rem', marginTop: '0.25rem', fontWeight: 600 }}>{file.name}</div>
                : <div className="upload-sub">Drag & drop or click to browse<br /><span style={{ fontSize: '0.7rem' }}>{accept.toUpperCase()} format</span></div>
            }
        </div>
    )
}

export default function UploadPage() {
    const navigate = useNavigate()
    const [files, setFiles] = useState({ gst_csv: null, itr_pdf: null, bank_pdf: null })
    const [meta, setMeta] = useState({ company_name: '', cin: '', gstin: '', collateral_value: '', collateral_type: 'default' })
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')
    const [step, setStep] = useState(1)

    const handleFileChange = (docType, file) => setFiles(prev => ({ ...prev, [docType]: file }))

    const handleSubmit = async () => {
        if (!meta.company_name) { setError('Company name is required.'); return }
        if (!files.gst_csv && !files.itr_pdf && !files.bank_pdf) { setError('Upload at least one document.'); return }

        setLoading(true)
        setError('')
        try {
            const fd = new FormData()
            fd.append('company_name', meta.company_name)
            if (meta.cin) fd.append('cin', meta.cin)
            if (meta.gstin) fd.append('gstin', meta.gstin)
            if (meta.collateral_value) fd.append('collateral_value', meta.collateral_value)
            fd.append('collateral_type', meta.collateral_type)
            if (files.gst_csv) fd.append('gst_csv', files.gst_csv)
            if (files.itr_pdf) fd.append('itr_pdf', files.itr_pdf)
            if (files.bank_pdf) fd.append('bank_pdf', files.bank_pdf)

            const { data: uploaded } = await uploadDocuments(fd)
            const appId = uploaded.application_id

            setStep(2)
            await triggerAnalysis(appId)
            navigate(`/applications/${appId}/dashboard`)
        } catch (e) {
            setError(e.response?.data?.detail || e.message || 'Upload failed.')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div>
            <div className="page-title">New Credit Application</div>
            <div className="page-sub">Upload financial documents to begin AI-powered credit appraisal</div>

            {/* Steps indicator */}
            <div className="flex items-center gap-3 mb-6" style={{ marginBottom: '1.75rem' }}>
                {['Company Details', 'Upload Documents', 'AI Analysis'].map((label, i) => (
                    <div key={i} className="flex items-center gap-2">
                        <div style={{
                            width: 28, height: 28, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: '0.75rem', fontWeight: 700,
                            background: step > i ? 'var(--accent)' : step === i + 1 ? 'var(--accent)' : 'var(--bg-card)',
                            border: '1px solid var(--border)', color: step >= i + 1 ? 'white' : 'var(--text-muted)'
                        }}>{i + 1}</div>
                        <span style={{ fontSize: '0.8rem', color: step >= i + 1 ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: step === i + 1 ? 600 : 400 }}>{label}</span>
                        {i < 2 && <div style={{ width: 32, height: 1, background: 'var(--border)' }} />}
                    </div>
                ))}
            </div>

            <div className="grid-2" style={{ gap: '1.5rem', alignItems: 'start' }}>
                {/* Left: Company form */}
                <div className="card">
                    <div className="card-header">
                        <div className="card-title"><span className="icon">🏢</span> Company Information</div>
                    </div>
                    <div className="form-group">
                        <label className="form-label">Company Name <span style={{ color: 'var(--danger)' }}>*</span></label>
                        <input className="form-input" placeholder="Acme Pvt Ltd" value={meta.company_name} onChange={e => setMeta(p => ({ ...p, company_name: e.target.value }))} />
                    </div>
                    <div className="form-group">
                        <label className="form-label">CIN (optional)</label>
                        <input className="form-input" placeholder="U74999DL2020PTC123456" value={meta.cin} onChange={e => setMeta(p => ({ ...p, cin: e.target.value }))} />
                    </div>
                    <div className="form-group">
                        <label className="form-label">GSTIN (optional)</label>
                        <input className="form-input" placeholder="27AABCU9603R1ZX" value={meta.gstin} onChange={e => setMeta(p => ({ ...p, gstin: e.target.value }))} />
                    </div>
                    <div className="grid-2" style={{ gap: '0.875rem' }}>
                        <div className="form-group" style={{ marginBottom: 0 }}>
                            <label className="form-label">Collateral Value (₹)</label>
                            <input className="form-input" type="number" placeholder="5000000" value={meta.collateral_value} onChange={e => setMeta(p => ({ ...p, collateral_value: e.target.value }))} />
                        </div>
                        <div className="form-group" style={{ marginBottom: 0 }}>
                            <label className="form-label">Collateral Type</label>
                            <select className="form-input" value={meta.collateral_type} onChange={e => setMeta(p => ({ ...p, collateral_type: e.target.value }))}>
                                <option value="default">Default (70% LTV)</option>
                                <option value="residential_property">Residential (75%)</option>
                                <option value="commercial_property">Commercial (65%)</option>
                                <option value="plant_and_machinery">Plant & Machinery (50%)</option>
                                <option value="fdr_liquid">FDR / Liquid (90%)</option>
                                <option value="stocks_mv">Stocks MV (60%)</option>
                            </select>
                        </div>
                    </div>
                </div>

                {/* Right: Upload zones */}
                <div className="card">
                    <div className="card-header">
                        <div className="card-title"><span className="icon">📁</span> Financial Documents</div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        <FileDropZone label="GST Returns CSV" accept=".csv" docType="gst_csv" file={files.gst_csv} onChange={handleFileChange} />
                        <FileDropZone label="Income Tax Return PDF" accept=".pdf" docType="itr_pdf" file={files.itr_pdf} onChange={handleFileChange} />
                        <FileDropZone label="Bank Statement PDF" accept=".pdf" docType="bank_pdf" file={files.bank_pdf} onChange={handleFileChange} />
                    </div>
                </div>
            </div>

            {/* Error */}
            {error && (
                <div className="alert alert-danger" style={{ marginTop: '1.25rem' }}>
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {/* Action */}
            <div className="flex items-center gap-3" style={{ marginTop: '1.5rem', justifyContent: 'flex-end' }}>
                <button className="btn btn-primary" onClick={handleSubmit} disabled={loading} style={{ minWidth: 180 }}>
                    {loading ? <><div className="spinner" /> Uploading & Analysing...</> : <><UploadCloud size={16} /> Submit for Appraisal</>}
                </button>
            </div>
        </div>
    )
}
