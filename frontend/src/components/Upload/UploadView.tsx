import { useCallback, useState } from 'react';
import { uploadAudio } from '../../api/client';
import { useJobPolling } from '../../hooks/useJobPolling';
import type { JobResult } from '../../types';
import { DropZone } from './DropZone';
import { ProgressBar } from './ProgressBar';

interface UploadViewProps {
  onDone: (result: JobResult) => void;
}

export function UploadView({ onDone }: UploadViewProps) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const { status, result, error: pollError } = useJobPolling(jobId);

  const handleFile = useCallback(async (file: File) => {
    setUploadError(null);
    setUploading(true);
    try {
      const res = await uploadAudio(file);
      setJobId(res.job_id);
    } catch (err) {
      const msg =
        err instanceof Error
          ? err.message
          : 'Błąd przesyłania pliku. Spróbuj ponownie.';
      setUploadError(msg);
    } finally {
      setUploading(false);
    }
  }, []);

  const isProcessing = !!jobId && status?.status !== 'done' && status?.status !== 'failed';
  const isBusy = uploading || isProcessing;

  if (result && status?.status === 'done') {
    onDone(result);
    return null;
  }

  const error = uploadError ?? pollError;

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-950 p-6">
      <div className="w-full max-w-xl space-y-8">
        <header className="text-center">
          <h1 className="text-3xl font-bold tracking-tight text-white">
            DJ Intro/Outro Generator
          </h1>
          <p className="mt-2 text-gray-400">
            Wgraj utwór, aby wygenerować profesjonalne intro i outro
          </p>
        </header>

        <DropZone onFile={handleFile} disabled={isBusy} />

        {uploading && (
          <p className="text-center text-sm text-violet-400">Przesyłanie pliku...</p>
        )}

        {status && (status.status === 'processing' || status.status === 'queued') && (
          <div className="rounded-xl bg-gray-900 p-5">
            <ProgressBar
              progress={status.progress}
              currentStep={status.current_step}
            />
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="rounded-xl border border-red-900 bg-red-950/60 px-5 py-4 text-sm text-red-300"
          >
            <strong className="block font-semibold">Błąd</strong>
            {error}
            <button
              className="mt-3 block text-xs text-red-400 underline hover:text-red-300"
              onClick={() => {
                setJobId(null);
                setUploadError(null);
              }}
            >
              Spróbuj ponownie
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
