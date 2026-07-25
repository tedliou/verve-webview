"""Terminal explorer for the throwaway canonical Bazel package prototype."""

import os
import sys

from model import MODULES, target_label, validate


BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RESET = "\x1b[0m"


def clear() -> None:
    if sys.stdout.isatty():
        print("\x1b[2J\x1b[H", end="")


def render_target(module_index: int, target_index: int) -> None:
    module = MODULES[module_index]
    target = module.targets[target_index]
    deps = "\n".join(f"  - {dep}" for dep in target.deps) or "  (none)"
    constraints = (
        "\n".join(f"  - {item}" for item in target.compatible_with)
        or "  (configuration independent)"
    )
    errors = validate()
    status = "PASS — all model invariants hold" if not errors else "\n".join(errors)
    print(f"{BOLD}PROTOTYPE — canonical Bazel package templates{RESET}")
    print(f"{DIM}Target view · module {module_index + 1}/{len(MODULES)} · "
          f"target {target_index + 1}/{len(module.targets)}{RESET}\n")
    print(f"{BOLD}Repository Module{RESET}: {module.package} ({module.kind})")
    print(f"{BOLD}Target{RESET}:            {target_label(module, target)}")
    print(f"{BOLD}Rule kind{RESET}:         {target.rule}")
    print(f"{BOLD}Role{RESET}:              {target.role}")
    print(f"{BOLD}Visibility{RESET}:        {target.visibility}")
    print(f"{BOLD}Fragment provider{RESET}: "
          f"{'yes' if target.produces_fragment else 'no'}")
    print(f"{BOLD}Dependencies{RESET}:\n{deps}")
    print(f"{BOLD}Target constraints{RESET}:\n{constraints}")
    print(f"\n{BOLD}Invariant status{RESET}: {status}")


def render_graph() -> None:
    errors = validate()
    print(f"{BOLD}PROTOTYPE — canonical Bazel package templates{RESET}")
    print(f"{DIM}Repository graph view{RESET}\n")
    print("sdk (Unity or Godot)")
    print("├── adapter ──────────> core:api_contract")
    print("├── binding_android ──> android:backend ──> core:core_native")
    print("├── binding_ios ──────> ios:backend ─────> core:core_native")
    print("├── binding_windows ──> windows:backend ─> core:core_native")
    print("└── binding_web ──────> web:backend ─────> core:core_web")
    print("                          core transports ─> core:api_contract")
    print("\nDistribution flow:")
    print("source target → DistributionFragmentInfo → manifest verification")
    print("              → canonical Linux aggregation → Engine SDK archive")
    print(f"\n{BOLD}Invariant status{RESET}: "
          f"{'PASS' if not errors else 'FAIL'}")


def run() -> None:
    module_index = 0
    target_indexes = [0] * len(MODULES)
    graph = False
    while True:
        clear()
        if graph:
            render_graph()
        else:
            render_target(module_index, target_indexes[module_index])
        print(
            f"\n{BOLD}[1-7]{RESET} module  {BOLD}[j/k]{RESET} target  "
            f"{BOLD}[g]{RESET} graph  {BOLD}[q]{RESET} quit"
        )
        try:
            command = input("> ").strip().lower()
        except EOFError:
            return
        if command == "q":
            return
        if command == "g":
            graph = not graph
        elif command in {str(index) for index in range(1, len(MODULES) + 1)}:
            module_index = int(command) - 1
            graph = False
        elif command == "j":
            count = len(MODULES[module_index].targets)
            target_indexes[module_index] = (target_indexes[module_index] + 1) % count
            graph = False
        elif command == "k":
            count = len(MODULES[module_index].targets)
            target_indexes[module_index] = (target_indexes[module_index] - 1) % count
            graph = False


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    run()
