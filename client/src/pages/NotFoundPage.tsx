import { Link } from 'react-router-dom';
import EmptyState from '../components/common/EmptyState';

export default function NotFoundPage() {
  return (
    <EmptyState
      title="No file here"
      message="That page isn't part of the case system."
      action={
        <Link to="/cases" className="btn-primary" style={{ textDecoration: 'none' }}>
          Back to cases
        </Link>
      }
    />
  );
}
