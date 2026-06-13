from pathlib import Path

WORKSPACE_DIRS = [
    "_workingspace/log",
    "_workingspace/diary",
    "_workingspace/plans",
]


def init() -> None:
    print("dna_kernel - initial setup")
    print()

    print("Checking _workingspace/ directories...")
    for d in WORKSPACE_DIRS:
        path = Path(d)
        if not path.exists():
            path.mkdir(parents=True)
            (path / ".gitkeep").touch()
            print(f"  created: {d}/")
        else:
            print(f"  ready: {d}/")

    print()
    print("Setup complete. Available tools:")
    print("  uv run python tools/kernel/workspace_audit_log.py append 'message'")
    print("  uv run python tools/kernel/json_weighted_pick.py <file.json> -p <path>")
    print()
    print("Generate rules for configured LLM tools:")
    print("  corepack pnpm dlx rulesync generate")


if __name__ == "__main__":
    init()
