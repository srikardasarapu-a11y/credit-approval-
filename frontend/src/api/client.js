import axios from 'axios'

const api = axios.create({
    baseURL: '/api',
    timeout: 120000,
})

export const uploadDocuments = (formData) =>
    api.post('/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } })

export const triggerAnalysis = (appId) =>
    api.post(`/applications/${appId}/analyze`)

export const getResults = (appId) =>
    api.get(`/applications/${appId}/results`)

export const listApplications = () =>
    api.get('/applications/')

export const downloadCAM = (appId) =>
    `/api/reports/${appId}/cam`

export default api
