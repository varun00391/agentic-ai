export function formatMoney(
  totalMinorUnits: number | null,
  currency: string | null,
): string {
  if (totalMinorUnits === null) {
    return "—";
  }
  const amount = (totalMinorUnits / 100).toFixed(2);
  return currency ? `${currency} ${amount}` : amount;
}

export function formatCategory(category: string | null): string {
  if (!category) {
    return "—";
  }
  return category.replaceAll("_", " ");
}

export function formatDisplayDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  const iso = value.length <= 10 ? `${value}T00:00:00` : value;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function formatPolicy(value: string | null): string {
  if (!value) {
    return "—";
  }
  const labels: Record<string, string> = {
    auto_accept: "Approved",
    review_required: "Needs review",
    reject: "Not approved",
    rejected: "Not approved",
  };
  return labels[value] ?? value.replaceAll("_", " ");
}

export function formatToolName(tool: string): string {
  const labels: Record<string, string> = {
    archive_receipt: "Archive original file",
    extract_document_text: "Read document text",
    extract_expense_fields: "Extract bill fields",
    normalize_expense: "Normalize amounts",
    validate_expense: "Validate totals",
    categorize_expense: "Assign category",
    check_duplicate: "Check for duplicates",
    evaluate_policy: "Check policy",
    build_final_result: "Prepare result",
    save_result: "Save to ledger",
  };
  return labels[tool] ?? tool.replaceAll("_", " ");
}

export function statusClass(status: string): string {
  switch (status) {
    case "accepted":
    case "succeeded":
      return "bg-emerald-950 text-emerald-50";
    case "needs_review":
    case "running":
      return "bg-amber-100 text-amber-950";
    case "duplicate":
      return "bg-sky-100 text-sky-950";
    case "failed":
    case "dead_letter":
      return "bg-rose-100 text-rose-950";
    default:
      return "bg-stone-200 text-stone-800";
  }
}
