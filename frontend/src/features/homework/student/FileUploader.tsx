import { FileText, Trash2 } from "lucide-react";
import { useRef, useState } from "react";

import { errorMessage } from "@/api/errors";
import { Button } from "@/components/ui/button";
import { texts } from "@/lib/texts";

import { MAX_FILES, MAX_FILE_BYTES, useDeleteSolution, useUploadSolution } from "./studentApi";
import type { SolutionFile } from "./studentApi";

const t = texts.student.homework.uploader;
const ALLOWED = /\.(jpe?g|png|heic|heif|pdf)$/i;
const ALLOWED_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/heic",
  "image/heif",
  "application/pdf",
]);

/** Проверка до отправки: тип по расширению/MIME и размер (сервер проверит содержимое сам). */
export function validateFile(file: File, currentCount: number): string | null {
  if (currentCount >= MAX_FILES) return t.limitReached;
  if (!ALLOWED.test(file.name) && !ALLOWED_TYPES.has(file.type)) return t.wrongType;
  if (file.size > MAX_FILE_BYTES) return t.tooLarge;
  return null;
}

type FileUploaderProps = {
  assignmentId: number;
  files: SolutionFile[];
  disabled?: boolean;
};

/** Загрузчик файлов решения (docs/07 §6.10): список, прогресс, удаление, лимиты. */
export function FileUploader({ assignmentId, files, disabled = false }: FileUploaderProps) {
  const upload = useUploadSolution(assignmentId);
  const remove = useDeleteSolution(assignmentId);
  const input = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<{ name: string; percent: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pick = (file: File) => {
    const problem = validateFile(file, files.length);
    if (problem !== null) {
      setError(problem);
      return;
    }
    setError(null);
    setProgress({ name: file.name, percent: 0 });
    upload.mutate(
      {
        file,
        onProgress: (percent) => {
          setProgress({ name: file.name, percent });
        },
      },
      {
        onError: (failure) => {
          setError(errorMessage(failure));
        },
        onSettled: () => {
          setProgress(null);
        },
      },
    );
  };

  return (
    <div className="flex flex-col gap-3">
      {files.length > 0 && (
        <ul className="flex flex-col gap-2">
          {files.map((file) => (
            <li
              key={file.id}
              className="flex min-h-12 items-center gap-3 rounded-md border border-border px-3 font-body"
            >
              <FileText className="size-5 shrink-0 text-primary" aria-hidden />
              <span className="min-w-0 flex-1 truncate text-sm">{file.original_name}</span>
              {!disabled && (
                <Button
                  variant="ghost"
                  size="compact"
                  aria-label={texts.student.homework.removeFile(file.original_name)}
                  loading={remove.isPending && remove.variables === file.id}
                  onClick={() => {
                    setError(null);
                    remove.mutate(file.id, {
                      onError: (failure) => {
                        setError(errorMessage(failure));
                      },
                    });
                  }}
                >
                  <Trash2 className="size-5" aria-hidden />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {progress !== null && (
        <div className="flex flex-col gap-1" role="status">
          <span className="text-sm font-body">{t.uploading(progress.name, progress.percent)}</span>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full bg-primary transition-[width]"
              style={{ width: `${String(progress.percent)}%` }}
            />
          </div>
        </div>
      )}
      {!disabled && (
        <>
          <input
            ref={input}
            type="file"
            hidden
            accept="image/jpeg,image/png,image/heic,image/heif,application/pdf,.heic,.heif"
            data-testid="solution-input"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file !== undefined) pick(file);
            }}
          />
          <Button
            variant="outline"
            disabled={upload.isPending}
            onClick={() => {
              input.current?.click();
            }}
          >
            {t.add}
          </Button>
          <p className="text-sm text-muted-foreground font-body">{t.hint}</p>
        </>
      )}
      {error !== null && (
        <p role="alert" className="text-sm text-destructive font-body">
          {error}
        </p>
      )}
    </div>
  );
}
