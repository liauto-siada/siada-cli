#!/usr/bin/env node
/**
 * Comprehensive test for height constraint feature
 * 
 * Tests various height scenarios:
 * 1. Height = process.stdout.rows (should be constrained)
 * 2. Height = process.stdout.rows - 1 (should pass through)
 * 3. Height > process.stdout.rows (should be constrained)
 * 4. Height as string percentage (should pass through)
 * 5. Height undefined (should pass through)
 */

import React, { useState } from 'react';
import { render, Box, Text } from '../src/index.js';

const TestScenarios = () => {
	const [count, setCount] = useState(0);
	const terminalRows = process.stdout.rows || 24;

	setTimeout(() => {
		setCount(count + 1);
	}, 100);

	return (
		<Box flexDirection="column" paddingX={2} paddingY={1}>
			<Text>Terminal Height Constraint Test</Text>
			<Text>Terminal rows: {terminalRows}</Text>
			<Text>Update count: {count}</Text>
			<Text> </Text>
			
			<Text color="green">✓ Test 1: Height = terminal rows (should be constrained)</Text>
			<Box 
				height={terminalRows} 
				borderStyle="round" 
				width={40}
				marginBottom={1}
			>
				<Text>This box requested height={terminalRows}</Text>
			</Box>

			<Text color="green">✓ Test 2: Height = terminal rows - 1 (should work)</Text>
			<Box 
				height={terminalRows - 1} 
				borderStyle="round" 
				width={40}
				marginBottom={1}
			>
				<Text>This box requested height={terminalRows - 1}</Text>
			</Box>

			<Text color="green">✓ Test 3: Height &gt; terminal rows (should be constrained)</Text>
			<Box 
				height={terminalRows + 10} 
				borderStyle="round" 
				width={40}
				marginBottom={1}
			>
				<Text>This box requested height={terminalRows + 10}</Text>
			</Box>

			<Text color="cyan">ℹ Test 4: Height as percentage (should work naturally)</Text>
			<Box 
				height="50%" 
				borderStyle="round" 
				width={40}
				marginBottom={1}
			>
				<Text>This box uses height="50%"</Text>
			</Box>

			<Text color="cyan">ℹ Test 5: No height specified (natural flow)</Text>
			<Box 
				borderStyle="round" 
				width={40}
				marginBottom={1}
			>
				<Text>This box has no height constraint</Text>
			</Box>

			<Text> </Text>
			<Text color="yellow">Check logs for constraint warnings...</Text>
		</Box>
	);
};

render(<TestScenarios />);
