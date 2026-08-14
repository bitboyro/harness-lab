"use client";

type Props = {
  label: string;
  onDelete: () => Promise<void>;
  disabled?: boolean;
  className?: string;
};

export function DeleteButton({ label, onDelete, disabled, className = "" }: Props) {
  return (
    <button
      type="button"
      className={`btn btn-ghost btn-danger ${className}`.trim()}
      disabled={disabled}
      onClick={() => {
        if (!window.confirm(`Delete ${label}? This removes it from disk and cannot be undone.`)) {
          return;
        }
        void onDelete().catch((e: Error) => {
          window.alert(e.message);
        });
      }}
    >
      Delete
    </button>
  );
}
