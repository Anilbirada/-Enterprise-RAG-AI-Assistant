export type UserRole = 'SUPER_ADMIN' | 'ORG_ADMIN' | 'KNOWLEDGE_MANAGER' | 'EMPLOYEE';

export interface User {
  id: string;
  email: string;
  full_name?: string;
  first_name?: string;
  last_name?: string;
  role: UserRole;
  organization_id: string;
  department_id?: string | null;
  is_active: boolean;
  created_at: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
}

export interface Department {
  id: string;
  name: string;
  organization_id: string;
  description?: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginResponse {
  tokens: AuthTokens;
  user: User;
  organization: Organization;
}

export type DocumentStatus = 'UPLOADED' | 'PARSING' | 'CHUNKING' | 'EMBEDDING' | 'COMPLETED' | 'FAILED';

export interface DocumentItem {
  id: string;
  organization_id: string;
  department_id?: string | null;
  uploaded_by_id: string;
  title: string;
  file_type: string;
  file_size: number;
  status: DocumentStatus;
  current_version_id?: string | null;
  total_chunks?: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: DocumentItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface Citation {
  chunk_id: string;
  document_id: string;
  document_title: string;
  page_number?: number | null;
  snippet: string;
  score?: number;
  citation_number?: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  citations?: Citation[];
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  organization_id: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  messages?: Message[];
}

export type SearchMode = 'hybrid' | 'dense';

export interface ChatCompletionRequest {
  conversation_id?: string;
  message: string;
  search_mode?: SearchMode;
  dense_weight?: number;
  sparse_weight?: number;
  department_id?: string | null;
  stream?: boolean;
}
