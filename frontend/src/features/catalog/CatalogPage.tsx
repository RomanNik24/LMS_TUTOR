import { ArrowDown, ArrowUp, BookOpen, GripVertical, Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/api/errors";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { PageSkeleton } from "@/components/common/PageSkeleton";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { texts } from "@/lib/texts";
import { cn } from "@/lib/utils";

import {
  movedIds,
  useCatalog,
  useDeleteCatalogItem,
  useReorderCatalog,
  useUpdateCatalogItem,
} from "./api";
import type { CatalogItem } from "./api";
import { CatalogFormDialog } from "./CatalogFormDialog";

const t = texts.admin.catalog;

/** «Каталог услуг» (docs/07 §9.2.12): карточки витрины, публикация и порядок. */
export function CatalogPage() {
  const query = useCatalog();
  const reorder = useReorderCatalog();
  const update = useUpdateCatalogItem();
  const remove = useDeleteCatalogItem();
  const [editing, setEditing] = useState<CatalogItem | "new" | null>(null);
  const [deleting, setDeleting] = useState<CatalogItem | null>(null);
  const [dragFrom, setDragFrom] = useState<number | null>(null);

  const fail = (error: unknown) => {
    toast.error(errorMessage(error));
  };

  if (query.isPending) return <PageSkeleton />;
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
  const items = query.data;
  const move = (from: number, to: number) => {
    if (from === to || to < 0 || to >= items.length) return;
    reorder.mutate(movedIds(items, from, to), { onError: fail });
  };

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t.title}
        actions={
          <Button
            size="compact"
            onClick={() => {
              setEditing("new");
            }}
          >
            <Plus className="size-5" aria-hidden />
            {t.newItem}
          </Button>
        }
      />
      {items.length === 0 ? (
        <EmptyState icon={BookOpen} title={t.empty} description={t.emptyHint} />
      ) : (
        <>
          <p className="text-sm text-muted-foreground font-body">{t.dragHint}</p>
          <ul className="flex flex-col gap-3">
            {items.map((item, index) => (
              <li
                key={item.id}
                draggable
                onDragStart={() => {
                  setDragFrom(index);
                }}
                onDragOver={(event) => {
                  event.preventDefault();
                }}
                onDrop={() => {
                  if (dragFrom !== null) move(dragFrom, index);
                  setDragFrom(null);
                }}
                onDragEnd={() => {
                  setDragFrom(null);
                }}
              >
                <Card className={cn("flex flex-col gap-3", dragFrom === index && "opacity-60")}>
                  <div className="flex items-start gap-3">
                    <GripVertical
                      className="mt-1 size-5 shrink-0 cursor-grab text-muted-foreground"
                      aria-hidden
                    />
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <h2 className="text-base font-bold font-heading">{item.title}</h2>
                      <p className="whitespace-pre-wrap text-sm font-body">{item.description}</p>
                      <p className="text-sm text-muted-foreground font-body">
                        {item.price_text ?? t.noPrice}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "shrink-0 rounded-sm px-2 py-1 text-xs font-bold font-heading",
                        item.is_published
                          ? "bg-success-bg text-success-fg"
                          : "bg-muted text-muted-foreground",
                      )}
                    >
                      {item.is_published ? t.published : t.hidden}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="compact"
                      variant="outline"
                      disabled={index === 0}
                      aria-label={`${t.moveUp}: ${item.title}`}
                      onClick={() => {
                        move(index, index - 1);
                      }}
                    >
                      <ArrowUp className="size-5" aria-hidden />
                      {t.moveUp}
                    </Button>
                    <Button
                      size="compact"
                      variant="outline"
                      disabled={index === items.length - 1}
                      aria-label={`${t.moveDown}: ${item.title}`}
                      onClick={() => {
                        move(index, index + 1);
                      }}
                    >
                      <ArrowDown className="size-5" aria-hidden />
                      {t.moveDown}
                    </Button>
                    <Button
                      size="compact"
                      variant="outline"
                      aria-label={`${item.is_published ? t.unpublish : t.publish}: ${item.title}`}
                      loading={update.isPending && update.variables.id === item.id}
                      onClick={() => {
                        update.mutate(
                          { id: item.id, body: { is_published: !item.is_published } },
                          { onError: fail },
                        );
                      }}
                    >
                      {item.is_published ? t.unpublish : t.publish}
                    </Button>
                    <Button
                      size="compact"
                      variant="outline"
                      aria-label={`${t.edit}: ${item.title}`}
                      onClick={() => {
                        setEditing(item);
                      }}
                    >
                      {t.edit}
                    </Button>
                    <Button
                      size="compact"
                      variant="ghost"
                      aria-label={`${t.delete}: ${item.title}`}
                      onClick={() => {
                        setDeleting(item);
                      }}
                    >
                      {t.delete}
                    </Button>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        </>
      )}
      {editing !== null && (
        <CatalogFormDialog
          key={editing === "new" ? "new" : editing.id}
          item={editing === "new" ? null : editing}
          open
          onOpenChange={(open) => {
            if (!open) setEditing(null);
          }}
        />
      )}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title={t.deleteTitle(deleting?.title ?? "")}
        description={t.deleteText}
        confirmLabel={t.deleteConfirm}
        loading={remove.isPending}
        onConfirm={() => {
          if (deleting === null) return;
          remove.mutate(deleting.id, {
            onSuccess: () => {
              setDeleting(null);
            },
            onError: fail,
          });
        }}
      />
    </div>
  );
}
