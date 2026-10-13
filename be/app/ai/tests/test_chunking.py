"""청킹이 원문 위치를 지키며 기록을 나누는지 검증한다."""

import json
from pathlib import Path

from app.ai.contracts import RecordBlock, SourceLocation
from app.ai.features.retrieval.chunking import (
    CHUNK_MAX_CHARS,
    CHUNK_OVERLAP_CHARS,
    chunk_document,
    chunk_ledger,
)

FIXTURES = Path(__file__).parent / "fixtures" / "records"


def _fixture_blocks(name: str) -> list[RecordBlock]:
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return [RecordBlock.model_validate(block) for block in data["parse_result"]["blocks"]]


def _rows(sheet: str | None, count: int, start: int = 2, length: int = 50) -> list[RecordBlock]:
    """`length`자 행 `count`개. 시트가 없으면 CSV 라벨이다"""
    blocks = []
    for number in range(start, start + count):
        label = f"{number}행" if sheet is None else f"{sheet} · {number}행"
        text = f"{number}행: " + "가" * (length - len(f"{number}행: "))
        blocks.append(RecordBlock(text=text, location=SourceLocation(label=label)))
    return blocks


def _labels(chunks) -> list[str]:
    return [chunk.location.label for chunk in chunks]


# --- 장부 -------------------------------------------------------------------


def test_XLSX_장부는_시트별로_묶이고_라벨에_행_범위가_붙는다():
    chunks = chunk_ledger(_fixture_blocks("ledger_2025_h1"))

    assert _labels(chunks) == [
        "회비 수납 시트 · 2~15행",
        "회비 수납 시트 · 16~28행",
        "지출 시트 · 2~9행",
    ]
    assert [chunk.block_indexes for chunk in chunks] == [
        tuple(range(0, 14)),
        tuple(range(14, 27)),
        tuple(range(27, 35)),
    ]


def test_CSV_장부는_시트_없이_행_범위만_라벨에_붙는다():
    chunks = chunk_ledger(_fixture_blocks("ledger_2024_h2"))

    assert _labels(chunks) == ["2~7행"]
    assert chunks[0].block_indexes == tuple(range(6))


def test_청크_본문은_원본_행을_줄바꿈으로_이은_것이다():
    blocks = _fixture_blocks("ledger_2024_h2")

    chunks = chunk_ledger(blocks)

    assert chunks[0].text == "\n".join(block.text for block in blocks)


def test_모든_행이_정확히_한_청크에_들어간다():
    """겹치지 않아야 #72에서 같은 행을 두 번 세지 않는다"""
    blocks = _fixture_blocks("ledger_2025_h1")

    chunks = chunk_ledger(blocks)

    indexes = [index for chunk in chunks for index in chunk.block_indexes]
    assert indexes == list(range(len(blocks)))


def test_청크는_최대_글자_수를_넘지_않는다():
    chunks = chunk_ledger(_rows("회비", 100))

    assert all(len(chunk.text) <= CHUNK_MAX_CHARS for chunk in chunks)


def test_마지막_청크에_몇_행만_남지_않게_고르게_나눈다():
    """앞에서부터 채우면 19행 + 2행이 된다"""
    chunks = chunk_ledger(_rows("회비", 21))

    assert [len(chunk.block_indexes) for chunk in chunks] == [11, 10]


def test_시트가_다른_행은_한_청크에_섞이지_않는다():
    chunks = chunk_ledger(_rows("회비", 3) + _rows("지출", 2))

    assert _labels(chunks) == ["회비 · 2~4행", "지출 · 2~3행"]


def test_한_행만_있으면_범위_없이_그_행을_적는다():
    chunks = chunk_ledger(_rows("지출", 1, start=5))

    assert _labels(chunks) == ["지출 · 5행"]


def test_시트_이름에_구분자가_있어도_마지막_구분자로_나눈다():
    chunks = chunk_ledger(_rows("2025 · 상반기", 2))

    assert _labels(chunks) == ["2025 · 상반기 · 2~3행"]


def test_최대_글자_수보다_긴_행은_자르지_않고_혼자_둔다():
    long_row = _rows("회비", 1, start=4, length=CHUNK_MAX_CHARS + 200)
    blocks = _rows("회비", 2) + long_row + _rows("회비", 2, start=5)

    chunks = chunk_ledger(blocks)

    assert _labels(chunks) == ["회비 · 2~3행", "회비 · 4행", "회비 · 5~6행"]
    assert chunks[1].text == long_row[0].text


def test_라벨_형식이_다른_블록은_묶지_않고_라벨_그대로_둔다():
    """추측해서 묶으면 출처가 틀릴 수 있다"""
    odd = RecordBlock(text="날짜: 2025-03-04", location=SourceLocation(label="회비 수납 시트"))
    blocks = _rows("회비 수납 시트", 2) + [odd] + _rows("회비 수납 시트", 1, start=5)

    chunks = chunk_ledger(blocks)

    assert _labels(chunks) == [
        "회비 수납 시트 · 2~3행",
        "회비 수납 시트",
        "회비 수납 시트 · 5행",
    ]
    assert [chunk.block_indexes for chunk in chunks] == [(0, 1), (2,), (3,)]


# --- 문서 -------------------------------------------------------------------


def _page(text: str, label: str = "1쪽") -> list[RecordBlock]:
    return [RecordBlock(text=text, location=SourceLocation(label=label))]


def test_회칙은_조_단위로_나뉘고_라벨에_쪽과_조_제목이_붙는다():
    chunks = chunk_document(_fixture_blocks("rules_2024"))

    assert _labels(chunks) == [
        "1쪽 · 제1조(명칭)",
        "1쪽 · 제2조(목적)",
        "2쪽 · 제8조(학기 회비)",
        "2쪽 · 제9조(행사 참가비)",
        "2쪽 · 제10조(참가비 환불)",
        "3쪽 · 제11조(예비비)",
        "3쪽 · 제12조(지출 승인)",
    ]
    assert [chunk.block_indexes for chunk in chunks] == [(0,), (0,), (1,), (1,), (1,), (2,), (2,)]


def test_조_안의_번호_줄은_제목이_아니라_그_조의_항목으로_남는다():
    chunks = chunk_document(_fixture_blocks("rules_2024"))

    refund = chunks[4]
    assert refund.text.splitlines()[1:] == [
        "1. 행사 시작 7일 전까지: 전액",
        "2. 행사 시작 3일 전까지: 50%",
        "3. 그 이후: 환불하지 않는다.",
    ]


def test_제목만_있는_줄은_다음_섹션_앞에_붙는다():
    chunks = chunk_document(_fixture_blocks("rules_2024"))

    assert chunks[2].text.startswith("제3장 회비\n제8조(학기 회비)")


def test_결과보고는_번호_소제목으로_나뉘고_표는_한_청크에_남는다():
    chunks = chunk_document(_fixture_blocks("mt_2025_spring_report"))

    assert _labels(chunks) == ["1쪽 · 1. 행사 개요", "2쪽 · 2. 예산", "2쪽 · 3. 정산", "3쪽 · 4. 회고"]
    assert chunks[0].text.startswith("2025 봄 MT 결과보고\n1. 행사 개요")
    assert chunks[1].text.splitlines()[1:] == [
        "항목 예산 실제",
        "숙소 550,000 550,000",
        "식비 400,000 412,000",
        "물품 180,000 168,000",
        "예비비 130,000 172,000",
        "합계 1,260,000 1,302,000",
    ]


def test_문서의_모든_줄이_청크_어딘가에_들어간다():
    for name in ("rules_2024", "mt_2025_spring_report"):
        blocks = _fixture_blocks(name)

        chunks = chunk_document(blocks)

        lines = [line for block in blocks for line in block.text.splitlines()]
        chunked = [line for chunk in chunks for line in chunk.text.splitlines()]
        assert chunked == lines, name


def test_제목이_없는_쪽은_쪽_번호만_라벨로_쓴다():
    chunks = chunk_document(_page("모임 장소는 학생회관 3층이다.\n시간은 저녁 7시다.", "4쪽"))

    assert _labels(chunks) == ["4쪽"]


def test_콜론이_있거나_문장인_번호_줄은_제목이_아니다():
    text = "1. 준비물\n1. 집결: 정문 앞\n2. 회비를 미리 낸다."

    chunks = chunk_document(_page(text))

    assert _labels(chunks) == ["1쪽 · 1. 준비물"]


def test_줄_앞의_조_인용은_제목이_아니다():
    text = "제5조(회의) 회의는 매달 연다.\n제10조에 따라 환불한다."

    chunks = chunk_document(_page(text))

    assert _labels(chunks) == ["1쪽 · 제5조(회의)"]


def test_번호가_거꾸로_가는_목록은_소제목이_아니라_쪽_라벨로_둔다():
    text = "1. 행사 개요\n일시: 4월\n2. 예산\n총 30만원\n1. 숙소비 20만원\n2. 식비 10만원"

    chunks = chunk_document(_page(text))

    assert [(chunk.location.label, chunk.text) for chunk in chunks][1:] == [
        ("1쪽 · 2. 예산", "2. 예산\n총 30만원"),
        ("1쪽", "1. 숙소비 20만원\n2. 식비 10만원"),
    ]


def test_거꾸로_간_목록_뒤에_다음_번호가_오면_다시_소제목으로_본다():
    text = "2. 예산\n총 30만원\n1. 숙소비 20만원\n2. 식비 10만원\n3. 정산\n4만원 초과"

    chunks = chunk_document(_page(text))

    assert _labels(chunks) == ["1쪽 · 2. 예산", "1쪽", "1쪽 · 3. 정산"]


def test_조_제목은_띄어쓰기_전각_괄호_대괄호도_알아본다():
    text = "제10조 (참가비 환불) 전액 환불한다.\n제11조（벌칙） 경고한다.\n제12조[지출] 총무가 승인한다."

    chunks = chunk_document(_page(text, "2쪽"))

    assert _labels(chunks) == ["2쪽 · 제10조 (참가비 환불)", "2쪽 · 제11조（벌칙）", "2쪽 · 제12조[지출]"]


def test_가지_조항도_따로_나눈다():
    text = "제10조(참가비 환불) 전액 환불한다.\n제10조의2(환불 신청) 총무에게 신청한다."

    chunks = chunk_document(_page(text, "2쪽"))

    assert _labels(chunks) == ["2쪽 · 제10조(참가비 환불)", "2쪽 · 제10조의2(환불 신청)"]


def test_괄호_제목이_붙은_장도_다음_조_앞에_붙는다():
    blocks = _pages("제1조(명칭) 큰나무라 한다.", "제2장(회비)\n제8조(학기 회비) 매 학기 낸다.")

    chunks = chunk_document(blocks)

    assert [(chunk.location.label, chunk.text) for chunk in chunks][1:] == [
        ("2쪽 · 제8조(학기 회비)", "제2장(회비)\n제8조(학기 회비) 매 학기 낸다."),
    ]


def _pages(*texts: str, first: int = 1) -> list[RecordBlock]:
    return [
        RecordBlock(text=text, location=SourceLocation(label=f"{number}쪽"))
        for number, text in enumerate(texts, start=first)
    ]


def test_쪽을_넘어_이어지는_조의_문장은_다음_조_라벨을_받지_않는다():
    blocks = _pages(
        "제10조(참가비 환불) 행사 시작 7일 전까지 취소하면 참가비를 전액",
        "환불하지 않는다.\n제11조(벌칙) 회칙을 어긴 회원은 경고한다.",
        first=2,
    )

    chunks = chunk_document(blocks)

    assert [(chunk.location.label, chunk.text) for chunk in chunks] == [
        ("2쪽 · 제10조(참가비 환불)", "제10조(참가비 환불) 행사 시작 7일 전까지 취소하면 참가비를 전액"),
        ("3쪽", "환불하지 않는다."),
        ("3쪽 · 제11조(벌칙)", "제11조(벌칙) 회칙을 어긴 회원은 경고한다."),
    ]


def test_쪽을_넘어_이어지는_조의_번호_줄은_소제목이_아니다():
    blocks = _pages(
        "제10조(참가비 환불) 다음과 같이 환불한다.\n1. 7일 전까지 전액",
        "2. 3일 전까지 절반 환불\n3. 당일 환불 불가\n제11조(벌칙) 경고한다.",
        first=2,
    )

    chunks = chunk_document(blocks)

    assert [(chunk.location.label, chunk.text) for chunk in chunks][1:] == [
        ("3쪽", "2. 3일 전까지 절반 환불\n3. 당일 환불 불가"),
        ("3쪽 · 제11조(벌칙)", "제11조(벌칙) 경고한다."),
    ]


def test_줄_앞에_온_조문_참조는_새_조가_아니다():
    text = (
        "제10조(참가비 환불) 참가비는 환불한다. 다만\n"
        "제9조 제2항에 해당하는 회원은 제외한다. 또한\n"
        "제7조 및 제8조를 어긴 회원과\n"
        "제3조 또는 제4조의 회원도 같다."
    )

    chunks = chunk_document(_page(text, "2쪽"))

    assert _labels(chunks) == ["2쪽 · 제10조(참가비 환불)"]


def test_괄호_제목이_없는_조도_참조가_아니면_조로_본다():
    text = "제10조 참가비는 환불한다.\n제11조 회칙을 어긴 회원은 경고한다."

    chunks = chunk_document(_page(text, "2쪽"))

    assert _labels(chunks) == ["2쪽 · 제10조", "2쪽 · 제11조"]


def test_쪽_끝에_제목만_남아도_버리지_않는다():
    chunks = chunk_document(_page("제1조(명칭) 큰나무라 한다.\n제2장 회원"))

    assert [chunk.text for chunk in chunks] == ["제1조(명칭) 큰나무라 한다.", "제2장 회원"]


def test_긴_섹션은_줄_경계에서_겹치게_잘린다():
    lines = [f"{number:02d}번째 줄: " + "가" * 50 for number in range(40)]

    chunks = chunk_document(_page("\n".join(lines)))

    assert len(chunks) > 1
    assert all(len(chunk.text) <= CHUNK_MAX_CHARS for chunk in chunks)
    assert _labels(chunks) == ["1쪽"] * len(chunks)
    for before, after in zip(chunks, chunks[1:]):
        shared = after.text.splitlines()[0]
        assert shared in before.text.splitlines()  # 앞 조각의 끝 줄로 시작한다
        assert len(shared) <= CHUNK_OVERLAP_CHARS


def test_최대_글자_수보다_긴_한_줄은_문장_단위로_나눈다():
    sentence = "가" * 99 + "."
    line = " ".join([sentence] * 25)  # 줄바꿈 없는 2,524자 문단

    chunks = chunk_document(_page(line))

    assert len(chunks) > 1
    assert all(len(chunk.text) <= CHUNK_MAX_CHARS for chunk in chunks)
    assert all(chunk.text.endswith(".") for chunk in chunks)
