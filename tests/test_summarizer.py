from src.agents.summarizer import _normalize_summary_result


def _thread_posts() -> list[dict[str, object]]:
    return [
        {
            "number": 1,
            "name": "スレ主",
            "display_id": "Thread0P",
            "content": "元レス1",
        },
        {
            "number": 2,
            "name": "名無しさん",
            "display_id": "abc123",
            "content": "元レス2",
        },
        {
            "number": 3,
            "name": "風吹けば名無し",
            "display_id": "xyz789",
            "content": "元レス3",
        },
    ]


def test_normalize_summary_result_picked_comments() -> None:
    result = _normalize_summary_result(
        raw_data={
            "title": 123,
            "category": None,
            "picked_comments": [
                {
                    "number": "2",
                    "is_highlighted": "true",
                    "highlight_color": "blue",
                    "content": "改変本文",
                },
                {
                    "number": 99,
                    "is_highlighted": True,
                    "highlight_color": "red",
                },
                {
                    "number": 2,
                    "is_highlighted": False,
                    "highlight_color": "red",
                },
                {
                    "number": 1,
                    "is_highlighted": 0,
                    "highlight_color": "green",
                },
            ],
            "editor_comment": 456,
            "reactions_summary": None,
        },
        thread_posts=_thread_posts(),
        default_title="既定タイトル",
    )

    assert result["title"] == "123"
    assert result["category"] == "議論"
    assert result["editor_comment"] == "456"
    assert result["reactions_summary"] == ""
    assert result["thread_comments"] == [
        {
            "number": 2,
            "name": "名無しさん",
            "id": "abc123",
            "content": "元レス2",
            "is_highlighted": True,
            "highlight_color": "blue",
        },
        {
            "number": 1,
            "name": "スレ主",
            "id": "Thread0P",
            "content": "元レス1",
            "is_highlighted": False,
            "highlight_color": None,
        },
    ]


def test_normalize_summary_result_falls_back_on_invalid_data() -> None:
    result = _normalize_summary_result(
        raw_data="not-a-dict",
        thread_posts=_thread_posts(),
        default_title="既定タイトル",
    )

    assert result["title"] == "既定タイトル"
    assert result["category"] == "議論"
    assert result["editor_comment"] == "まとめの自動生成に一部失敗しました。"
    assert [comment["number"] for comment in result["thread_comments"]] == [
        1,
        2,
        3,
    ]


def test_normalize_summary_result_ignores_missing_numbers() -> None:
    result = _normalize_summary_result(
        raw_data={
            "title": "タイトル",
            "category": "カテゴリ",
            "picked_comments": [
                {"number": "abc"},
                {"number": 999},
            ],
        },
        thread_posts=_thread_posts(),
        default_title="既定タイトル",
    )

    assert result["editor_comment"] == "まとめの自動生成に一部失敗しました。"
    assert [comment["number"] for comment in result["thread_comments"]] == [
        1,
        2,
        3,
    ]


def test_normalize_summary_result_supports_legacy_thread_comments() -> None:
    result = _normalize_summary_result(
        raw_data={
            "title": "旧形式",
            "category": "議論",
            "thread_comments": [
                {
                    "number": 3,
                    "name": "偽名",
                    "id": "fake",
                    "content": "偽本文",
                    "is_highlighted": True,
                    "highlight_color": "red",
                },
                {
                    "number": 1,
                    "name": "偽名2",
                    "id": "fake2",
                    "content": "偽本文2",
                    "is_highlighted": False,
                    "highlight_color": None,
                },
            ],
        },
        thread_posts=_thread_posts(),
        default_title="既定タイトル",
    )

    assert result["thread_comments"] == [
        {
            "number": 3,
            "name": "風吹けば名無し",
            "id": "xyz789",
            "content": "元レス3",
            "is_highlighted": True,
            "highlight_color": "red",
        },
        {
            "number": 1,
            "name": "スレ主",
            "id": "Thread0P",
            "content": "元レス1",
            "is_highlighted": False,
            "highlight_color": None,
        },
    ]
