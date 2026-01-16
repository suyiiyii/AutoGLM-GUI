/**
 * WebCodecs API availability detection utilities
 */

/**
 * Detect the specific reason why WebCodecs API is unavailable
 * @returns The unavailability reason, or null if WebCodecs is available
 */
export function detectWebCodecsUnavailabilityReason(): string | null {
  // Check if running in browser environment
  if (typeof window === 'undefined') {
    return 'browser_unsupported';
  }

  // Check if VideoDecoder is available
  if (!window.VideoDecoder) {
    return 'browser_unsupported';
  }

  // Check if running in secure context (HTTPS or localhost)
  if (!window.isSecureContext) {
    return 'insecure_context';
  }

  return null;
}

// SessionStorage key for tracking dismissed warnings
const WEBCODECS_WARNING_KEY = 'webcodecs_warning_dismissed';

/**
 * Check if the WebCodecs warning should be shown to the user
 * @returns true if the warning should be shown, false if it was dismissed
 */
export function shouldShowWebCodecsWarning(): boolean {
  return !sessionStorage.getItem(WEBCODECS_WARNING_KEY);
}

/**
 * Mark the WebCodecs warning as dismissed for the current session
 */
export function dismissWebCodecsWarning(): void {
  sessionStorage.setItem(WEBCODECS_WARNING_KEY, 'true');
}
