import { afterEach, expect, test } from "bun:test";
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { ACPClient } from "@chrome-acp/shared/acp";
import { ACPMain } from "@chrome-acp/shared/components";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | undefined;
afterEach(() => {
  act(() => root?.unmount());
  root = undefined;
  document.body.innerHTML = "";
});

test("disconnect unmounts ACPMain and leaves a usable connection screen", async () => {
  const client = new ACPClient({ proxyUrl: "ws://localhost:9315/ws" });
  // Session startup is unrelated to disconnect; leave the UI waiting for it.
  client.createSession = async () => {};
  client.listDir = async () => [];

  function Panel() {
    const [connected, setConnected] = useState(true);
    return (
      <>
        <button onClick={() => {
          client.disconnect();
          setConnected(false);
        }}>Disconnect</button>
        {connected ? <ACPMain client={client} /> : <p>No agent connected</p>}
      </>
    );
  }

  const container = document.createElement("div");
  document.body.append(container);
  await act(async () => {
    root = createRoot(container);
    root.render(<Panel />);
  });
  expect(container.textContent).toContain("Chat");
  await act(async () => {
    (container.querySelector("button") as HTMLButtonElement).click();
  });
  expect(container.textContent).toContain("No agent connected");
  expect(container.textContent).toContain("Disconnect");
  expect(container.querySelector('[role="tablist"]')).toBeNull();
});