from pydub import AudioSegment

from interview_mux.audio_timeline import append_with_crossfade, concat_clips_with_crossfade


def test_concat_clips_with_crossfade():
    clips = [AudioSegment.silent(duration=500), AudioSegment.silent(duration=500)]
    merged = concat_clips_with_crossfade(clips, 50)
    assert len(merged) > 500
    assert len(merged) < 1000


def test_append_integration():
    a = AudioSegment.silent(duration=1000)
    b = AudioSegment.silent(duration=1000)
    out = append_with_crossfade(a, b, 100)
    assert len(out) == len(a) + len(b) - 100
