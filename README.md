# 📘 규정 RAG 챗봇

`regulations/` 폴더에 넣은 규정 문서를 근거로 답변하는 RAG 챗봇입니다. 답변 모델로 **Claude** 또는 **Gemini**를 선택할 수 있습니다.

## 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

1. `regulations/` 폴더에 규정 파일을 넣습니다 (하위 폴더 가능). 지원 형식: **PDF, DOCX, TXT, MD**
2. 브라우저에서 사이드바의 **모델 제공사**(Claude/Gemini)를 고르고 **API Key**를 입력합니다.
3. 질문하면 관련 조항을 찾아 근거(`[문서명 제N조]`)와 함께 답변합니다. 답변 아래 `📎 참고한 규정`에서 원문을 확인할 수 있습니다.

파일을 추가·수정하면 자동으로 다시 색인됩니다 (수동: `🔄 다시 색인`).

## 설정 (선택)

| 환경변수 | 설명 |
|---|---|
| `REGULATIONS_DIR` | 규정 폴더 경로 (기본값: `./regulations`). 사이드바에서도 변경 가능 |
| `ANTHROPIC_API_KEY` | 지정 시 Claude 키 입력란에 미리 채워짐 |
| `GEMINI_API_KEY` | 지정 시 Gemini 키 입력란에 미리 채워짐 |

`.streamlit/secrets.toml`에 같은 이름으로 넣어도 됩니다. API 키는 저장소에 커밋하지 마세요.

## 배포 (Streamlit Community Cloud)

1. https://share.streamlit.io 에 GitHub 계정으로 로그인 → **Create app** → **Deploy a public app from GitHub**
2. Repository `velvety2525/myChat2`, Branch `claude/zen-euler-ovu48t`(또는 기본 브랜치), Main file path `app.py` → **Deploy**
3. 사용자는 사이드바에 각자 API 키를 입력해 사용합니다.

- 앱이 공개 상태일 때 **Secrets에 API 키를 넣으면 누구나 그 키로 요금을 쓰게 됩니다.** 키를 미리 넣어 두려면 앱 설정에서 열람자를 제한(Sharing → Only specific people)하세요.
- 규정 파일과 `.index_cache/chunks_*.json`(미리 읽어 둔 결과)을 함께 커밋하면 클라우드에서 앱이 깨어날 때 PDF를 다시 읽지 않습니다. 규정 파일을 바꾸면 로컬에서 한 번 실행한 뒤 새로 생긴 캐시 파일도 같이 커밋하세요.

## 동작 방식

- **청킹**: 규정 문서는 `제N조(제목)` 단위로 자르고, 소속 `제N장`을 함께 붙입니다. 조문 구조가 없거나 조문이 길면 약 900자 단위로 겹쳐 자릅니다. PDF는 페이지 번호를 기록합니다.
- **규정집 PDF**: 여러 규정을 묶은 PDF는 페이지 머리글(`문서번호` 블록)에서 규정명을 읽어 각 조문에 붙이고(예: `취업규칙(KCS-B-301) · 제64조(연가)`), 머리글은 본문에서 제거합니다.
- **캐시**: 큰 PDF는 처음 읽을 때 수 분이 걸리므로 결과를 `.index_cache/`에 저장해 두고, 파일이 바뀌지 않으면 다시 읽지 않습니다.
- **검색**: 한국어 음절 bigram 기반 BM25 키워드 검색 (별도 임베딩 API 불필요).
  Gemini 사용 시 `gemini-embedding-001` 의미 검색을 결합한 하이브리드 검색(RRF)을 켤 수 있으며, 임베딩은 `.index_cache/`에 캐시됩니다.
- **생성**: 검색된 조항만 근거로 답하고, 근거가 없으면 "찾을 수 없다"고 답하도록 지시합니다. 최근 대화 몇 턴을 함께 보내 후속 질문도 처리합니다.

## 참고

- 스캔 이미지로 된 PDF는 텍스트 추출이 되지 않습니다 (OCR 후 넣어 주세요).
- HWP 파일은 지원하지 않으므로 PDF나 DOCX로 변환해 넣어 주세요.
- 목록에 없는 모델은 모델 선택에서 `직접 입력`으로 모델 ID를 지정할 수 있습니다.

## 구조

```
app.py            Streamlit UI
rag/loader.py     파일 읽기 (PDF/DOCX/TXT/MD)
rag/chunker.py    조문 단위 청킹
rag/retriever.py  BM25 + (선택) Gemini 임베딩 하이브리드 검색
rag/llm.py        프롬프트 및 Claude/Gemini 스트리밍 호출
regulations/      ← 규정 파일을 넣는 폴더
```
