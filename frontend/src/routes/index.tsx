import { createFileRoute } from '@tanstack/react-router';
import { useEffect } from 'react';
import { useNavigate } from '@tanstack/react-router';

export const Route = createFileRoute('/')({
  component: HomeComponent,
});

export function HomeComponent() {
  const navigate = useNavigate();

  useEffect(() => {
    navigate({ to: '/chat' });
  }, [navigate]);

  return (
    <div className="p-2">
      <h3>Welcome Home!</h3>
    </div>
  );
}
