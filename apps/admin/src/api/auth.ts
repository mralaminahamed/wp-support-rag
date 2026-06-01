// Auth API calls: login, logout, me, register, acceptInvite, forgotPassword, resetPassword.
// Author: Al Amin Ahamed.
import type {
  AcceptInviteRequest,
  AuthUser,
  ChangePasswordRequest,
  CreateRoleRequest,
  CreateUserRequest,
  ForgotPasswordRequest,
  InviteRequest,
  InviteResponse,
  LoginRequest,
  PatchRoleRequest,
  PatchUserRequest,
  RegisterRequest,
  ResetPasswordRequest,
  RoleSummary,
  UserListItem,
} from "@/types/api";
import { apiClient } from "./client";

export async function login(payload: LoginRequest): Promise<AuthUser> {
  const res = await apiClient.post<AuthUser>("/api/v1/auth/login", payload);
  return res.data;
}

export async function logout(): Promise<void> {
  await apiClient.post("/api/v1/auth/logout");
}

export async function getMe(): Promise<AuthUser> {
  const res = await apiClient.get<AuthUser>("/api/v1/auth/me");
  return res.data;
}

export async function register(payload: RegisterRequest): Promise<AuthUser> {
  const res = await apiClient.post<AuthUser>("/api/v1/auth/register", payload);
  return res.data;
}

export async function acceptInvite(payload: AcceptInviteRequest): Promise<AuthUser> {
  const res = await apiClient.post<AuthUser>("/api/v1/auth/accept-invite", payload);
  return res.data;
}

export async function forgotPassword(payload: ForgotPasswordRequest): Promise<void> {
  await apiClient.post("/api/v1/auth/forgot-password", payload);
}

export async function resetPassword(payload: ResetPasswordRequest): Promise<void> {
  await apiClient.post("/api/v1/auth/reset-password", payload);
}

export async function changePassword(payload: ChangePasswordRequest): Promise<AuthUser> {
  const res = await apiClient.patch<AuthUser>("/api/v1/auth/me/password", payload);
  return res.data;
}

// User management
export async function listUsers(): Promise<UserListItem[]> {
  const res = await apiClient.get<UserListItem[]>("/api/v1/admin/users");
  return res.data;
}

export async function createUser(payload: CreateUserRequest): Promise<AuthUser> {
  const res = await apiClient.post<AuthUser>("/api/v1/admin/users", payload);
  return res.data;
}

export async function patchUser(id: string, payload: PatchUserRequest): Promise<AuthUser> {
  const res = await apiClient.patch<AuthUser>(`/api/v1/admin/users/${id}`, payload);
  return res.data;
}

export async function deleteUser(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/admin/users/${id}`);
}

export async function inviteUser(payload: InviteRequest): Promise<InviteResponse> {
  const res = await apiClient.post<InviteResponse>("/api/v1/admin/users/invite", payload);
  return res.data;
}

// Role management
export async function listRoles(): Promise<RoleSummary[]> {
  const res = await apiClient.get<RoleSummary[]>("/api/v1/admin/roles");
  return res.data;
}

export async function createRole(payload: CreateRoleRequest): Promise<RoleSummary> {
  const res = await apiClient.post<RoleSummary>("/api/v1/admin/roles", payload);
  return res.data;
}

export async function patchRole(id: string, payload: PatchRoleRequest): Promise<RoleSummary> {
  const res = await apiClient.patch<RoleSummary>(`/api/v1/admin/roles/${id}`, payload);
  return res.data;
}

export async function deleteRole(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/admin/roles/${id}`);
}
