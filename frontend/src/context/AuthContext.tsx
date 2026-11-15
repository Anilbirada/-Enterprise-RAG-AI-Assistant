import React, { createContext, useContext, useEffect, useState } from 'react';
import { User, Organization, UserRole } from '../types';
import { api } from '../lib/api';

interface AuthContextType {
  user: User | null;
  organization: Organization | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (slug: string, email: string, pass: string) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (roles: UserRole | UserRole[]) => boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const initAuth = async () => {
      const token = api.getAccessToken();
      const savedUser = localStorage.getItem('auth_user');
      const savedOrg = localStorage.getItem('auth_org');

      if (token && savedUser && savedOrg) {
        try {
          setUser(JSON.parse(savedUser));
          setOrganization(JSON.parse(savedOrg));
          // Verify with backend
          const me = await api.getCurrentUser();
          if (me) {
            setUser(me);
            localStorage.setItem('auth_user', JSON.stringify(me));
          }
        } catch {
          // Token expired or invalid
          setUser(null);
          setOrganization(null);
          localStorage.removeItem('auth_user');
          localStorage.removeItem('auth_org');
        }
      }
      setIsLoading(false);
    };

    initAuth();
  }, []);

  const login = async (slug: string, email: string, pass: string) => {
    setIsLoading(true);
    try {
      const response = await api.login(slug, email, pass);
      setUser(response.user);
      setOrganization(response.organization);
      localStorage.setItem('auth_user', JSON.stringify(response.user));
      localStorage.setItem('auth_org', JSON.stringify(response.organization));
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    setIsLoading(true);
    try {
      await api.logout();
    } finally {
      setUser(null);
      setOrganization(null);
      localStorage.removeItem('auth_user');
      localStorage.removeItem('auth_org');
      setIsLoading(false);
    }
  };

  const hasRole = (roles: UserRole | UserRole[]) => {
    if (!user) return false;
    const roleList = Array.isArray(roles) ? roles : [roles];
    return roleList.includes(user.role);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        organization,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
        hasRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
