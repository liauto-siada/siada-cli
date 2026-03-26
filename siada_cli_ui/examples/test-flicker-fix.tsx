#!/usr/bin/env node
/**
 * Test case for flicker fix
 * 
 * This reproduces the original issue where rendering content with
 * height >= process.stdout.rows causes flickering.
 * 
 * With the fix applied, the Box component should automatically
 * constrain the height to process.stdout.rows - 1.
 */

import React, { useState } from 'react';
import { render, Box } from '../src/index.js';

const App = () => {
	const [count, setCount] = useState(0);

	setTimeout(() => {
		setCount(count + 1);
	}, 100);

	// This should now be automatically constrained to process.stdout.rows - 1
	return (
		<Box height={process.stdout.rows} borderStyle="round" width={10}>
			Count: {count}
		</Box>
	);
};

const app = <App />;
render(app);
