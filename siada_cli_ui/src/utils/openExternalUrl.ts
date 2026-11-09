import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execute = promisify(execFile);

/** Open a web link using the OS handler without interpreting it as shell code. */
export async function openExternalUrl(url: string, signal?: AbortSignal): Promise<void> {
  if (new URL(url).protocol !== 'https:') throw new Error('Only HTTPS links are supported');
  const [command, args] = process.platform === 'darwin'
    ? ['open', [url]] as const
    : process.platform === 'win32'
      ? ['rundll32.exe', ['url.dll,FileProtocolHandler', url]] as const
      : ['xdg-open', [url]] as const;
  await execute(command, [...args], { timeout: 10000, windowsHide: true, signal });
}