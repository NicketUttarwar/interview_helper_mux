from interview_mux.prompt_validation import validate_transcript_review_queue


def test_invalid_review_queue_fails():
    errors = validate_transcript_review_queue({"chunks": "not-a-list"})
    assert errors
