"""Publisher: pushes the generated static site to a remote server via rsync."""

import logging
import os
import subprocess
from pathlib import Path

from src.config import SITE_DIR, get_config

logger = logging.getLogger(__name__)


def push_to_remote() -> bool:
    """Push the site/ directory to the remote server using rsync.

    Returns True if successful, False otherwise.
    """
    config = get_config().publish

    if config.remote_host == "your-server.com":
        logger.warning(
            "[publisher] Remote host not configured (still 'your-server.com'). "
            "Skipping push. Update config.yaml or .env to set PUBLISH_REMOTE_HOST."
        )
        return False

    # Expand SSH key path
    ssh_key = os.path.expanduser(config.ssh_key)

    # Build rsync command
    remote_dest = f"{config.remote_user}@{config.remote_host}:{config.remote_path}"
    cmd = [
        "rsync",
        "-avz",
        "--delete",
        "-e",
        f"ssh -i {ssh_key} -o StrictHostKeyChecking=no",
        f"{SITE_DIR}/",
        remote_dest,
    ]

    logger.info(f"[publisher] Pushing site to {remote_dest} ...")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            logger.info(f"[publisher] Successfully pushed to {remote_dest}")
            if result.stdout:
                logger.debug(f"[publisher] rsync output:\n{result.stdout}")
            return True
        else:
            logger.error(
                f"[publisher] rsync failed (exit code {result.returncode}):\n"
                f"{result.stderr}"
            )
            return False

    except subprocess.TimeoutExpired:
        logger.error("[publisher] rsync timed out after 120 seconds.")
        return False
    except FileNotFoundError:
        logger.error("[publisher] rsync command not found. Please install rsync.")
        return False
    except Exception as e:
        logger.error(f"[publisher] Push failed: {e}", exc_info=True)
        return False
