#!/usr/bin/env node
/**
 * Test case for input box visibility fix
 * 
 * This test verifies that the input box remains visible even when
 * there's a lot of message content. Before the fix, long content
 * would push the input box off the screen.
 * 
 * Expected behavior:
 * - Input box always visible at the bottom
 * - Message area scrolls with overflow:hidden
 * - No flickering even with terminal-height content
 */

import React, { useState, useEffect } from 'react';
import { render, Box, Text } from '../src/index.js';

const LongContentTest = () => {
	const [messageCount, setMessageCount] = useState(1);

	// Add a new message every 2 seconds to simulate chat
	useEffect(() => {
		const interval = setInterval(() => {
			setMessageCount(prev => Math.min(prev + 1, 50));
		}, 2000);

		return () => clearInterval(interval);
	}, []);

	// Generate many messages to test overflow
	const messages = Array.from({ length: messageCount }, (_, i) => ({
		id: i,
		content: `Message ${i + 1}: This is a test message with some content. Lorem ipsum dolor sit amet, consectetur adipiscing elit.`
	}));

	const terminalRows = process.stdout.rows || 24;

	return (
		<Box flexDirection="column" width="100%">
			{/* Header */}
			<Box borderStyle="round" paddingX={1} marginBottom={1}>
				<Text bold color="cyan">
					Input Visibility Test (Terminal: {terminalRows} rows)
				</Text>
			</Box>

			{/* Message Area - should be constrained */}
			<Box flexDirection="column" flexGrow={1}>
				<Text color="green">
					Messages ({messageCount}/50) - Area should be constrained:
				</Text>
				{messages.map(msg => (
					<Box key={msg.id} marginLeft={2} marginY={0}>
						<Text dimColor>{msg.content}</Text>
					</Box>
				))}
			</Box>

			{/* Status indicator */}
			<Box marginY={1} paddingX={2}>
				<Text color="yellow">
					⚡ Simulating chat updates... ({messageCount} messages)
				</Text>
			</Box>

			{/* Input Box - should ALWAYS be visible */}
			<Box 
				borderStyle="round" 
				paddingX={1}
				borderColor="green"
			>
				<Text>
					▸ Type your message... (THIS SHOULD ALWAYS BE VISIBLE)
				</Text>
			</Box>

			<Box marginTop={1}>
				<Text dimColor>
					✓ If you can see this input box, the fix is working!
				</Text>
			</Box>
		</Box>
	);
};

render(<LongContentTest />);
