from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class UploadResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str                   # queued | processing | done | failed
    progress: int                 # 0-100
    current_step: Optional[str] = None
    error: Optional[str] = None


class JobResultResponse(BaseModel):
    job_id: str
    status: str
    analysis: Optional[dict] = None       # Essentia analysis
    beats: Optional[dict] = None          # allin1fix beats/structure
    harmony: Optional[dict] = None        # OMAR-RQ key/chords
    cue_points: Optional[list] = None
    variations: Optional[dict] = None     # intros/outros paths
    error: Optional[str] = None


class ReprocessRequest(BaseModel):
    trim_start: float = Field(default=0.0, ge=0.0, description="Seconds to trim from start")
    first_beat: float = Field(default=0.0, ge=0.0, description="Corrected first downbeat position (s)")
    key_shift: int = Field(default=0, ge=-12, le=12, description="Pitch shift in semitones")
    bpm_target: Optional[float] = Field(default=None, gt=0.0, description="Target BPM (None = keep original)")
    selected_intro: int = Field(default=0, ge=0, le=2, description="Intro variant index 0/1/2")
    selected_outro: int = Field(default=0, ge=0, le=2, description="Outro variant index 0/1/2")

    @field_validator("key_shift")
    @classmethod
    def warn_large_key_shift(cls, v: int) -> int:
        # Validated here so API can log it; pyrubberband will also warn at execution time
        return v
