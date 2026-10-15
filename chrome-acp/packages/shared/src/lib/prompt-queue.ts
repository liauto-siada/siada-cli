/** Serial prompt dispatch with explicit mid-turn steering and stop semantics. */
export interface QueuedPrompt<T> {
  id: string;
  value: T;
  steering?: boolean;
  deliveryUnknown?: boolean;
}

export class PromptQueue<T> {
  items: QueuedPrompt<T>[] = [];
  activeId: string | null = null;
  paused = false;
  private epoch = 0;

  constructor(
    private send: (item: QueuedPrompt<T>) => Promise<void>,
    private steerSend: (item: QueuedPrompt<T>) => Promise<void>,
    private changed: () => void,
    private error: (error: unknown) => void,
  ) {}

  enqueue(value: T): void {
    this.items.push({ id: crypto.randomUUID(), value });
    this.pump();
    this.changed();
  }

  private pump(): void {
    if (this.activeId || this.paused || !this.items.length || this.items[0]?.steering || this.items[0]?.deliveryUnknown) return;
    const item = this.items.shift()!;
    this.activeId = item.id;
    const epoch = this.epoch;
    void this.send(item).catch((error) => {
      if (epoch !== this.epoch || this.activeId !== item.id) return;
      this.activeId = null;
      this.items.unshift(item);
      this.paused = true;
      this.error(error);
      this.changed();
    });
  }

  complete(reason: string, id?: string): void {
    if (!this.activeId || (id && id !== this.activeId)) return;
    this.activeId = null;
    if (reason !== "end_turn") this.paused = true;
    this.pump();
    this.changed();
  }

  pause(): void {
    this.paused = true;
    this.changed();
  }

  resume(): void {
    this.paused = false;
    this.pump();
    this.changed();
  }

  remove(id: string): void {
    this.items = this.items.filter((item) => item.id !== id || item.steering);
    this.changed();
  }

  async steer(id: string): Promise<void> {
    const item = this.items.find((item) => item.id === id);
    if (!item || item.steering || !this.activeId) return;
    const epoch = this.epoch;
    item.steering = true;
    this.changed();
    try {
      await this.steerSend(item);
      if (epoch !== this.epoch) return;
      this.items = this.items.filter((entry) => entry !== item);
    } catch (error) {
      if (epoch !== this.epoch) return;
      item.steering = false;
      if (error instanceof Error && "deliveryUnknown" in error && error.deliveryUnknown === true) {
        item.deliveryUnknown = true;
      }
      this.paused = true;
      this.error(error);
    }
    if (epoch !== this.epoch) return;
    this.pump();
    this.changed();
  }

  reset(): void {
    this.epoch++;
    this.items = [];
    this.activeId = null;
    this.paused = false;
    this.changed();
  }
}