# Backend/App Target Tree

هذا الملف يربط الشجرة المقترحة بالبنية الحالية بدون إعادة كتابة المشروع.

## ما أُضيف فعليًا الآن

- `backend/app/events`
- `backend/app/readmodels`
- `backend/app/workflows`
- `backend/app/adapters`
- `backend/app/observability`
- `packages/contracts`
- `workers/*` كـ scaffolds أولية
- `backend/app/domain/execution/*`
- `backend/app/domain/risk/*`

## المقصود من هذه الطبقات

- `events`: عقود وأدوات نشر موحّدة فوق modular monolith الحالي.
- `readmodels`: استجابات مجمعة للواجهة بدل تجميع البيانات في الصفحة.
- `workflows`: نقطة مركزية لتسجيل وتشغيل workflows الحالية.
- `adapters`: واجهات واضحة للـ broker وmarket data وباقي المزودين.
- `domain/execution`: state machine وidempotency وrouting للتنفيذ.
- `domain/risk`: pre-trade gate وسياسات المخاطر المنفصلة عن التنفيذ.
- `packages/contracts`: المصدر المشترك للعقود التي ستُستخدم لاحقًا بين الـ backend والـ workers.

## ما لم أفعله عمدًا بعد

- لم أنقل منطق التشغيل الحالي من `services/` أو `application/` إلى أماكنه الجديدة نقلاً كاملاً.
- لم أربط transports فعلية مثل `NATS/JetStream`.
- لم أستبدل routes الحالية أو frontend contracts.

السبب: الهدف في هذه المرحلة هو بناء الشجرة الصحيحة مع واجهات توافقية، مع إبقاء النظام الحالي شغالًا وقابلًا للاختبار.
