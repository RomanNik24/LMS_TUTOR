import { ChevronLeft, ChevronRight, FileText, ZoomIn, ZoomOut } from "lucide-react";
import { useState } from "react";

import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/common/ErrorState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { texts } from "@/lib/texts";
import { externalLinkProps } from "@/lib/externalLink";

import { useFileUrl } from "./api";
import type { AssignmentFile } from "./api";

const t = texts.admin.homework.review;
const ZOOM_MIN = 1;
const ZOOM_MAX = 4;
const ZOOM_STEP = 0.5;

function CurrentFile({ file, zoom }: { file: AssignmentFile; zoom: number }) {
  const query = useFileUrl(file.id);
  if (query.isPending) return <Skeleton className="h-64 w-full" />;
  if (query.isError) {
    return (
      <ErrorState
        message={errorMessage(query.error)}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  if (!file.content_type.startsWith("image/")) {
    return (
      <a
        {...externalLinkProps(query.data.url)}
        className="flex min-h-24 items-center justify-center gap-2 text-base font-semibold text-primary font-body"
      >
        <FileText className="size-6" aria-hidden />
        {t.openFile}: {file.original_name}
      </a>
    );
  }
  return (
    <div className="max-h-[70dvh] overflow-auto rounded-md bg-muted">
      <img
        src={query.data.url}
        alt={file.original_name}
        style={{ width: `${String(zoom * 100)}%`, maxWidth: "none" }}
        className="block"
      />
    </div>
  );
}

/** Просмотр файлов ученика: масштаб и перелистывание (docs/07 §9.2.9). */
export function PhotoViewer({ files }: { files: AssignmentFile[] }) {
  const [index, setIndex] = useState(0);
  const [zoom, setZoom] = useState(ZOOM_MIN);
  const current = files[index];
  if (current === undefined) return null;

  const go = (delta: number) => {
    setIndex((value) => Math.min(files.length - 1, Math.max(0, value + delta)));
    setZoom(ZOOM_MIN);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="compact"
            aria-label={t.prev}
            disabled={index === 0}
            onClick={() => {
              go(-1);
            }}
          >
            <ChevronLeft className="size-5" aria-hidden />
          </Button>
          <span className="min-w-14 text-center text-sm font-body">
            {t.fileOf(index + 1, files.length)}
          </span>
          <Button
            variant="outline"
            size="compact"
            aria-label={t.next}
            disabled={index === files.length - 1}
            onClick={() => {
              go(1);
            }}
          >
            <ChevronRight className="size-5" aria-hidden />
          </Button>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="compact"
            aria-label={t.zoomOut}
            disabled={zoom <= ZOOM_MIN}
            onClick={() => {
              setZoom((value) => Math.max(ZOOM_MIN, value - ZOOM_STEP));
            }}
          >
            <ZoomOut className="size-5" aria-hidden />
          </Button>
          <Button
            variant="outline"
            size="compact"
            aria-label={t.zoomIn}
            disabled={zoom >= ZOOM_MAX}
            onClick={() => {
              setZoom((value) => Math.min(ZOOM_MAX, value + ZOOM_STEP));
            }}
          >
            <ZoomIn className="size-5" aria-hidden />
          </Button>
        </div>
      </div>
      <CurrentFile key={current.id} file={current} zoom={zoom} />
    </div>
  );
}
