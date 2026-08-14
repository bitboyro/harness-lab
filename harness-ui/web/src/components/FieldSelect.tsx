"use client";

import { SearchSelect, type SearchSelectOption } from "@/components/SearchSelect";

type Props = {
  options: Array<string | SearchSelectOption>;
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
};

/** Single-choice control that matches SearchSelect glass menus (not native <select>). */
export function FieldSelect({
  options,
  value,
  onChange,
  placeholder = "Choose…",
  disabled,
  className,
}: Props) {
  const normalized: SearchSelectOption[] = options.map((o) =>
    typeof o === "string" ? { id: o, label: o } : o,
  );

  return (
    <SearchSelect
      options={normalized}
      value={value || null}
      onChange={(id) => {
        if (id) onChange(id);
      }}
      allowClear={false}
      emptyLabel={placeholder}
      placeholder={placeholder}
      disabled={disabled}
      className={className}
    />
  );
}
