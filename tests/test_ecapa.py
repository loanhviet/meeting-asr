import numpy as np

from meeting_asr.ecapa import Window, assign_overlaps, cluster_clean_embeddings, cluster_embeddings
from meeting_asr.models import Segment


def test_cluster_and_margin_with_speaker_bounds():
    vectors = np.array([[1, 0], [0.99, 0.01], [0, 1], [0.01, 0.99]])
    labels, margins = cluster_embeddings(vectors, 0.2)
    assert labels[0] == labels[1] != labels[2] == labels[3]
    assert all(m > 0.9 for m in margins)
    labels, margins = cluster_embeddings(vectors, 0.2, max_speakers=1)
    assert len(set(labels)) == 1
    assert margins == [None] * 4


def test_overlap_assignment_uses_only_nearby_predicted_anchors():
    segments = [Segment(0, 3, "SPEAKER_00"), Segment(3, 5, "SPEAKER_01")]
    windows = [Window(0, 1, 0), Window(3, 4, 0)]
    result, extras = assign_overlaps(segments, windows, [0, 1], [0.5, 0.6], [(1, 2)])
    assert len(result) == 3
    assert extras[0][0] == Segment(1, 2, "SPEAKER_01")
    result, extras = assign_overlaps(segments, [], [], [], [(1, 2)])
    assert result == segments
    assert extras == []


def test_short_and_overlap_windows_do_not_create_extra_clean_clusters():
    vectors = np.array([[1, 0, 0], [0.99, 0.01, 0], [0, 1, 0], [0, 0, 1]])
    windows = [Window(0, 1, 0), Window(1, 2, 0), Window(3, 4, 1), Window(5, 5.3, 2)]
    labels, margins = cluster_clean_embeddings(vectors, windows, [], threshold=0.2)
    assert len(set(labels)) == 2
    assert labels[0] == labels[1] != labels[2]
    assert len(margins) == 4
    windows[-1] = Window(5, 6, 2)
    labels, _ = cluster_clean_embeddings(vectors, windows, [(5, 6)], threshold=0.2)
    assert len(set(labels)) == 2


def test_clean_clustering_falls_back_without_enough_clean_evidence():
    vectors = np.array([[1, 0], [0, 1]])
    windows = [Window(0, 1, 0), Window(1, 2, 0)]
    expected, _ = cluster_embeddings(vectors, 0.2)
    actual, _ = cluster_clean_embeddings(vectors, windows, [(0, 2)], threshold=0.2)
    assert np.array_equal(actual, expected)
