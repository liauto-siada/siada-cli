#!/usr/bin/env node
/**
 * Static Banner Demo
 * 
 * Demonstrates how to use Ink's Static component to render ASCII art banner
 * with gradient colors. The Static component renders content once and prevents
 * re-rendering, which is perfect for banners and headers.
 * 
 * Usage:
 *   npx tsx examples/static-banner-demo.tsx
 */

import React, { useState, useEffect } from 'react';
import { render, Box, Text, Static } from '@jrichman/ink';

// ASCII art lines - matching siada-cli output
const bannerLines = [
  "  ▆▆▆▆▆▆▆╗▆▆╗ ▆▆▆▆▆╗ ▆▆▆▆▆▆╗  ▆▆▆▆▆╗      ▆▆▆▆▆▆╗▆▆╗     ▆▆╗  ",
  "  ▆▆╔════╝▆▆║▆▆╔══▆▆╗▆▆╔══▆▆╗▆▆╔══▆▆╗    ▆▆╔════╝▆▆║     ▆▆║  ",
  "  ▆▆▆▆▆▆▆╗▆▆║▆▆▆▆▆▆▆║▆▆║  ▆▆║▆▆▆▆▆▆▆║    ▆▆║     ▆▆║     ▆▆║  ",
  "  ╚════▆▆║▆▆║▆▆╔══▆▆║▆▆║  ▆▆║▆▆╔══▆▆║    ▆▆║     ▆▆║     ▆▆║  ",
  "  ▆▆▆▆▆▆▆║▆▆║▆▆║  ▆▆║▆▆▆▆▆▆╔╝▆▆║  ▆▆║    ╚▆▆▆▆▆▆╗▆▆▆▆▆▆▆╗▆▆║  ",
  "  ╚══════╝╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝     ╚═════╝╚══════╝╚═╝  "
];

// Gradient colors matching siada-cli TTY banner
const lineColors = [
  '#5b8cd5', // color(75)  Blue
  '#6BA5E7', // color(111) Bright blue
  '#79B8FF', // color(117) Light blue (GitHub theme start)
  '#7FC9E8', // color(116) Cyan
  '#85D89D', // color(115) Light cyan-green
  '#85E89D', // color(121) Light green (GitHub theme end)
];

/**
 * Render a single banner line with gradient colors
 * Colors transition from left to right across the line
 */
const BannerLine: React.FC<{ line: string; lineIndex: number }> = ({ line, lineIndex }) => {
  const chars = [...line];
  
  return (
    <Box>
      {chars.map((ch, charIndex) => {
        // Calculate color based on position (left to right gradient)
        const ratio = chars.length <= 1 ? 0 : charIndex / (chars.length - 1);
        const colorIndex = Math.floor(ratio * (lineColors.length - 1));
        const color = lineColors[colorIndex];
        
        return (
          <Text key={charIndex} color={color}>
            {ch}
          </Text>
        );
      })}
    </Box>
  );
};

/**
 * Static Banner Component
 * Uses Ink's Static component to render the banner once
 */
const StaticBanner: React.FC = () => {
  return (
    <Box flexDirection="column" paddingX={2} paddingY={1}>
      <Text bold color="cyan">╔═══════════════════════════════════════════════════════════════════╗</Text>
      <Text bold color="cyan">║                                                                   ║</Text>
      
      {/* Use Static component to render ASCII art - it will only render once */}
      <Static items={bannerLines}>
        {(line, index) => (
          <Box key={index}>
            <Text color="cyan">║ </Text>
            <BannerLine line={line} lineIndex={index} />
            <Text color="cyan"> ║</Text>
          </Box>
        )}
      </Static>
      
      <Text bold color="cyan">║                                                                   ║</Text>
      <Text bold color="cyan">╚═══════════════════════════════════════════════════════════════════╝</Text>
    </Box>
  );
};

/**
 * Demo App Component
 * Shows the static banner with dynamic content below
 */
const DemoApp: React.FC = () => {
  const [counter, setCounter] = useState(0);
  const [messages, setMessages] = useState<string[]>([]);

  // Simulate dynamic updates
  useEffect(() => {
    const interval = setInterval(() => {
      setCounter(prev => prev + 1);
      setMessages(prev => [...prev, `Update #${prev.length + 1} at ${new Date().toLocaleTimeString()}`]);
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  return (
    <Box flexDirection="column">
      {/* Static Banner - renders once and never updates */}
      <StaticBanner />
      
      {/* Dynamic Content - updates regularly */}
      <Box flexDirection="column" paddingX={2} paddingTop={1}>
        <Text bold color="yellow">
          ⚡ Demo: Static Banner with Dynamic Content
        </Text>
        <Text dimColor>
          The banner above uses Ink's Static component and renders only once.
        </Text>
        <Text dimColor>
          The content below updates every 2 seconds to demonstrate that the banner stays static.
        </Text>
        
        <Box paddingTop={1}>
          <Text>
            Update Counter: <Text bold color="green">{counter}</Text>
          </Text>
        </Box>
        
        <Box flexDirection="column" paddingTop={1}>
          <Text bold>Recent Updates:</Text>
          {messages.slice(-5).map((msg, idx) => (
            <Text key={idx} dimColor>
              • {msg}
            </Text>
          ))}
        </Box>
        
        <Box paddingTop={1}>
          <Text dimColor italic>
            Press Ctrl+C to exit
          </Text>
        </Box>
      </Box>
    </Box>
  );
};

// Render the demo
console.clear();
render(<DemoApp />);
