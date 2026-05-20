import axios from 'axios';
import type { JobResult, JobStatus, ReprocessRequest, UploadResponse } from '../types';

const baseURL = '/api';

const api = axios.create({ baseURL });

export async function uploadAudio(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file);
  const { data } = await api.post<UploadResponse>('/upload', form);
  return data;
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const { data } = await api.get<JobStatus>(`/status/${jobId}`);
  return data;
}

export async function getJobResult(jobId: string): Promise<JobResult> {
  const { data } = await api.get<JobResult>(`/result/${jobId}`);
  return data;
}

export async function reprocessJob(
  jobId: string,
  corrections: ReprocessRequest,
): Promise<JobStatus> {
  const { data } = await api.post<JobStatus>(`/reprocess/${jobId}`, corrections);
  return data;
}
