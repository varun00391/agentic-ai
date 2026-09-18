export type Organization = {
  id: string;
  name: string;
  slug: string;
  role: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  user_id: string;
  email: string;
  display_name: string;
  organizations: Organization[];
};

export type MeResponse = {
  user_id: string;
  email: string;
  display_name: string;
  organizations: Organization[];
};

export type JobSummary = {
  job_id: string;
  receipt_id: string;
  filename: string;
  status: string;
};

export type TraceEvent = {
  step: number;
  tool: string;
  reason: string;
  success: boolean;
  observation: string;
  created_at?: string;
};

export type JobProgress = {
  step_count: number;
  current_tool: string | null;
  current_reason: string | null;
  current_arguments: Record<string, unknown>;
  merchant: string | null;
  total: string | null;
  currency: string | null;
  category: string | null;
  extraction_confidence: number | null;
  extraction_source: string | null;
  policy_decision: string | null;
  final_status: string | null;
  item_index: number;
  item_count: number;
  trace: TraceEvent[];
};

export type MerchantMemory = {
  merchant: string;
  category: string;
  updated_at: string;
};

export type OrganizationPolicy = {
  extraction_min_confidence: number;
  max_auto_accept_minor_units: number | null;
  always_review_categories: string[];
  review_all: boolean;
  merchant_memories: MerchantMemory[];
};

export type JobDetail = JobSummary & {
  batch_id: string | null;
  organization_id: string;
  attempt_count: number;
  error_message: string | null;
  expense_id: string | null;
  created_at: string;
  updated_at: string;
  progress: JobProgress;
};

export type ExpenseStatus =
  | "accepted"
  | "needs_review"
  | "duplicate"
  | "failed"
  | "rejected";

export type ExpenseDetail = {
  expense_id: string;
  organization_id: string;
  receipt_id: string;
  job_id: string;
  filename: string | null;
  merchant: string | null;
  transaction_date: string | null;
  total_minor_units: number | null;
  currency: string | null;
  category: string | null;
  status: ExpenseStatus;
  messages: string[];
  duplicate_of_expense_id: string | null;
  duplicate_match_type: string | null;
  policy_decision: string | null;
  extraction_confidence: number | null;
  extraction_source: string | null;
  step_count: number;
  trace: TraceEvent[];
  created_at: string;
};
