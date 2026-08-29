import { useParams } from 'react-router-dom';
import { Layers } from 'lucide-react';
import EmptyState from '../components/common/EmptyState';

// Placeholder until Phase 5 builds the freeform corkboard. The route exists now
// so the sidebar link is live and navigation can be exercised.

export default function CorkboardPage() {
  useParams();
  return (
    <div className="workspace-page">
      <header className="workspace-head">
        <h1 className="stamp-font">Evidence board</h1>
        <p>Pin hypotheses, suspects and case files; cord the connections.</p>
      </header>
      <EmptyState
        icon={<Layers size={26} />}
        title="Board under construction"
        message="The freeform corkboard lands in the next iteration. Hypotheses logged from the workspace will appear here as index cards."
      />
    </div>
  );
}
