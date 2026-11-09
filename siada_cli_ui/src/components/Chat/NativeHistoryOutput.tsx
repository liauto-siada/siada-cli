import React, { useRef } from 'react';
import { Box, Static } from '@jrichman/ink';
import { Banner, type BannerProps } from '../Banner/Banner.js';
import { ConversationBlock, conversationBlocks } from './ConversationViewport.js';
import type { NativeHistoryChunk } from '../../utils/nativeHistory.js';

const ignoreMeasurement = () => {};

/** One Static node owns scrollback for the entire UI lifetime, including overlays. */
export function NativeHistoryOutput({
  chunks, banner, width, isCollapsed, presentation, ready,
}: {
  chunks: NativeHistoryChunk[];
  banner: BannerProps;
  width: number;
  isCollapsed: boolean;
  presentation: boolean;
  ready: boolean;
}) {
  const initialBanner = useRef<BannerProps | null>(null);
  if (!initialBanner.current && ready) initialBanner.current = banner;
  return <Static items={initialBanner.current ? [null, ...chunks] : chunks}>
    {(chunk) => chunk === null
      ? <Box key="native-banner" width={width} flexDirection="column">
          <Banner {...initialBanner.current!} interactive={false} />
        </Box>
      : <Box key={chunk.id} width={width} flexDirection="column">
          {conversationBlocks([chunk.message], presentation).map(block =>
            <ConversationBlock key={block.id} block={{
              ...block,
              continuation: block.continuation || chunk.continuation,
              gapAfter: !chunk.complete ? 0 : block.gapAfter,
            }} width={width} collapsed={isCollapsed} presentation={presentation}
              hovered={false} onMeasure={ignoreMeasurement}
              onHeadingRef={ignoreMeasurement} onBlockRef={ignoreMeasurement} />,
          )}
        </Box>}
  </Static>;
}