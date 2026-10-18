from nodes import nodes_draft


def test_build_draft_body_forbids_reused_params():
    body = nodes_draft.build_draft_body("cgt-1", {
        "output_format": "mov", "watermark": True, "return_last_frame": False,
        "priority": 2, "execution_expires_after": 172800,
    })
    assert body["model"] == "doubao-seedance-2-5-260628"
    assert body["resolution"] == "1080p"
    assert body["content"] == [{"type": "draft_task", "draft_task": {"id": "cgt-1"}}]
    for forbidden in ("duration", "ratio", "seed", "generate_audio", "omni_reference_task_type"):
        assert forbidden not in body
