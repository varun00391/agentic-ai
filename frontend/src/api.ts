import type {
  ExpenseDetail,
  JobDetail,
  JobSummary,
  MeResponse,
  TokenResponse,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function errorMessage(payload: unknown, fallback: string): string {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return fallback;
}

async function request<T>(
  path: string,
  options: RequestInit & { token?: string; organizationId?: string } = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }
  if (options.organizationId) {
    headers.set("X-Organization-Id", options.organizationId);
  }
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(payload, response.statusText));
  }
  return payload as T;
}

export const api = {
  signup(body: {
    email: string;
    password: string;
    display_name: string;
    organization_name: string;
  }) {
    return request<TokenResponse>("/api/v2/auth/signup", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  login(email: string, password: string) {
    return request<TokenResponse>("/api/v2/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },
  me(token: string) {
    return request<MeResponse>("/api/v2/me", { token });
  },
  uploadReceipts(token: string, organizationId: string, files: File[]) {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    return request<{ batch_id: string; jobs: JobSummary[] }>("/api/v2/receipts", {
      method: "POST",
      token,
      organizationId,
      body,
    });
  },
  getJob(token: string, organizationId: string, jobId: string) {
    return request<JobDetail>(`/api/v2/jobs/${jobId}`, { token, organizationId });
  },
  listExpenses(token: string, organizationId: string) {
    return request<{ items: ExpenseDetail[] }>("/api/v2/expenses", {
      token,
      organizationId,
    });
  },
  getExpense(token: string, organizationId: string, expenseId: string) {
    return request<ExpenseDetail>(`/api/v2/expenses/${expenseId}`, {
      token,
      organizationId,
    });
  },
};
