import { useCallback, useRef, useState } from 'react';

const ACCEPTED_MIME = new Set([
  'audio/mpeg',
  'audio/mp3',
  'audio/wav',
  'audio/x-wav',
  'audio/flac',
  'audio/x-flac',
  'audio/aac',
  'audio/x-aac',
]);
const MAX_BYTES = 100 * 1024 * 1024;

interface DropZoneProps {
  onFile: (file: File) => void;
  disabled?: boolean;
}

export function DropZone({ onFile, disabled = false }: DropZoneProps) {
  const [dragging, setDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validate = useCallback(
    (file: File): string | null => {
      if (!ACCEPTED_MIME.has(file.type) && file.type !== '') {
        return `Nieobsługiwany format: ${file.type}. Akceptowane: MP3, WAV, FLAC, AAC.`;
      }
      if (file.size > MAX_BYTES) {
        return `Plik za duży (${(file.size / 1024 / 1024).toFixed(1)} MB). Maksimum: 100 MB.`;
      }
      return null;
    },
    [],
  );

  const handleFile = useCallback(
    (file: File) => {
      const err = validate(file);
      if (err) {
        setValidationError(err);
        return;
      }
      setValidationError(null);
      onFile(file);
    },
    [validate, onFile],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (disabled) return;
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [disabled, handleFile],
  );

  const onInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
      e.target.value = '';
    },
    [handleFile],
  );

  return (
    <div className="w-full">
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="Przeciągnij plik audio lub kliknij aby wybrać"
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => e.key === 'Enter' && !disabled && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={[
          'flex flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed px-8 py-16 transition-colors',
          disabled
            ? 'cursor-not-allowed border-gray-700 bg-gray-900 opacity-50'
            : dragging
            ? 'cursor-copy border-violet-400 bg-violet-950'
            : 'cursor-pointer border-gray-600 bg-gray-900 hover:border-violet-500 hover:bg-gray-800',
        ].join(' ')}
      >
        <svg
          className={`h-16 w-16 ${dragging ? 'text-violet-400' : 'text-gray-500'}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"
          />
        </svg>
        <div className="text-center">
          <p className="text-lg font-medium text-gray-200">
            {dragging ? 'Upuść plik tutaj' : 'Przeciągnij plik audio'}
          </p>
          <p className="mt-1 text-sm text-gray-400">
            lub <span className="text-violet-400 underline">wybierz z dysku</span>
          </p>
          <p className="mt-2 text-xs text-gray-500">MP3 · WAV · FLAC · AAC · maks. 100 MB</p>
        </div>
      </div>

      {validationError && (
        <p role="alert" className="mt-3 text-sm text-red-400">
          {validationError}
        </p>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="audio/mpeg,audio/wav,audio/x-wav,audio/flac,audio/x-flac,audio/aac,audio/x-aac,.mp3,.wav,.flac,.aac"
        className="hidden"
        onChange={onInputChange}
        disabled={disabled}
      />
    </div>
  );
}
