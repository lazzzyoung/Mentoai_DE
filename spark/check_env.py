import os
from dotenv import load_dotenv

load_dotenv()

access_key = os.getenv("AWS_ACCESS_KEY_ID")
secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
bucket = os.getenv("S3_BUCKET_NAME")

print(f"🔑 Access Key: {access_key[:4]}**** (길이: {len(access_key) if access_key else 0})")
print(f"🔒 Secret Key: {'*' * 5} (길이: {len(secret_key) if secret_key else 0})")
print(f"🪣 Bucket Name: {bucket}")

if not access_key or not secret_key:
    print("❌ .env 파일에서 키를 읽어오지 못했습니다. 파일 위치나 내용을 확인하세요.")
else:
    print("✅ 환경변수 로딩 성공!")