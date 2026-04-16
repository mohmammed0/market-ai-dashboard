# Event Contracts

هذه الوثيقة تمثل أول عقود أحداث رسمية بين طبقات المنصة.

## المسار

- `market.normalized.quote`
- `feature.snapshot.updated`
- `strategy.signal.generated`
- `risk.decision.made`
- `execution.order.created`
- `execution.fill.received`

## المصدر البرمجي

العقود موجودة في:

- [backend/app/eventing/contracts.py](/C:/Users/fas51/Desktop/market-ai-dashboard-backup/backend/app/eventing/contracts.py)

## الهدف

- تثبيت أسماء الـtopics
- تثبيت payloads الأساسية
- تجهيز المشروع لاحقًا لـNATS / JetStream أو أي event backbone
- جعل الربط بين `market_data -> features -> strategy -> risk -> execution` صريحًا بدل الاعتماد على استدعاءات غير موثقة
