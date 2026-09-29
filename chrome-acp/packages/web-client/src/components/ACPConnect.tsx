// Re-export from shared with PWA-specific configuration
import { ACPConnect as SharedACPConnect } from "@chrome-acp/shared/components";
import type { ACPClient } from "@chrome-acp/shared/acp";

interface ACPConnectProps {
  onClientReady?: (client: ACPClient | null) => void;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
  /** Connect automatically on mount (e.g. when a share link provides a token). */
  autoConnect?: boolean;
}

export function ACPConnect({ onClientReady, expanded, onExpandedChange, autoConnect }: ACPConnectProps) {
  return (
    <SharedACPConnect
      onClientReady={onClientReady}
      expanded={expanded}
      onExpandedChange={onExpandedChange}
      showTokenInput
      inferFromUrl
      showScanButton
      autoConnect={autoConnect}
    />
  );
}
