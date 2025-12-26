import _ from 'lodash';
import { useCallback, useRef, useState } from 'react';

export function useDebouncedState<T>(
  initialValue: T,
  delay: number
): [T, (value: T) => void] {
  const [state, setState] = useState<T>(initialValue);
  const debouncedSetState = useRef(_.debounce(setState, delay));

  const setDebouncedState = useCallback((value: T) => {
    debouncedSetState.current(value);
  }, []);

  return [state, setDebouncedState];
}
