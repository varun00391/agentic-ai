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

export type JobDetail = JobSummary & {
  batch_id: string | null;
  organization_id: string;
  attempt_count: number;
  error_message: string | null;
  expense_id: string | null;
  created_at: string;
  updated_at: string;
};

export type TraceEvent = {
  step: number;
  tool: string;
  reason: string;
  success: boolean;
  observation: string;
};

export type ExpenseStatus = "accepted" | "needs_review" | "duplicate" | "failed";

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
  step_count: number;
  trace: TraceEvent[];
  created_at: string;
};
