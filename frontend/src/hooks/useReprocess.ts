import { useCallback, useEffect, useRef, useState } from 'react';
import { getJobResult, getJobStatus, reprocessJob } from '../api/client';
import type { JobResult, JobStatus, ReprocessRequest } from '../types';

type ReprocessState = 'idle' | 'submitting' | 'processing' | 'done' | 'failed';

interface UseReprocessResult {
  state: ReprocessState;
  jobStatus: JobStatus | null;
  newResult: JobResult | null;
  error: string | null;
  submit: (corrections: ReprocessRequest) => void;
  reset: () => void;
}

const POLL_MS = 3000;

export function useReprocess(jobId: string | null): UseReprocessResult {
  const [state, setState]     = useState<ReprocessState>('idle');
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [newResult, setNewResult] = useState<JobResult | null>(null);
  const [error, setError]     = useState<string | null>(null);
  const activeRef             = useRef(false);

  // Clean up polling on unmount
  useEffect(() => () => { activeRef.current = false; }, []);

  const reset = useCallback(() => {
    activeRef.current = false;
    setState('idle');
    setJobStatus(null);
    setNewResult(null);
    setError(null);
  }, []);

  const submit = useCallback(
    (corrections: ReprocessRequest) => {
      if (!jobId) return;
      activeRef.current = true;
      setState('submitting');
      setError(null);
      setNewResult(null);
      setJobStatus(null);

      async function run() {
        try {
          // Kick off reprocess
          await reprocessJob(jobId!, corrections);
          if (!activeRef.current) return;

          setState('processing');

          // Poll until done / failed
          while (activeRef.current) {
            const s = await getJobStatus(jobId!);
            if (!activeRef.current) return;
            setJobStatus(s);

            if (s.status === 'done') {
              const r = await getJobResult(jobId!);
              if (!activeRef.current) return;
              setNewResult(r);
              setState('done');
              return;
            }
            if (s.status === 'failed') {
              setError(s.error ?? 'Reprocess nie powiódł się');
              setState('failed');
              return;
            }
            // still processing — wait then loop
            await new Promise<void>((res) => setTimeout(res, POLL_MS));
          }
        } catch (err) {
          if (!activeRef.current) return;
          setError(err instanceof Error ? err.message : 'Błąd sieci');
          setState('failed');
        }
      }

      run();
    },
    [jobId],
  );

  return { state, jobStatus, newResult, error, submit, reset };
}
