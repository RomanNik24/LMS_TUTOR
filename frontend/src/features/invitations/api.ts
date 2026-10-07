/** Приглашения учеников и сотрудников (docs/08 §5.2–§5.3). Ссылка показывается один раз. */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { unwrap, unwrapEmpty } from "@/api/errors";

export type InviteTarget = { kind: "student" | "staff"; id: number };

export function useIssueInvitation(target: InviteTarget) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      target.kind === "student"
        ? unwrap(
            await api.POST("/api/v1/admin/students/{student_id}/invitations", {
              params: { path: { student_id: target.id } },
            }),
          )
        : unwrap(
            await api.POST("/api/v1/admin/staff/{staff_id}/invitations", {
              params: { path: { staff_id: target.id } },
            }),
          ),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: [target.kind === "student" ? "students" : "staff"],
      }),
  });
}

export function useRevokeInvitation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (invitationId: number) => {
      unwrapEmpty(
        await api.DELETE("/api/v1/admin/invitations/{invitation_id}", {
          params: { path: { invitation_id: invitationId } },
        }),
      );
    },
    onSuccess: () => queryClient.invalidateQueries(),
  });
}
