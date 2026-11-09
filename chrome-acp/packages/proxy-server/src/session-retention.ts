export const SESSION_RETENTION_MS = 5 * 60 * 1000;

/** Own detached sessions and dispose them once their retention window ends. */
export class SessionRetention<T> {
  private entries = new Map<string, { value: T; expiresAt: number; timer: ReturnType<typeof setTimeout> }>();

  constructor(
    private dispose: (value: T) => void,
    private duration = SESSION_RETENTION_MS,
    private now = () => Date.now(),
    private schedule = (callback: () => void, delay: number) => setTimeout(callback, delay),
    private unschedule = (timer: ReturnType<typeof setTimeout>) => clearTimeout(timer),
  ) {}

  get size(): number { return this.entries.size; }

  retain(key: string, value: T): void {
    this.remove(key);
    // Bound resident processes even if an authenticated client creates many IDs.
    if (this.entries.size >= 32) this.remove(this.entries.keys().next().value!);
    const entry = {
      value,
      expiresAt: this.now() + this.duration,
      timer: this.schedule(() => {
        if (this.entries.get(key) === entry) this.remove(key);
      }, this.duration),
    };
    entry.timer.unref?.();
    this.entries.set(key, entry);
  }

  take(key: string): T | undefined {
    const entry = this.entries.get(key);
    if (!entry) return;
    this.entries.delete(key);
    this.unschedule(entry.timer);
    if (this.now() >= entry.expiresAt) {
      this.dispose(entry.value);
      return;
    }
    return entry.value;
  }

  remove(key: string): void {
    const entry = this.entries.get(key);
    if (!entry) return;
    this.entries.delete(key);
    this.unschedule(entry.timer);
    this.dispose(entry.value);
  }

  clear(): void {
    for (const key of this.entries.keys()) this.remove(key);
  }
}