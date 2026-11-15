import {
  AuthTokens,
  Conversation,
  DocumentItem,
  DocumentListResponse,
  LoginResponse,
  Citation,
  ChatCompletionRequest,
} from '../types';

const API_BASE = ((import.meta as any).env?.VITE_API_BASE_URL ? (import.meta as any).env.VITE_API_BASE_URL.replace(/\/$/, '') : '') + '/api/v1';

class ApiClient {
  private accessToken: string | null = null;
  private refreshToken: string | null = null;

  constructor() {
    this.accessToken = localStorage.getItem('access_token');
    this.refreshToken = localStorage.getItem('refresh_token');
  }

  public setTokens(tokens: AuthTokens | null) {
    if (tokens) {
      this.accessToken = tokens.access_token;
      this.refreshToken = tokens.refresh_token;
      localStorage.setItem('access_token', tokens.access_token);
      localStorage.setItem('refresh_token', tokens.refresh_token);
    } else {
      this.accessToken = null;
      this.refreshToken = null;
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
    }
  }

  public getAccessToken(): string | null {
    return this.accessToken;
  }

  private async refreshAccessToken(): Promise<string | null> {
    if (!this.refreshToken) return null;
    try {
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: this.refreshToken }),
      });

      if (!response.ok) {
        this.setTokens(null);
        return null;
      }

      const data = await response.json();
      this.setTokens({
        access_token: data.access_token,
        refresh_token: data.refresh_token || this.refreshToken,
        token_type: data.token_type,
        expires_in: data.expires_in,
      });
      return data.access_token;
    } catch {
      this.setTokens(null);
      return null;
    }
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    retry = true
  ): Promise<T> {
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    if (this.accessToken && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (response.status === 401 && retry) {
      const newToken = await this.refreshAccessToken();
      if (newToken) {
        headers['Authorization'] = `Bearer ${newToken}`;
        return this.request<T>(endpoint, { ...options, headers }, false);
      } else {
        throw new Error('Session expired. Please log in again.');
      }
    }

    if (!response.ok) {
      let errorMessage = `Request failed with status ${response.status}`;
      try {
        const errorData = await response.json();
        errorMessage = errorData.detail || errorData.message || errorMessage;
      } catch {
        // use fallback status
      }
      throw new Error(errorMessage);
    }

    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
  }

  // --- Auth Endpoints ---
  public async login(
    organizationSlug: string,
    email: string,
    password: string
  ): Promise<LoginResponse> {
    const tokenData = await this.request<AuthTokens>('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        organization_slug: organizationSlug,
        email,
        password,
      }),
    });
    this.setTokens(tokenData);

    const user = await this.getCurrentUser();
    const organization = {
      id: user.organization_id,
      name: organizationSlug
        .split('-')
        .map((w: string) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(' '),
      slug: organizationSlug,
      is_active: true,
    };

    return {
      tokens: tokenData,
      user,
      organization,
    };
  }

  public async logout(): Promise<void> {
    if (this.refreshToken) {
      try {
        await this.request('/auth/logout', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: this.refreshToken }),
        });
      } catch {
        // ignore logout errors on backend
      }
    }
    this.setTokens(null);
  }

  public async getCurrentUser(): Promise<any> {
    return this.request('/auth/me');
  }

  // --- Document Endpoints ---
  public async getDocuments(
    page = 1,
    pageSize = 20,
    departmentId?: string
  ): Promise<DocumentListResponse> {
    const params = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
    });
    if (departmentId) params.append('department_id', departmentId);
    return this.request<DocumentListResponse>(`/documents?${params.toString()}`);
  }

  public async getDocument(documentId: string): Promise<DocumentItem> {
    return this.request<DocumentItem>(`/documents/${documentId}`);
  }

  public async getDocumentStatus(documentId: string): Promise<any> {
    return this.request(`/documents/${documentId}/status`);
  }

  public async uploadDocument(
    file: File,
    departmentId?: string,
    onProgress?: (percent: number) => void
  ): Promise<DocumentItem> {
    const formData = new FormData();
    formData.append('file', file);
    if (departmentId) {
      formData.append('department_id', departmentId);
    }

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${API_BASE}/documents/upload`);

      if (this.accessToken) {
        xhr.setRequestHeader('Authorization', `Bearer ${this.accessToken}`);
      }

      if (xhr.upload && onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            const percent = Math.round((e.loaded / e.total) * 100);
            onProgress(percent);
          }
        };
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const result = JSON.parse(xhr.responseText);
            resolve(result);
          } catch (err) {
            reject(new Error('Invalid response from server'));
          }
        } else {
          try {
            const error = JSON.parse(xhr.responseText);
            reject(new Error(error.detail || `Upload failed (${xhr.status})`));
          } catch {
            reject(new Error(`Upload failed (${xhr.status})`));
          }
        }
      };

      xhr.onerror = () => reject(new Error('Network error during upload'));
      xhr.send(formData);
    });
  }

  public async deleteDocument(documentId: string): Promise<void> {
    await this.request(`/documents/${documentId}`, {
      method: 'DELETE',
    });
  }

  // --- Chat Endpoints ---
  public async getConversations(): Promise<Conversation[]> {
    return this.request<Conversation[]>('/chat/conversations');
  }

  public async getConversation(id: string): Promise<Conversation> {
    return this.request<Conversation>(`/chat/conversations/${id}`);
  }

  public async createConversation(title?: string): Promise<Conversation> {
    return this.request<Conversation>('/chat/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: title || 'New Conversation' }),
    });
  }

  // --- SSE Streaming Chat Completion ---
  public async streamChatCompletion(
    payload: ChatCompletionRequest,
    callbacks: {
      onToken: (token: string) => void;
      onCitations: (citations: Citation[]) => void;
      onDone: (data: { conversation_id: string; message_id: string }) => void;
      onError: (err: Error) => void;
    }
  ): Promise<void> {
    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (this.accessToken) {
        headers['Authorization'] = `Bearer ${this.accessToken}`;
      }

      const response = await fetch(`${API_BASE}/chat/completions`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ ...payload, stream: true }),
      });

      if (!response.ok) {
        let errText = `Chat request failed: ${response.status}`;
        try {
          const errData = await response.json();
          errText = errData.detail || errText;
        } catch {
          // ignore
        }
        throw new Error(errText);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('Streaming response body is undefined');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let currentEvent = 'message';
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) {
            currentEvent = 'message';
            continue;
          }

          if (trimmed.startsWith('event:')) {
            currentEvent = trimmed.replace('event:', '').trim();
            continue;
          }

          if (trimmed.startsWith('data:')) {
            const dataStr = trimmed.replace('data:', '').trim();
            if (currentEvent === 'token') {
              try {
                const parsed = JSON.parse(dataStr);
                callbacks.onToken(parsed.token !== undefined ? parsed.token : dataStr);
              } catch {
                callbacks.onToken(dataStr);
              }
            } else if (currentEvent === 'citations') {
              try {
                const parsed = JSON.parse(dataStr);
                const citationList = Array.isArray(parsed) ? parsed : (parsed.citations || []);
                callbacks.onCitations(citationList);
              } catch (e) {
                console.error('Failed to parse citations event:', e);
              }
            } else if (currentEvent === 'done') {
              try {
                const doneData = JSON.parse(dataStr);
                callbacks.onDone(doneData);
              } catch {
                callbacks.onDone({ conversation_id: payload.conversation_id || '', message_id: '' });
              }
            }
          }
        }
      }
    } catch (err: any) {
      callbacks.onError(err);
    }
  }
}

export const api = new ApiClient();
