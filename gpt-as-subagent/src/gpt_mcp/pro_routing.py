"""Pro delegations run as background jobs.

A Pro turn usually outlasts the host's tool timeout (60 s in Claude Desktop),
which cancels a blocking call and discards the work. GPT_PRO_SYNC=1 restores
waiting for hosts without that timeout.
"""

import json
import os

SYNC_ENV = "GPT_PRO_SYNC"


def runs_in_background(model: str) -> bool:
    return model == "pro" and os.getenv(SYNC_ENV, "") != "1"


def started(start_payload: str) -> str:
    """Annotate a start_* payload so the host knows to poll for the result."""
    payload = json.loads(start_payload)
    if payload.get("ok"):
        payload["note"] = (
            "Pro runs as a background job because it usually outlasts the host's "
            "tool timeout. Poll get_gpt_result(job_id). "
            f"Set {SYNC_ENV}=1 to wait instead."
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)
