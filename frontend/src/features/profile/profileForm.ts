import { z } from "zod";

import { NAME_MAX_LENGTH } from "@/features/students/studentForm";
import { texts } from "@/lib/texts";

export const profileFormSchema = z.object({
  display_name: z
    .string()
    .trim()
    .min(1, texts.profile.nameRequired)
    .max(NAME_MAX_LENGTH, texts.profile.nameTooLong),
  timezone: z.string().min(1),
});

export type ProfileFormValues = z.infer<typeof profileFormSchema>;
