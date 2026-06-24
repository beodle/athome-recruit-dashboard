"""
YouTube Analytics OAuth 인증 (1회) — 앳홈 채널 시청 지속률용 refresh token 발급.

사용: python3 youtube_oauth.py "/path/to/client_secret_xxx.json"
  → 브라우저 열림 → 앳홈 채널을 관리하는 계정/브랜드 선택 → 승인
  → youtube_token.json 저장 (refresh_token 포함). 이 파일은 .gitignore(*.json)로 커밋 안 됨.

발급된 refresh_token + client_id/secret은 이후 GitHub Secret으로 넣어 Actions 자동 갱신에 사용.
"""
import sys, json, pathlib
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]


def main():
    if len(sys.argv) < 2:
        raise SystemExit("사용: python3 youtube_oauth.py <client_secret.json 경로>")
    client_file = sys.argv[1]
    flow = InstalledAppFlow.from_client_secrets_file(client_file, scopes=SCOPES)
    # prompt=consent + offline → refresh_token 확보 / 여러 채널이면 브라우저에서 선택
    # select_account → 계정/브랜드 채널 선택 화면 강제 (앳홈 채널 선택용)
    creds = flow.run_local_server(port=8088, prompt="select_account consent", access_type="offline")

    out = pathlib.Path(__file__).with_name("youtube_token.json")
    out.write_text(json.dumps({
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "token_uri": creds.token_uri,
        "scopes": list(creds.scopes or SCOPES),
    }, ensure_ascii=False))
    print(f"✅ youtube_token.json 저장 (refresh_token {'있음' if creds.refresh_token else '없음!'})")


if __name__ == "__main__":
    main()
