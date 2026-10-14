"""Runs the REAL dlib models on public sample photos (ageitgey/face_recognition examples).

Photos are downloaded at test time and are never committed. The test is skipped
if dlib or the network is unavailable.
"""
import os
import urllib.request

import pytest

pytest.importorskip("dlib")
from src.pipelines.face_pipeline import build_gallery, get_face_embeddings, match_encodings, to_rgb_array  # noqa: E402

BASE = "https://raw.githubusercontent.com/ageitgey/face_recognition/master/examples/"
CACHE = os.environ.get("SA_TEST_FACES", "/tmp/smartattend_faces")


def _img(name):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        try:
            urllib.request.urlretrieve(BASE + name, path)
        except Exception:
            pytest.skip(f"cannot download {name}")
    return path


@pytest.fixture(scope="module")
def gallery():
    rows = []
    for sid, f in {1: "obama.jpg", 2: "biden.jpg", 3: "alex-lacamoire.png"}.items():  # 3 is an RGBA PNG
        enc = get_face_embeddings(_img(f))
        assert len(enc) == 1, f"{f}: expected exactly one face, got {len(enc)}"
        assert enc[0].shape == (128,)
        rows.append({"student_id": sid, "face_embedding": enc[0].tolist()})
    return build_gallery(rows)


def test_rgba_png_is_supported():
    arr = to_rgb_array(_img("alex-lacamoire.png"))
    assert arr.ndim == 3 and arr.shape[2] == 3 and arr.dtype.name == "uint8"


def test_group_photo_identifies_both_people_not_the_absent_one(gallery):
    ids, mat = gallery
    r = match_encodings(get_face_embeddings(_img("two_people.jpg")), ids, mat, threshold=0.6)
    assert r.num_faces == 2
    assert set(r.matched) == {1, 2}  # Obama + Biden present, student 3 absent


def test_other_photo_of_same_person_matches(gallery):
    ids, mat = gallery
    r = match_encodings(get_face_embeddings(_img("obama2.jpg")), ids, mat, threshold=0.6)
    assert 1 in r.matched and 2 not in r.matched


def test_restricting_to_enrolled_students(gallery):
    ids, mat = gallery
    r = match_encodings(get_face_embeddings(_img("two_people.jpg")), ids, mat, allowed_ids={2, 3})
    assert set(r.matched) == {2}
