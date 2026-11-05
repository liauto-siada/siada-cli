import os from 'node:os';
import { syncBuiltinESMExports } from 'node:module';

// Keep config writes and session discovery inside this test's temporary state.
if (!process.env.PICKER_TEST_HOME) throw new Error('PICKER_TEST_HOME is required');
os.homedir = () => process.env.PICKER_TEST_HOME;
syncBuiltinESMExports();