/**
 * FingerprintContext - Shot Fingerprint State Management
 * Fetches and provides the user's shot fingerprint across all screens.
 */

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { useAuth } from './AuthContext';
import { getFingerprint, type ShotFingerprint } from '../lib/api';

interface FingerprintContextType {
  fingerprint: ShotFingerprint | null;
  loading: boolean;
  isReady: boolean;
  sessionsUntilReady: number;
  refreshFingerprint: () => Promise<void>;
}

const FingerprintContext = createContext<FingerprintContextType | undefined>(undefined);

export function FingerprintProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [fingerprint, setFingerprint] = useState<ShotFingerprint | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchFingerprint = useCallback(async () => {
    if (!user?.id) return;
    setLoading(true);
    try {
      const fp = await getFingerprint(user.id);
      setFingerprint(fp);
    } catch {
      setFingerprint(null);
    } finally {
      setLoading(false);
    }
  }, [user?.id]);

  // Fetch on mount when user is available
  useEffect(() => {
    if (user?.id) {
      fetchFingerprint();
    } else {
      setFingerprint(null);
    }
  }, [user?.id, fetchFingerprint]);

  const isReady = fingerprint?.fingerprint_ready ?? false;
  const sessionsUntilReady = Math.max(0, 3 - (fingerprint?.session_count ?? 0));

  const value: FingerprintContextType = {
    fingerprint,
    loading,
    isReady,
    sessionsUntilReady,
    refreshFingerprint: fetchFingerprint,
  };

  return (
    <FingerprintContext.Provider value={value}>
      {children}
    </FingerprintContext.Provider>
  );
}

export function useFingerprint(): FingerprintContextType {
  const context = useContext(FingerprintContext);
  if (context === undefined) {
    throw new Error('useFingerprint must be used within a FingerprintProvider');
  }
  return context;
}
