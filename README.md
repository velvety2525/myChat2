# 📘 규정 RAG 챗봇

`regulations/` 폴더의 규정 문서를 근거로 답변하는 RAG 챗봇입니다. 답변 모델로 **Claude** 또는 **Gemini**를 선택할 수 있습니다.

두 가지 형태로 실행할 수 있습니다.

| | 웹 앱 (`public/` + `api/`) | Streamlit 앱 (`streamlit_app.py`) |
|---|---|---|
| 배포 | **Vercel** | Streamlit Community Cloud / 로컬 |
| 검색 | 미리 만든 색인(`.index_cache/`)만 사용 | 규정 폴더를 직접 읽음 (+ Gemini 의미 검색 옵션) |

## Vercel 배포

1. https://vercel.com 에 GitHub 계정으로 로그인 → **Add New… → Project**
2. `velvety2525/myChat2` 저장소 **Import**
3. Framework Preset은 **Other** 그대로, 설정 변경 없이 **Deploy**
4. 배포된 주소에 접속 → 왼쪽 설정에서 API 키 입력 후 질문

- (선택) Project Settings → Environment Variables에 `ANTHROPIC_API_KEY` / `GEMINI_API_KEY`를 넣으면 키 입력 없이 사용할 수 있습니다.
  **단, 공개 주소라면 누구나 그 키로 요금을 쓰게 되므로** Settings → Deployment Protection 등으로 접근을 제한하세요.
- Vercel 함수에는 원본 PDF를 올리지 않고(`.vercelignore`), 커밋된 색인 `.index_cache/chunks_*.json`만 사용합니다.

### 규정 파일을 바꿨을 때

```bash
python scripts/build_index.py
```

`regulations/`를 다시 읽어 `.index_cache/`를 갱신합니다(큰 PDF는 수 분). 규정 파일과 `.index_cache/`를 함께 커밋·푸시하면 Vercel이 자동으로 재배포합니다.

## 로컬 실행

```bash
pip install -r requirements.txt
python scripts/dev_server.py        # 웹 앱 → http://localhost:3000
```

Streamlit 앱:

```bash
pip install -r requirements.txt streamlit
streamlit run streamlit_app.py
```

## Streamlit Community Cloud 배포

https://share.streamlit.io → **Create app** → Repository `velvety2525/myChat2`, Main file path `streamlit_app.py` → **Deploy**

## API 키

- Claude: https://console.anthropic.com/settings/keys (크레딧 충전 필요)
- Gemini: https://aistudio.google.com/apikey (무료 등급 있음)

웹 앱에서 입력한 키는 답변 생성 요청에만 쓰이며 서버에 저장되지 않습니다. "이 브라우저에 키 저장"을 켜면 해당 브라우저(localStorage)에만 저장됩니다.

## 동작 방식

- **청킹**: `제N조(제목)` 단위로 자르고 소속 `제N장`을 붙입니다. 조문 구조가 없거나 길면 약 900자 단위로 겹쳐 자릅니다. PDF는 페이지 번호를 기록합니다.
- **규정집 PDF**: 여러 규정을 묶은 PDF는 페이지 머리글(`문서번호` 블록)에서 규정명을 읽어 각 조문에 붙이고(예: `취업규칙(KCS-B-301) · 제64조(연가)`), 머리글은 본문에서 제거합니다.
- **캐시**: 파일 내용 해시 기준으로 `.index_cache/chunks_*.json`에 저장하며, 폴더에서 사라진 파일의 캐시는 자동 삭제합니다.
- **검색**: 한국어 음절 bigram 기반 BM25 키워드 검색. Streamlit 앱에서는 Gemini 임베딩 의미 검색을 결합(RRF)할 수 있습니다.
- **생성**: 검색된 조항만 근거로 답하고, 근거가 없으면 "찾을 수 없다"고 답하도록 지시합니다. 최근 대화 몇 턴을 함께 보내 후속 질문도 처리합니다.

## 참고

- 지원 형식: PDF, DOCX, TXT, MD. HWP는 PDF/DOCX로 변환해 넣어 주세요.
- 스캔 이미지 PDF는 텍스트 추출이 되지 않습니다 (OCR 필요).

## 구조

```
public/index.html   웹 UI
api/chat.py         POST /api/chat  (검색 + 답변 스트리밍, NDJSON)
api/info.py         GET  /api/info  (규정 수, 모델 목록)
streamlit_app.py    Streamlit UI
rag/                로더 · 청킹 · 검색 · LLM · 색인 캐시 · 웹 API 공통 로직
scripts/            build_index.py(색인 생성), dev_server.py(로컬 웹 서버)
regulations/        규정 파일
.index_cache/       색인 캐시 (커밋)
```
