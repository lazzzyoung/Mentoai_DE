import os
import sys
import json
import time
import logging
import requests
from dotenv import load_dotenv
from kafka import KafkaProducer
from kafka.errors import KafkaError
load_dotenv() 

sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

from utils.wanted_scraper import fetch_job_id_list, fetch_job_detail_raw


# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WantedProducer")

BASE_URL = os.getenv('WANTED_BASE_URL')
GROUP_ID = os.getenv('TARGET_JOB_GROUP') # 개발
JOB_ID_CODE = os.getenv('TARGET_JOB_ID') # 데이터 엔지니어
BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
TOPIC_NAME = os.getenv('KAFKA_TOPIC_NAME', 'career_raw')

def run_producer():
    logger.info("🎬 Wanted Producer 시작...")
    
    try:
        producer = KafkaProducer(
            bootstrap_servers=[BOOTSTRAP_SERVERS],
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda v: str(v).encode('utf-8'),
            retries=3  
        )
        logger.info(f"Kafka Connected: {BOOTSTRAP_SERVERS}")
    except Exception as e:
        logger.critical(f"Kafka 연결 실패! Error: {e}")
        return

   
    with requests.Session() as session:
        
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': BASE_URL
        })

        # ID 리스트 수집
        logger.info("공고 ID 리스트 수집 중...")
        target_ids = fetch_job_id_list(session, BASE_URL, GROUP_ID, JOB_ID_CODE, limit=50)
        
        if not target_ids:
            logger.warning("⚠️ 수집된 공고 ID가 없습니다. 종료합니다.")
            producer.close()
            return

        logger.info(f"👉 총 {len(target_ids)}개의 공고 상세 정보를 수집합니다.")

        # 상세 정보 수집 및 Kafka 전송
        success_count = 0
        fail_count = 0

        for job_id in target_ids:
            try:
               
                raw_data = fetch_job_detail_raw(session, BASE_URL, job_id)
                
                if not raw_data:
                    fail_count += 1
                    continue 

                message = {
                    "source": "wanted",
                    "source_id": str(job_id),
                    "collected_at": time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    "raw_data": raw_data 
                }

                producer.send(
                    TOPIC_NAME,
                    key=str(job_id), # Log Compaction을 위한 Key 설정
                    value=message
                )
                
                success_count += 1
                if success_count % 10 == 0:
                    logger.info(f"   ... {success_count}건 전송 완료")
                
                time.sleep(0.5)

            except KafkaError as ke:
                logger.error(f"⚠️ Kafka 전송 에러 (ID: {job_id}): {ke}")
                fail_count += 1
            except Exception as e:
                logger.error(f"⚠️ 알 수 없는 에러 (ID: {job_id}): {e}")
                fail_count += 1
                continue 

  
        producer.flush() 
        producer.close()
        logger.info(f"작업 완료! 성공: {success_count}, 실패: {fail_count}")

if __name__ == "__main__":
    run_producer()