"""Approve a draft through a separate authenticated human workflow."""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_server.server import approve_communication


def parse_args() -> argparse.Namespace:
    """Parse the draft ID and authenticated approver identity."""
    parser = argparse.ArgumentParser(
        description="Approve one pending draft without exposing approval to an agent."
    )
    parser.add_argument("draft_id", help="Draft ID, for example DRAFT-A1B2C3D4")
    parser.add_argument(
        "--approver-id",
        default=os.getenv("APPROVER_ID"),
        help="Authenticated reviewer identity (defaults to APPROVER_ID).",
    )
    return parser.parse_args()


def main() -> int:
    """Validate local credentials and approve the requested draft."""
    load_dotenv()
    args = parse_args()
    try:
        credentials = json.loads(os.getenv("APPROVER_CREDENTIALS_JSON", "{}"))
    except json.JSONDecodeError:
        credentials = {}
    approval_token = (
        credentials.get(args.approver_id, "")
        if args.approver_id and isinstance(credentials, dict)
        else ""
    )
    if not args.approver_id or not approval_token:
        print(
            "Approval denied: set APPROVER_ID and a matching entry in "
            "APPROVER_CREDENTIALS_JSON."
        )
        return 1

    result = approve_communication(
        draft_id=args.draft_id,
        approver_id=args.approver_id,
        approval_token=approval_token,
    )
    if "error" in result:
        print(result["error"])
        return 1
    print(result["message"])
    print(
        f"status={result['status']} approved_by={result['approved_by']} "
        f"reviewed_at={result['reviewed_at']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
