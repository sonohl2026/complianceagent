import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";

/** Renaming a product is sticky on the backend (products.py::rename_product
 * sets name_manually_set) -- a future completed scan won't silently
 * overwrite it. Shared by the Products list and a product's own results
 * page, the two places a rename was asked for. */
export function RenameProductControl({
  productId,
  currentName,
  size = "sm",
  onEditingChange,
}: {
  productId: string;
  currentName: string;
  size?: "sm" | "lg";
  onEditingChange?: (editing: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(currentName);

  const setEditingState = (next: boolean) => {
    setEditing(next);
    onEditingChange?.(next);
  };

  const renameMutation = useMutation({
    mutationFn: () => api.patch(`/products/${productId}`, { name: value.trim() }),
    onSuccess: () => {
      setEditingState(false);
      queryClient.invalidateQueries({ queryKey: ["products"] });
      queryClient.invalidateQueries({ queryKey: ["product", productId] });
    },
  });

  const startEditing = () => {
    setValue(currentName);
    setEditingState(true);
  };

  if (!editing) {
    return (
      <button
        onClick={startEditing}
        title="Rename"
        className={
          size === "lg"
            ? "text-xs rounded border border-slate-300 dark:border-slate-700 px-2 py-1 hover:bg-slate-100 dark:hover:bg-slate-900"
            : "text-xs text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 underline decoration-dotted"
        }
      >
        Rename
      </button>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5">
      <input
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && value.trim()) renameMutation.mutate();
          if (e.key === "Escape") setEditingState(false);
        }}
        className="rounded border border-slate-300 dark:border-slate-700 bg-transparent px-2 py-1 text-sm"
      />
      <button
        disabled={!value.trim() || renameMutation.isPending}
        onClick={() => renameMutation.mutate()}
        className="text-xs rounded bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-2 py-1 disabled:opacity-50"
      >
        Save
      </button>
      <button onClick={() => setEditingState(false)} className="text-xs text-slate-500 underline">
        Cancel
      </button>
      {renameMutation.isError && (
        <span className="text-xs text-risk-critical">{(renameMutation.error as Error).message}</span>
      )}
    </span>
  );
}
