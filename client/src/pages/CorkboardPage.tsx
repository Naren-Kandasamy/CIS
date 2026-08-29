import { useEffect, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { LayoutDashboard, Layers } from 'lucide-react';
import { useCasesStore } from '../stores/casesStore';
import { deriveBoardCards, useBoardStore } from '../stores/boardStore';
import EmptyState from '../components/common/EmptyState';
import { CorkboardCanvas } from '../components/board/CorkboardCanvas';
import type { HypothesisRecord } from '../types/hypothesis';

// Phase 5: the freeform evidence corkboard. Persistent per case via
// case_board_layout:{id} (card positions / cords) + case-scoped hypotheses.
// Every hypothesis materializes as a card; pinned FIRs and suspects do too.

const NO_HYPS: HypothesisRecord[] = [];

export default function CorkboardPage() {
  const { caseId } = useParams();
  const navigate = useNavigate();

  const cases = useCasesStore((s) => s.cases);
  const fetchCases = useCasesStore((s) => s.fetchCases);
  const loadCase = useBoardStore((s) => s.loadCase);

  const layout = useBoardStore((s) => (caseId ? s.layoutByCase[caseId] : undefined));
  const hypotheses = useBoardStore((s) => (caseId ? s.hypothesesByCase[caseId] : undefined));
  const pins = useBoardStore((s) => (caseId ? s.pinsByCase[caseId] : undefined));
  const loading = useBoardStore((s) => (caseId ? s.loadingByCase[caseId] : false));

  useEffect(() => {
    if (!caseId) return;
    if (cases.length === 0) fetchCases().catch(() => {});
    loadCase(caseId).catch(() => {});
  }, [caseId, cases.length, fetchCases, loadCase]);

  const cards = useMemo(
    () => deriveBoardCards(layout, hypotheses, pins),
    [layout, hypotheses, pins],
  );

  const current = cases.find((c) => c.case_id === caseId);

  if (!caseId) return null;

  const empty = cards.length === 0;

  return (
    <div className="board-page">
      <header className="board-page-head">
        <div>
          <h1 className="stamp-font">{current?.title ?? 'Evidence board'}</h1>
          <p>Pin hypotheses, suspects and case files; cord the connections.</p>
        </div>
        <button
          type="button"
          className="btn-ghost flex items-center gap-1.5 flex-shrink-0"
          onClick={() => navigate(`/cases/${caseId}`)}
        >
          <LayoutDashboard size={14} /> Workspace
        </button>
      </header>

      <div className={`board-stage ${empty ? 'board-stage--empty' : ''}`}>
        {empty ? (
          <EmptyState
            icon={<Layers size={26} />}
            title={loading ? 'Loading the board…' : 'Nothing on the board yet'}
            message="Log a hypothesis from the workspace, or pin FIRs and suspects from a session. They land here as index cards you can arrange and cord together."
          />
        ) : (
          <CorkboardCanvas caseId={caseId} cards={cards} hypotheses={hypotheses ?? NO_HYPS} />
        )}
      </div>
    </div>
  );
}
