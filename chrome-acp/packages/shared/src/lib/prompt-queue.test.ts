import { expect, test } from "bun:test";
import { PromptQueue } from "./prompt-queue";

test("unknown steering delivery never turns into an ordinary prompt retry", async () => {
  const sent: string[] = [];
  const queue = new PromptQueue<string>(
    async (item) => { sent.push(item.value); },
    async () => { throw Object.assign(new Error("acknowledgement lost"), { deliveryUnknown: true }); },
    () => {},
    () => {},
  );
  queue.enqueue("active");
  queue.enqueue("uncertain");
  const id = queue.items[0]!.id;
  await queue.steer(id);
  queue.complete("end_turn");
  queue.resume();
  expect(queue.items[0]?.deliveryUnknown).toBe(true);
  expect(sent).toEqual(["active"]);
  queue.remove(id);
  queue.enqueue("next");
  expect(sent).toEqual(["active", "next"]);
});

function fixture(steer = async (_item: unknown) => {}) {
  const sent: string[] = [];
  const errors: unknown[] = [];
  const queue = new PromptQueue<string>(
    async (item) => { sent.push(item.value); },
    steer, () => {}, (error) => errors.push(error),
  );
  return { queue, sent, errors };
}

test("submissions dispatch FIFO only after matching end_turn", () => {
  const { queue, sent } = fixture();
  queue.enqueue("first");
  const firstId = queue.activeId!;
  queue.enqueue("second");
  queue.enqueue("third");
  expect(sent).toEqual(["first"]);
  queue.complete("end_turn", "stale");
  expect(sent).toEqual(["first"]);
  queue.complete("end_turn", firstId);
  expect(sent).toEqual(["first", "second"]);
  queue.complete("end_turn", firstId);
  expect(sent).toEqual(["first", "second"]);
  queue.complete("end_turn", queue.activeId!);
  expect(sent).toEqual(["first", "second", "third"]);
});

test("cancel/error retain queued messages until explicit resume", () => {
  for (const reason of ["cancelled", "error", "disconnected"]) {
    const { queue, sent } = fixture();
    queue.enqueue("first");
    queue.enqueue("second");
    queue.complete(reason);
    expect(sent).toEqual(["first"]);
    expect(queue.items.map((item) => item.value)).toEqual(["second"]);
    queue.resume();
    expect(sent).toEqual(["first", "second"]);
  }
});

test("steering acknowledgement cannot duplicate a queued turn at completion", async () => {
  let acknowledge!: () => void;
  const { queue, sent } = fixture(() => new Promise<void>((resolve) => { acknowledge = resolve; }));
  queue.enqueue("first");
  queue.enqueue("steer this");
  queue.enqueue("last");
  const steering = queue.steer(queue.items[0]!.id);
  queue.complete("end_turn");
  expect(sent).toEqual(["first"]);
  acknowledge();
  await steering;
  expect(sent).toEqual(["first", "last"]);
});

test("failed steering retains input and pauses dispatch", async () => {
  const { queue, sent, errors } = fixture(async () => { throw new Error("unsupported"); });
  queue.enqueue("first");
  queue.enqueue("keep me");
  await queue.steer(queue.items[0]!.id);
  queue.complete("end_turn");
  expect(sent).toEqual(["first"]);
  expect(queue.items[0]?.value).toBe("keep me");
  expect(errors).toHaveLength(1);
});

test("session reset ignores late steering acknowledgements", async () => {
  let acknowledge!: () => void;
  const { queue, sent } = fixture(() => new Promise<void>((resolve) => { acknowledge = resolve; }));
  queue.enqueue("old");
  queue.enqueue("old steering");
  const pending = queue.steer(queue.items[0]!.id);
  queue.reset();
  queue.enqueue("new");
  acknowledge();
  await pending;
  expect(sent).toEqual(["old", "new"]);
  expect(queue.items).toEqual([]);
});

test("removed input is never sent", () => {
  const { queue, sent } = fixture();
  queue.enqueue("first");
  queue.enqueue("remove");
  queue.remove(queue.items[0]!.id);
  queue.complete("end_turn");
  expect(sent).toEqual(["first"]);
});