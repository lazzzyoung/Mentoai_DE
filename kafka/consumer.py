# kafka/consumer.py
import json
from kafka import KafkaConsumer

def run_consumer():
    topic_name = 'career_raw'
    print(f"👀 '{topic_name}' 토픽 감시 중... (Ctrl+C로 종료)")

    # Consumer 설정
    consumer = KafkaConsumer(
        topic_name,
        bootstrap_servers=['localhost:9092'],
        auto_offset_reset='earliest', 
        enable_auto_commit=True,
        group_id='mentoai-group',     
        value_deserializer=lambda x: json.loads(x.decode('utf-8'))
    )

    try:
        for message in consumer:
            data = message.value
            print(f"\n📨 [Received] Offset: {message.offset}")
            print(f"   🏢 회사: {data.get('company')}")
            print(f"   📝 제목: {data.get('title')}")
            print(f"   💰 급여: {data.get('pay')}")
            print(f"   🎓 학력: {data.get('education')} / 경력: {data.get('experience')}")
            print(f"   📍 위치: {data.get('location')}")
            print(f"   📅 마감: {data.get('deadline')} (등록: {data.get('reg_date')})")
            print(f"   🔗 링크: {data.get('link')}")
            print("-" * 50)
            
    except KeyboardInterrupt:
        print("\n👋 컨슈머를 종료합니다.")
    finally:
        consumer.close()

if __name__ == "__main__":
    run_consumer()