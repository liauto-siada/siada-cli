import React, { useEffect, useState } from 'react';
import { readFileSync } from 'node:fs';
import { Box, Text, render, useApp, useStdout } from '@jrichman/ink';
import { KeypressProvider, useKeypress } from '../src/contexts/KeypressContext.js';
import { MarkdownText } from '../src/components/common/MarkdownText.js';
import { applyMarkdownTheme } from '../src/components/markdown/theme.js';

const path = process.argv[2];
const source = path ? readFileSync(path, 'utf8') :
  'flowchart LR\n A[Input request] --> B[Collect evidence] --> C[Analyze dependencies] --> D[Find root cause] --> E[Archive result]';
applyMarkdownTheme(process.argv.includes('--light') ? 'light' : 'dark');

function Preview() {
  const { stdout } = useStdout();
  const { exit } = useApp();
  const [columns, setColumns] = useState(stdout.columns ?? 80);
  useEffect(() => {
    const resize = () => setColumns(stdout.columns ?? 80);
    stdout.on('resize', resize);
    return () => { stdout.off('resize', resize); };
  }, [stdout]);
  useKeypress(key => { if (key.name === 'escape' || key.name === 'q') exit(); });
  return <Box flexDirection="column" width={columns}>
    <Text wrap="truncate">Mermaid preview · Click ◀ / ▶ · Esc to exit</Text>
    <Box paddingLeft={2}>
      <MarkdownText content={`\`\`\`mermaid\n${source}\n\`\`\``} availableWidth={Math.max(1, columns - 2)} />
    </Box>
  </Box>;
}

render(<KeypressProvider><Preview /></KeypressProvider>);