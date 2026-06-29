from interview_mux.operator_recovery import format_recovery_command


class _Ctx:
    run_id = "run_test_001"


def test_format_recovery_command_analysis():
    cmd = format_recovery_command(_Ctx(), from_stage="segment_classification")
    assert "run_test_001" in cmd
    assert "--from-stage segment_classification" in cmd
