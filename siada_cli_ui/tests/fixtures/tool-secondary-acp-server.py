"""Offline ACP fixture using the checkout's actual Python tool formatters."""

import json
import sys

from siada.tools.tool_call_format.formatters import (
    FactStoreFormatter,
    MemoryWriteFormatter,
    SearchFormatter,
)


def notify(method, params):
    print(json.dumps({"jsonrpc": "2.0", "method": method, "params": params}), flush=True)


def scene(index):
    if index in (7, 8):
        query = ("ToolPromptView|ConversationViewport|\nsecondary|expandable" if index == 7
                 else "(?x)\nsecondary\n| expandable\n| memory\n")
        return SearchFormatter().format_input(
            "synthetic", "regex_search_files", json.dumps({
                "regex": query, "directory_path": "siada_cli_ui/src",
                "file_pattern": "*.{ts,tsx}", "cwd": "/tmp/project",
            })
        )[0]
    if index in (1, 2, 3):
        action = {1: "create", 2: "undo", 3: "update"}[index]
        data = {"callId": "synthetic", "action": action, "path": f"src/{action}.ts",
                "status": "failed", "error": f"REJECTED_{action.upper()}"}
        return (f"File edit: {action} src/{action}.ts\n<!-- siada-file-edit:start -->\n"
                + json.dumps(data) + "\n<!-- siada-file-edit:end -->")
    text = "FIRST_ARGUMENT\n" + "中文内容" * 25 + "\nCOMPLETE_ARGUMENT_TAIL"
    if index == 4:
        return MemoryWriteFormatter().format_input(
            "synthetic", "memory", json.dumps({"action": "add", "target": "memory", "content": text})
        )[0]
    if index == 5:
        return FactStoreFormatter().format_input(
            "synthetic", "fact_store", json.dumps({"action": "add", "category": "project", "content": text})
        )[0]
    return "Search for: FIRST_QUERY\nSECOND_QUERY in src with file pattern *.ts in /tmp/project"


notify("session/update", {"reason": "banner_info", "content": json.dumps({
    "version": "synthetic", "working_dir": ".", "agent": "coder", "provider": "synthetic",
    "model": "synthetic", "session_id": "synthetic-tool-secondary", "theme": "dark",
    "slash_commands": [{"name": "fixture", "description": "Offline display check"}],
})})
notify("ui/startupComplete", {})
frame = None
for line in sys.stdin:
    line = line.rstrip("\n")
    if line == "<<<SIADA_MSG_START>>>":
        frame = []
    elif line == "<<<SIADA_MSG_END>>>" and frame is not None:
        message = json.loads("\n".join(frame))
        frame = None
        prompt = message.get("prompt", "")
        if prompt.startswith("/fixture "):
            index = int(prompt.split()[-1])
            messages = [{"role": "user", "content": f"Synthetic scene {index}."}]
            if index >= 4:
                messages.append({"role": "agent", "content": "Read the file `src/a.ts`",
                                 "subtype": "tool_use"})
            messages.extend([
                {"role": "agent", "content": scene(index), "subtype": "tool_use"},
                {"role": "agent", "content": f"SCENE_{index}_READY", "subtype": "answer"},
            ])
            if index == 8:
                # Exercise the live tool event path as well as restored history.
                notify("ui/loadHistory", {"messages": messages[:2]})
                notify("session/update", {"reason": "lifecycle_event", "type": "tool_use",
                                         "delta": scene(index), "chunk_index": 0, "is_final": True})
                notify("session/update", {"reason": "message_chunk", "content": f"SCENE_{index}_READY",
                                         "metadata": {"subtype": "answer"}})
            else:
                notify("ui/loadHistory", {"messages": messages})
            notify("session/update", {"reason": "lifecycle_event", "type": "input_ready",
                                      "animation_control": "stop"})
    elif frame is not None:
        frame.append(line)