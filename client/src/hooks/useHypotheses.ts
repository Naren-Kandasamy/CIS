import { useCallback, useState } from 'react';
import * as api from '../lib/api';
import { useBoardStore } from '../stores/boardStore';
import type { HypothesisCheckLog, HypothesisRecord } from '../types/hypothesis';

// Phase 5: thin wrapper over the four hypothesis calls, unchanged on the wire:
//   list    → GET  /api/cases/:id/hypotheses          (case-scoped, added Phase 4)
//   create  → POST /api/cases/:id/hypotheses          (injects case_id)
//   check   → POST /api/investigation/hypothesis/:id/check
//   resolve → POST /api/investigation/hypothesis/:id/resolve
// List + create live in boardStore (shared with the workspace strip); check/
// resolve are local to the board, so their transient state stays here.

const EMPTY: HypothesisRecord[] = [];

export function useHypotheses(caseId: string) {
  const hypotheses = useBoardStore((s) => s.hypothesesByCase[caseId] ?? EMPTY);
  const fetchHypotheses = useBoardStore((s) => s.fetchHypotheses);
  const addHypothesis = useBoardStore((s) => s.addHypothesis);
  const applyHypothesis = useBoardStore((s) => s.applyHypothesis);

  const [checkLogs, setCheckLogs] = useState<Record<string, HypothesisCheckLog>>({});
  const [busyId, setBusyId] = useState<string | null>(null);

  const check = useCallback(async (hypothesisId: string) => {
    setBusyId(hypothesisId);
    try {
      const { log } = await api.checkHypothesis(hypothesisId);
      setCheckLogs((prev) => ({ ...prev, [hypothesisId]: log }));
    } finally {
      setBusyId(null);
    }
  }, []);

  const resolve = useCallback(
    async (hypothesisId: string, status: 'confirmed' | 'refuted', reason: string) => {
      setBusyId(hypothesisId);
      try {
        const { hypothesis } = await api.resolveHypothesis(hypothesisId, {
          status,
          resolved_reason: reason,
        });
        applyHypothesis(caseId, hypothesis);
      } finally {
        setBusyId(null);
      }
    },
    [caseId, applyHypothesis],
  );

  const refetch = useCallback(() => fetchHypotheses(caseId), [caseId, fetchHypotheses]);

  return { hypotheses, checkLogs, busyId, check, resolve, addHypothesis, refetch };
}
