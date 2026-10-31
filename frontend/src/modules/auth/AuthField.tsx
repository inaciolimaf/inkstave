import type { ComponentProps } from "react";
import type { Control, FieldValues, Path } from "react-hook-form";

import { FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";

type InputProps = Pick<ComponentProps<typeof Input>, "type" | "autoComplete" | "placeholder">;

/** One labelled input of a title-page form, with its validation message. */
export function AuthField<T extends FieldValues>({
  control,
  name,
  label,
  ...input
}: { control: Control<T>; name: Path<T>; label: string } & InputProps) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input {...input} {...field} />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
