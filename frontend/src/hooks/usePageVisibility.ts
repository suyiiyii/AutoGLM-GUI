import { useEffect, useState } from 'react';

function getCurrentVisibility(): boolean {
  if (typeof document === 'undefined') {
    return true;
  }

  return document.visibilityState === 'visible';
}

export function usePageVisibility(): boolean {
  const [isVisible, setIsVisible] = useState(getCurrentVisibility);

  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsVisible(getCurrentVisibility());
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  return isVisible;
}
