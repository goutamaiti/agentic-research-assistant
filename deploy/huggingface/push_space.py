"""Publish this project to a Hugging Face Docker Space.

Usage (from the project root, with the backend environment that run.bat creates):

    backend\\.venv\\Scripts\\python deploy\\huggingface\\push_space.py --space <user>/<name>
    backend\\.venv\\Scripts\\python deploy\\huggingface\\push_space.py --space <user>/<name> --secrets

The Space is created on the first run. Only files tracked by git are sent, and only
those the Docker build needs (no PDFs, tests, evaluation data or local settings);
README.md is replaced by deploy/huggingface/README.md, which carries the Space
settings. ``--secrets`` asks for the Gemini API key and an access password and stores
them as Space secrets; they are typed hidden and never printed or written to disk.

A Hugging Face access token with write permission is needed: the HF_TOKEN environment
variable, a previous ``hf auth login``, or the prompt this script shows.
"""

from __future__ import annotations

import argparse
import getpass
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPACE_README = Path(__file__).with_name("README.md")

# Paths (prefixes) the image needs; everything else stays on GitHub only.
INCLUDE = ("Dockerfile", ".dockerignore", "backend/", "frontend/", "storage/")
EXCLUDE = ("backend/tests/", "backend/scripts/")
KEEP_REMOTE = {".gitattributes"}  # created by Hugging Face; leave it alone


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode("utf-8")
    files = [f for f in out.split("\0") if f]
    return sorted(
        f
        for f in files
        if f.startswith(INCLUDE)
        and not f.startswith(EXCLUDE)
        and not f.lower().endswith(".pdf")
        and (ROOT / f).is_file()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--space",
        required=True,
        help="Space ID, e.g. yourname/agentic-research-assistant",
    )
    parser.add_argument(
        "--private", action="store_true", help="create the Space as private"
    )
    parser.add_argument(
        "--secrets", action="store_true", help="set GEMINI_API_KEY and ACCESS_PASSWORD"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="list the files and stop"
    )
    args = parser.parse_args()

    files = tracked_files()
    if "Dockerfile" not in files:
        print("Dockerfile is not committed yet; commit it first (git add Dockerfile).")
        return 1
    if args.dry_run:
        print("\n".join(["README.md  (from deploy/huggingface/README.md)", *files]))
        print(f"{len(files) + 1} files")
        return 0

    from huggingface_hub import (
        CommitOperationAdd,
        CommitOperationDelete,
        HfApi,
        get_token,
        login,
    )

    if get_token() is None:
        print("Paste a Hugging Face access token with write permission")
        print("(create one at https://huggingface.co/settings/tokens).")
        login()
    api = HfApi()

    api.create_repo(
        args.space,
        repo_type="space",
        space_sdk="docker",
        private=args.private,
        exist_ok=True,
    )
    remote = set(api.list_repo_files(args.space, repo_type="space"))
    sending = {"README.md", *files}
    operations: list = [CommitOperationAdd("README.md", str(SPACE_README))]
    operations += [CommitOperationAdd(f, str(ROOT / f)) for f in files]
    operations += [
        CommitOperationDelete(f) for f in sorted(remote - sending - KEEP_REMOTE)
    ]
    commit = api.create_commit(
        args.space,
        operations,
        repo_type="space",
        commit_message="Deploy from agentic-research-assistant",
    )
    print(f"Uploaded {len(sending)} files: {commit.commit_url}")

    if args.secrets:
        key = getpass.getpass(
            "Gemini API key (hidden; Enter to leave unchanged): "
        ).strip()
        if key:
            api.add_space_secret(args.space, "GEMINI_API_KEY", key)
            print("GEMINI_API_KEY saved as a Space secret.")
        password = getpass.getpass(
            "Access password for visitors (hidden; Enter to skip): "
        ).strip()
        if password:
            api.add_space_secret(args.space, "ACCESS_PASSWORD", password)
            print("ACCESS_PASSWORD saved as a Space secret.")

    print(
        f"The Space builds now (about 10 minutes): https://huggingface.co/spaces/{args.space}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
