# نشر المنصة على Hetzner

هذا المسار مناسب لسيرفر `CPX42` ويعتمد على:

- `Docker Compose` لتشغيل التطبيق
- `PostgreSQL` و`Redis` من داخل المشروع
- `Nginx` على السيرفر لاستقبال الدومين و`SSL`
- تشغيل `backend` و`frontend` و`scheduler` بشكل دائم

## قبل البدء

تأكد من توفر هذه العناصر على السيرفر:

- Ubuntu 24.04 أو 22.04
- مستخدم يملك صلاحية `sudo`
- دومين أو ساب دومين يشير إلى IP السيرفر
- مفاتيح Alpaca إذا كنت ستستخدم الوسيط أو market data

## 1. تثبيت Docker و Nginx

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg nginx certbot python3-certbot-nginx
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

سجل خروج ثم ادخل مرة أخرى حتى تعمل مجموعة `docker`.

## 2. سحب المشروع

```bash
cd /opt
sudo mkdir -p market-ai-dashboard
sudo chown "$USER":"$USER" market-ai-dashboard
git clone https://github.com/<your-user>/<your-repo>.git /opt/market-ai-dashboard
cd /opt/market-ai-dashboard
```

## 3. إعداد ملف البيئة للإنتاج

```bash
cp .env.production.example .env.production
```

حدّث القيم التالية داخل `.env.production`:

- `MARKET_AI_POSTGRES_PASSWORD`
- `MARKET_AI_DATABASE_URL`
- `MARKET_AI_PUBLIC_WEB_ORIGIN`
- `MARKET_AI_PUBLIC_API_ORIGIN`
- `MARKET_AI_SERVER_NAME`
- `MARKET_AI_TRUSTED_HOSTS`
- `MARKET_AI_ALLOWED_ORIGINS`
- `MARKET_AI_AUTH_DEFAULT_PASSWORD`
- `MARKET_AI_AUTH_SECRET_KEY`

إعدادات مقترحة للتداول الورقي كل 5 دقائق:

```dotenv
MARKET_AI_ENV=production
MARKET_AI_BACKEND_PUBLISHED_PORT=8000
MARKET_AI_FRONTEND_PUBLISHED_PORT=4173

MARKET_AI_PUBLIC_WEB_ORIGIN=https://app.example.com
MARKET_AI_PUBLIC_API_ORIGIN=https://app.example.com
MARKET_AI_SERVER_NAME=app.example.com
MARKET_AI_TRUSTED_HOSTS=app.example.com,localhost,127.0.0.1,backend
MARKET_AI_ALLOWED_ORIGINS=https://app.example.com

MARKET_AI_ENABLE_SCHEDULER=1
MARKET_AI_SCHEDULER_RUNNER_ROLE=automation
MARKET_AI_SERVER_ROLE_API=api
MARKET_AI_SERVER_ROLE_AUTOMATION=automation

MARKET_AI_BROKER_PROVIDER=alpaca
MARKET_AI_ALPACA_ENABLED=1
ALPACA_PAPER=1
MARKET_AI_BROKER_ORDER_SUBMISSION_ENABLED=1
MARKET_AI_BROKER_LIVE_EXECUTION_ENABLED=0
MARKET_AI_AUTO_TRADING_ENABLED=1
MARKET_AI_AUTO_TRADING_CYCLE_MINUTES=5
MARKET_AI_PAPER_TRADING_24_7=1
MARKET_AI_CONTINUOUS_PAPER_TRADING=1

MARKET_AI_AUTH_ENABLED=1
MARKET_AI_AUTH_DEFAULT_USERNAME=admin
MARKET_AI_AUTH_DEFAULT_PASSWORD=change-this-now
MARKET_AI_AUTH_SECRET_KEY=generate-a-long-random-secret
```

إذا كنت ستعتمد على إعدادات المفاتيح من داخل واجهة المنصة، اترك مفاتيح Alpaca فارغة في الملف وأدخلها من صفحة الإعدادات بعد الإقلاع.

## 4. تشغيل المنصة

```bash
mkdir -p data model_artifacts
chmod +x scripts/deploy_linux.sh scripts/check_stack.sh
./scripts/deploy_linux.sh .env.production
```

## 5. فحص الخدمات

```bash
docker compose --env-file .env.production ps
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/api/automation/status
curl -I http://127.0.0.1:4173/
```

تحقق خصوصًا من:

- `backend` بحالة `healthy`
- `automation` يعمل
- `frontend` بحالة `healthy`
- `auto_trading_cycle` موجود في `/api/automation/status`

## 6. ربط Nginx مع الدومين

انسخ الملف [deploy/nginx/market-ai.conf.example](/C:/Users/fas51/Desktop/market-ai-dashboard-backup/deploy/nginx/market-ai.conf.example) إلى السيرفر ثم عدّل `server_name`.

```bash
sudo cp deploy/nginx/market-ai.conf.example /etc/nginx/sites-available/market-ai
sudo nano /etc/nginx/sites-available/market-ai
sudo ln -s /etc/nginx/sites-available/market-ai /etc/nginx/sites-enabled/market-ai
sudo nginx -t
sudo systemctl reload nginx
```

## 7. تفعيل SSL

بعد أن يصبح الدومين يشير إلى السيرفر:

```bash
sudo certbot --nginx -d app.example.com
```

## 8. أوامر التشغيل اليومية

تحديث بعد `git pull`:

```bash
cd /opt/market-ai-dashboard
git pull
./scripts/deploy_linux.sh .env.production
```

قراءة السجلات:

```bash
docker compose --env-file .env.production logs --tail=150 backend
docker compose --env-file .env.production logs --tail=150 automation
docker compose --env-file .env.production logs --tail=150 frontend
```

إعادة تشغيل الخدمات:

```bash
docker compose --env-file .env.production restart backend automation frontend
```

## 9. ملاحظات مهمة للتداول

- الوضع الآمن الموصى به أولًا هو `paper trading`.
- اترك `MARKET_AI_BROKER_LIVE_EXECUTION_ENABLED=0` حتى تتأكد من السلوك كاملًا على السيرفر.
- التعديلات الحالية تمنع الشورت والمارجن وتسمح فقط بالتداول على الكاش والأسهم المملوكة.
- إذا أردت لاحقًا التنفيذ الحقيقي، فعّل ذلك فقط بعد مراجعة صفحة الوسيط والسجلات وأول عدة دورات تداول.

## 10. قرار التشغيل المقترح

أفضل توزيع لك هو:

- السيرفر: تشغيل حي مستمر
- جهازك: تطوير واختبار

لا أنصح بتشغيل نماذج ثقيلة جدًا أو inference محلي كبير على هذا السيرفر بدل جهازك الحالي.
