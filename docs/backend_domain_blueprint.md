# Backend Domain Blueprint

هذه الوثيقة تمثل المرحلة الأولى من نقل الباكند إلى بنية domain-driven أوضح
بدون كسر المسارات الحالية.

## الهدف

- تثبيت حدود واضحة بين `control plane` و`trading core`
- عزل التنفيذ عن طبقة الذكاء الاصطناعي
- إبقاء النظام الحالي شغالًا أثناء إعادة التنظيم

## الحدود الجديدة

- `backend/app/control`
  - auth
  - settings
  - admin orchestration
  - BFF aggregation
- `backend/app/market_data`
  - market facts
  - provider normalization
  - historical/raw ingestion
- `backend/app/features`
  - indicators
  - breadth
  - derived snapshots
- `backend/app/strategy`
  - signals
  - ranking
  - trade intents only
- `backend/app/risk`
  - exposure rules
  - sizing controls
  - execution gating
- `backend/app/execution`
  - paper/live order lifecycle
  - broker routing
  - audit and reconciliation
- `backend/app/portfolio`
  - positions
  - portfolio snapshot aggregation
  - pnl and exposure views
- `backend/app/broker`
  - provider-facing broker state and adapters
- `backend/app/automation`
  - workflows
  - schedules
  - recurring jobs
- `backend/app/research`
  - backtesting
  - replay
  - evaluation
- `backend/app/ai`
  - explanation
  - narrative
  - controlled planning only

## المرحلة الحالية

في هذه المرحلة تم إنشاء facades رسمية للدومينات التالية:

- `execution`
- `portfolio`
- `broker`
- `risk`
- `market_data`
- `features`
- `strategy`

الـ API routes أصبحت تستورد من هذه الحدود الجديدة بدل الوصول مباشرة إلى
الطبقات القديمة. التنفيذ الداخلي لا يزال يعتمد على الخدمات الحالية، لكن
الواجهة المعمارية أصبحت جاهزة للانتقال التدريجي.

## قواعد التطوير من الآن

- أي route جديدة للتنفيذ يجب أن تستورد من `backend.app.execution`
- أي route جديدة للمحفظة يجب أن تستورد من `backend.app.portfolio`
- أي route جديدة للوسيط يجب أن تستورد من `backend.app.broker`
- أي منطق مخاطر جديد يجب أن يمر عبر `backend.app.risk`
- أي route جديدة لحقائق السوق يجب أن تستورد من `backend.app.market_data`
- أي features أو breadth logic يجب أن يمر عبر `backend.app.features`
- أي تحليل أو ranking أو scan logic يجب أن يمر عبر `backend.app.strategy`
- الـ AI لا يستدعي broker أو execution مباشرة
- strategy ينتج intents فقط، وليس أوامر broker

## الخطوة التالية

1. فصل risk gating داخل execution pipeline
2. نقل recurring jobs إلى طبقة `automation`
3. عزل AI orchestration في طبقة `ai`
4. إضافة event contracts بين `market_data -> features -> strategy -> risk -> execution`
