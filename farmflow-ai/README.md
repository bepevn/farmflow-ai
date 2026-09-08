# FarmFlow AI (MVP)

휴경농지 · 신규 농업인 · 유통업체를 연결하는 AI 유통 플랫폼의 MVP입니다.
회원가입/로그인, 매물(휴경농지·농산물) 등록/조회 기능을 제공합니다.

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 1. 깃허브에 코드 올리기

이 폴더 전체를 압축 해제한 뒤, 터미널에서 순서대로 실행하세요.
(먼저 github.com에서 새 저장소를 하나 만들어두세요. 예: `farmflow-ai`, Public/Private 아무거나 상관없음)

```bash
cd farmflow-ai
git init
git add .
git commit -m "Initial commit: FarmFlow AI MVP"
git branch -M main
git remote add origin https://github.com/<본인_아이디>/farmflow-ai.git
git push -u origin main
```

- `<본인_아이디>`를 실제 깃허브 아이디로 바꿔주세요.
- push 시 아이디/비밀번호를 물어보면, 비밀번호 자리에 깃허브 **Personal Access Token**을 입력해야 합니다.
  (Settings → Developer settings → Personal access tokens 에서 발급)

## 2. Streamlit Community Cloud로 배포하기 (깃허브 코드 자동 연동)

1. https://share.streamlit.io 접속 → 깃허브 계정으로 로그인
2. **"New app"** 클릭
3. Repository: 방금 올린 `farmflow-ai` 선택
4. Branch: `main`
5. Main file path: `app.py`
6. **Deploy** 클릭

배포가 끝나면 `https://<앱이름>.streamlit.app` 형태의 링크가 생성되고,
이후 깃허브 저장소에 새로 `git push` 할 때마다 앱이 자동으로 다시 배포됩니다.

## 주의사항 (중요)

- 현재 회원/매물 데이터는 SQLite 파일(`farmflow.db`)에 저장됩니다.
  Streamlit Community Cloud는 앱을 재시작하거나 재배포할 때 파일 시스템이 초기화될 수 있어
  **데이터가 사라질 수 있습니다.** (테스트/데모용으로는 충분하지만, 실제 서비스라면
  Supabase, PlanetScale, Turso 같은 외부 DB로 교체를 권장합니다.)
- `farmflow.db`는 `.gitignore`에 포함되어 있어 깃허브에는 올라가지 않습니다.

## 폴더 구조

```
farmflow-ai/
├── app.py               # 메인 스트림릿 앱
├── requirements.txt     # 의존성
├── .gitignore
└── .streamlit/
    └── config.toml      # 테마 설정
```

## 다음 단계 (계획서 기준 확장 아이디어)

- 역할별(농가/유통업체/토지소유자) 맞춤 대시보드 분리
- AI 시세 예측, 도매처 추천 로직 추가 (scikit-learn/XGBoost)
- 공공데이터포털 API(농산물 가격, 기상청 등) 연동
- 지도 기반 휴경농지 위치 표시 (folium/streamlit-folium)
