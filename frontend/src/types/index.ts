export interface UploadResponse {
  job_id: string;
  status: string;
}

export interface JobStatus {
  job_id: string;
  status: 'queued' | 'processing' | 'done' | 'failed';
  progress: number;
  current_step: string | null;
  error: string | null;
}

export interface CuePoint {
  label: string;
  time: number;
  beat: number | null;
}

export interface BeatData {
  bpm: number;
  beats: number[];
  downbeats: number[];
  phrases: number[];
  time_signature: string | null;
  first_downbeat: number;
}

export interface AnalysisData {
  bpm: number;
  bpm_confidence: number;
  key: string;
  mode: string;
  loudness_integrated: number;
  dynamic_range: number;
  duration: number;
  structure: Record<string, unknown> | null;
  waveform_data: number[][] | null;
}

export interface HarmonyData {
  key: string;
  key_root: string;
  mode: string;
  key_confidence: number;
  camelot: string;
  chord_progression: string[];
}

export interface VariationsData {
  intros: (string | null)[];
  outros: (string | null)[];
}

export interface JobResult {
  job_id: string;
  status: string;
  analysis: AnalysisData | null;
  beats: BeatData | null;
  harmony: HarmonyData | null;
  cue_points: CuePoint[] | null;
  variations: VariationsData | null;
  error: string | null;
}

export interface ReprocessRequest {
  trim_start: number;
  first_beat: number;
  key_shift: number;
  bpm_target: number | null;
  selected_intro: number;
  selected_outro: number;
}

export type AppState = 'idle' | 'uploading' | 'processing' | 'done' | 'failed';
