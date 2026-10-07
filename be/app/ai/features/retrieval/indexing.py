"""기록 색인: 청크에 임베딩을 붙인다."""

from .schemas import TextChunk


def embedding_input(file_name: str, chunk: TextChunk) -> str:
    """임베딩 API에 보낼 글. 본문 앞에 문서명과 위치를 붙인다.

    본문에 "2025 봄 MT"가 없어도 파일명으로 찾게 하기 위해서다.
    이 글은 벡터를 만드는 데만 쓰고 저장하지 않는다. 저장되는 청크 text에는 붙이지 않는다.
    text는 검색 결과로 돌아와 근거로 쓰이므로 PDF 원문과 같아야 하고,
    문서명·위치는 검색 결과에 따로 온다.
    """
    return f"문서: {file_name}\n위치: {chunk.location.label}\n\n{chunk.text}"
