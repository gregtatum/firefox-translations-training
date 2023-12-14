import os
from pathlib import Path

from taskgraph import files_changed
from taskgraph.transforms.base import TransformSequence

KIND_DIR = Path(__file__).parent.parent.parent / "ci"

# Kinds are slightly special - there are some kinds that don't affect the pipeline,
# and changing them shouldn't force the pipeline to run.
EXCLUDE_KINDS = ["test"]
# Touching any file in any of these directories is considered a pipeline change
PIPELINE_DIRS = [
    "pipeline/**",
    "taskcluster/docker/**",
    "taskcluster/requirements.txt",
    "taskcluster/scripts/**",
    "taskcluster/translations_taskgraph/**",
]
PIPELINE_DIRS.extend(
    f"taskcluster/ci/{kind}" for kind in os.listdir(KIND_DIR) if kind not in EXCLUDE_KINDS
)

transforms = TransformSequence()


@transforms.add
def skip_unless_pipeline_changed(config, jobs):
    """Remove all jobs unless at least one pipeline impacting thing (a pipeline script or
    relevant Taskcluster code) has changed.

    If/when upstream taskgraph supports better selection (https://github.com/taskcluster/taskgraph/issues/369)
    this can be replaced with it."""

    if not files_changed.check(config.params, PIPELINE_DIRS):
        return

    yield from jobs