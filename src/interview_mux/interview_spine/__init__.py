"""Interview comprehension spine — time-aligned local analysis + optional CLAP retrieval."""

from interview_mux.interview_spine.compact import (
    attach_spine_to_payload,
    compact_for_boundary,
    compact_for_volley,
)
from interview_mux.interview_spine.config import spine_cfg, spine_enabled
from interview_mux.interview_spine.paths import SPINE_EMBEDDINGS_REL, SPINE_PATH
from interview_mux.interview_spine.retrieval import load_spine, query_spine
