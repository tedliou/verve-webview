#!/usr/bin/env python3
"""PROTOTYPE: terminal shell for feeling out the SDK lifecycle interface."""

from lifecycle import Model


BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

URLS = (
    "https://example.com/one",
    "https://example.com/two",
    "not a valid URL",
)


def adapter_call(adapter: str, action: str, url: str) -> str:
    if adapter == "Unity":
        calls = {
            "initialize": "await webView.InitializeAsync(options)",
            "open": f'await webView.OpenAsync("{url}", rectangle)',
            "close": "await webView.CloseAsync()",
            "dispose": "await webView.DisposeAsync()",
        }
    else:
        calls = {
            "initialize": "await web_view.initialize(options)",
            "open": f'await web_view.open("{url}", rectangle)',
            "close": "await web_view.close()",
            "dispose": "await web_view.dispose()",
        }
    return calls.get(action, "—")


def render(model: Model, adapter: str, next_url: str, last_call: str) -> None:
    print("\033[2J\033[H", end="")
    print(f"{BOLD}PROTOTYPE — minimal WebView SDK lifecycle{RESET}")
    print(f"{DIM}Adapter syntax is cosmetic; both views drive one Core model.{RESET}\n")
    print(f"{BOLD}Engine Adapter view:{RESET} {adapter}")
    print(f"{BOLD}Last public call:{RESET} {last_call}")
    print(f"{BOLD}Immediate result:{RESET} {model.last_result}")
    print(f"{BOLD}Completion/event:{RESET} {model.last_event}\n")
    print(f"{BOLD}SDK Instance state{RESET}")
    print(f"  phase: {model.phase.value}")
    print(f"  WebView Surface URL: {model.visible_url or 'none'}")
    if model.pending:
        print(
            "  pending operation: "
            f"{model.pending.identifier} / {model.pending.kind.value}"
        )
    else:
        print("  pending operation: none")
    retired = sorted(model.retired_operation_ids)
    print(f"  retired operation IDs: {retired or 'none'}")
    print(f"  next open URL: {next_url}")
    print(f"  diagnostics: {model.diagnostics[-3:] or 'none'}\n")
    print(f"{BOLD}Commands{RESET}")
    print("  [i] initialize  [o] open  [c] close  [d] dispose")
    print("  [s] complete successfully  [f] complete with backend error")
    print("  [l] deliver late completion  [n] change next URL")
    print("  [a] switch Unity/Godot view  [r] reset  [q] quit")


def main() -> None:
    model = Model()
    adapter = "Unity"
    url_index = 0
    last_call = "—"

    while True:
        next_url = URLS[url_index]
        render(model, adapter, next_url, last_call)
        key = input("\n> ").strip().lower()[:1]
        if key == "q":
            break
        if key == "a":
            adapter = "Godot" if adapter == "Unity" else "Unity"
        elif key == "n":
            url_index = (url_index + 1) % len(URLS)
        elif key == "r":
            model = Model()
            last_call = "—"
        elif key == "i":
            last_call = adapter_call(adapter, "initialize", next_url)
            model.initialize()
        elif key == "o":
            last_call = adapter_call(adapter, "open", next_url)
            model.open(next_url)
        elif key == "c":
            last_call = adapter_call(adapter, "close", next_url)
            model.close()
        elif key == "d":
            last_call = adapter_call(adapter, "dispose", next_url)
            model.dispose()
        elif key == "s":
            model.complete(True)
        elif key == "f":
            model.complete(False)
        elif key == "l":
            model.deliver_late_completion()


if __name__ == "__main__":
    main()
