# 會計事務所內部管理系統

第一版採用 Bolder 深海藍與琥珀色工作台。React 前端由 Nginx 提供，FastAPI 與 PostgreSQL 管理帳號、工作、出勤、審核及報表。

## 本機啟動

1. 複製 `.env.example` 為 `.env`，填入自己的 `POSTGRES_PASSWORD` 和 `BOOTSTRAP_OWNER_PASSWORD`。資料庫密碼請使用 URL 安全字元，老闆密碼至少 12 字元。
2. 執行 `docker compose --profile demo up --build`。
3. 開啟 [工作台](http://localhost:8080)，使用 `.env` 的老闆帳號登入。老闆在空資料庫啟動時建立。
4. 建立員工後，在 [Mailpit](http://localhost:8025) 查看邀請信並開啟啟用連結。Mailpit 僅供本機開發，所有郵件保留在測試信箱。

本機配置預設只綁定 loopback。資料庫資料使用 Compose volume。以 `docker compose --profile demo down` 停止服務。

若目前終端機尚未載入已加入的 `docker` 群組，可執行 `sg docker -c 'docker compose --profile demo up --build --detach --wait'`。工作台亦可從 [127.0.0.1](http://127.0.0.1:8080) 開啟。

本機建立的四個單一角色測試帳號及密碼存於 `.demo-accounts`，該檔案排除於 Git。測試員工的直屬主管為測試主管。

## 設定與資料邊界

- `ADMIN_REVIEW_ROUTING=shared` 開啟行政共用待審佇列，作為本機驗證選項。正式使用前需確認分派方式。
- `REPORT_FINALIZER_ROLE=admin` 可保存具版本的報表草稿，用於測試月結流程。工時 Excel 為初步計算，正式的班別、假勤、外出與加班規則及報表格式仍須確認。
- `TASK_CANCEL_POLICY` 和 `TASK_REOPEN_POLICY` 各可設為 `owner`、`creator` 或 `assignee`。權限定案並明確設定後，系統才開啟對應操作。
- 主管的管理資料範圍使用直屬關係。具期間的代理和老闆指派可依審核流程處理。間接下屬範圍待事務所確認。
- 正式部署須設定實際的網站網址與 TLS、`COOKIE_SECURE=true`、郵件服務及備份方式，並確認資料留存政策、匯入需求與各項角色資料範圍。
- 月曆隨附 2026、2027 年具名稱的節日參考日期，資料來自行政院人事行政總處，採政府資料開放授權條款第 1 版。公司工時依行政設定的班表及調班計算。 [政府資料開放平臺](https://data.gov.tw/dataset/14718)

詳見 [產品需求](docs/requirements.md) 與 [架構設計](docs/superpowers/specs/2026-11-25-accounting-office-design.md)。

## 開發驗證

- 前端在 `frontend` 執行 `npm ci`、`npm test` 與 `npm run build`。
- 後端安裝 `backend/requirements-dev.txt` 後，在專案根目錄執行 `PYTHONPATH=backend python -m unittest discover -s backend/tests -v`。
- API 整合測試需要全新的暫存 PostgreSQL 資料庫。設定 `DATABASE_URL`、`ACCOUNTING_INTEGRATION_TEST=1`、`BOOTSTRAP_OWNER_EMAIL=owner@example.test`、`BOOTSTRAP_OWNER_PASSWORD=Integration-check-only`、`ADMIN_REVIEW_ROUTING=shared` 與 `REPORT_FINALIZER_ROLE=admin` 後執行同一條後端測試指令。
