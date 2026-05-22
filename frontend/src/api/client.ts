import axios from 'axios';
import type { JobResult, JobStatus, ReprocessRequest, UploadResponse } from '../types';

const baseURL = '/api';

const api = axios.create({ baseURL });

export async function uploadAudio(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file);
  try {
    const { data } = await api.post<UploadResponse>('/upload', form);
    return data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const detail = error.response?.data?.detail;
      if (error.response?.status === 409 && detail && typeof detail === 'object') {
        const activeJobId = detail.active_job_id ?? 'unknown';
        const activeStep = detail.active_step ?? 'processing';
        const activeStatus = detail.active_status ?? 'processing';
        throw new Error(
          `Trwa już analiza innego pliku (job: ${activeJobId}, status: ${activeStatus}, krok: ${activeStep}). Poczekaj na zakończenie i spróbuj ponownie.`,
        );
      }
      if (typeof detail === 'string' && detail.trim()) {
        throw new Error(detail);
      }
    }
    throw error;
  }
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
