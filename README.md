---
title: 地盤 AI 安全監測及自動記錄系統
emoji: 🏗️
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# 地盤 AI 安全監測及自動記錄系統

AI Site Safety Monitoring and Automated Record System — CITF 申請所述方案的可運行原型。

前線師傅照常以即時通訊群組傳送工地相片，系統自動接收及歸檔，由 AI 初步篩查
安全帽（PPE）合規及吸煙違規，再交由管工或安全主任人手覆核，收工後自動生成每日
Word 報告。系統只作輔助，不取代法定人手安全巡查。

## 快速開始

```powershell
pip install -r requirements.txt
python seed_demo.py        # 生成示範相片（可略過，改用自己的相片）
python run.py              # 啟動後開啟 http://127.0.0.1:8000/
```

在概覽頁按「掃描收件匣」即完成接入與偵測，再到「覆核」確認結果，最後在概覽頁
每個地盤一行生成 .docx。

## 兩個界面

| 頁面 | 用途 |
|------|------|
| 概覽 | 各地盤當日相片數、AI 標示、覆核進度，以及日報預覽、生成及下載 |
| 覆核 | 逐項確認或推翻 AI 標示，可加備註 |

## 日報：線上預覽與 Word 檔

日報有兩種形式，內容由同一份資料組成（`app/report.py` 的 `collect_report_data`）：

- **線上預覽**：`/api/reports/preview?site_id=1&date=2026-09-03`，即時反映最新覆核結果，
  毋須先生成檔案。頁內可直接列印或另存 PDF（已設 A4 列印樣式，會自動隱藏工具列）。
- **Word 檔**：按「生成日報」後產生 `.docx`，存於 `data/reports/<地盤代號>/`。

概覽頁每個地盤一行都有「預覽」連結，以及「生成」或「下載」。

## 相片接入

兩個入口，共用同一條歸檔流程：

- **網頁上載**（主要入口）：概覽頁選定地盤後直接上載，可一次多張。
- **收件匣**（批次匯入）：把相片放入 `data/inbox/<地盤代號>/`，按「掃描收件匣」。
  處理後的原檔移入 `data/inbox/_processed/`，不會重覆掃描。

即時通訊群組自動收相尚未實作，目前一律由上述兩個入口人手提交。

相片按 `data/photos/<地盤代號>/<日期>/` 歸檔，工作日期取自 EXIF 拍攝時間，缺少時
退回檔案修改時間。

## 偵測器：由 mock 換成真實模型

預設使用 **mock 偵測器**：不讀取影像內容，以檔案 SHA-256 為亂數種子產生結果，因此
同一張相片結果恆定。它只用於搭建流程與演示界面，**準確度數字不具意義**，界面右上角
會以橙色標示 `模擬偵測器 mock`。

切換至真實視覺語言模型（VLM）：

```powershell
$env:CITF_DETECTOR = "vlm"
$env:OPENAI_API_KEY = "sk-..."
$env:OPENAI_BASE_URL = "https://api.openai.com/v1"   # 可改為自建或代理端點
$env:CITF_VLM_MODEL = "gpt-4o-mini"
python run.py
```

兩者共用 `app/detect/base.py` 的 `Detector` 介面，接入、覆核、報告、儀表板均不需改動。

新增違規類別（例如未繫安全帶、未設圍欄）只需在 `app/models.py` 登記類別，再於
`app/detect/vlm.py` 的 `CATEGORY_PROMPTS` 加一條文字描述即可起步，毋須重新訓練。

## 環境變數

| 變數 | 預設 | 說明 |
|------|------|------|
| `CITF_DETECTOR` | `mock` | `mock` 或 `vlm` |
| `CITF_AUTO_DETECT` | `1` | 接入相片後是否立即偵測 |
| `CITF_CONFIDENCE_THRESHOLD` | `0.35` | 低於此信心值不寫入資料庫 |
| `CITF_DATA_DIR` | `./data` | 資料目錄 |
| `CITF_DEMO_SEED` | `0` | 設為 `1` 時，資料庫為空會自動生成並接入示範相片 |
| `PORT` | `8000` | 伺服器連接埠 |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `CITF_VLM_MODEL` | — | VLM 設定 |

## 目錄結構

```
app/
  config.py        設定（全部可由環境變數覆寫）
  db.py            SQLite 連線與初始化
  schema.sql       資料庫結構
  models.py        偵測類別與共用資料結構
  ingest.py        接入、歸檔、觸發偵測
  detect/
    base.py        Detector 介面與工廠
    mock.py        模擬偵測器
    vlm.py         視覺語言模型偵測器
  review.py        覆核佇列與提交
  stats.py         概覽與報告共用統計
  report.py        每日 Word 報告生成
  main.py          FastAPI 路由
web/               概覽、覆核兩個頁面（原生 HTML/JS，無需建置）
data/              相片、資料庫、報告（不納入版本控制）
seed_demo.py       生成示範相片
run.py             啟動伺服器
Dockerfile         容器化部署（Hugging Face Spaces 等）
```

## 主要 API

| 方法 | 路徑 | 用途 |
|------|------|------|
| GET | `/api/health` | 狀態與目前偵測器 |
| GET | `/api/dashboard?date=` | 各地盤當日統計 |
| POST | `/api/ingest/scan` | 掃描收件匣並偵測 |
| POST | `/api/ingest/upload` | 上載相片（multipart） |
| GET | `/api/review/queue` | 覆核佇列 |
| POST | `/api/review/{detection_id}` | 提交覆核（重覆提交會覆寫） |
| GET | `/api/reports/preview?site_id=&date=` | 日報線上預覽（HTML，即時） |
| POST | `/api/reports/generate` | 生成單一地盤日報 |
| GET | `/api/reports/{id}/preview` | 已生成報告的線上預覽 |
| GET | `/api/reports/{id}/download` | 下載 .docx |

完整互動式文件：啟動後開啟 <http://127.0.0.1:8000/docs>。

## 線上演示部署

倉庫已附 `Dockerfile`，可直接部署至 Hugging Face Spaces（Docker SDK，連接埠 7860）：

```bash
git remote add space https://huggingface.co/spaces/<帳號>/<space-名稱>
git push space main
```

容器已設 `CITF_DEMO_SEED=1`，每次啟動若資料庫為空會自動生成三個地盤、兩天的示範
相片並跑完偵測，因此不需上傳任何資料即可演示。演示環境的儲存空間是暫存的，重啟
後資料會重新生成。

## 與 CITF 申請文件的對應

`CITF_申請填寫總表_定稿.md` 所列交付成果與本原型的對應關係：

| 申請書交付成果 | 本原型 |
|----------------|--------|
| 微調視覺語言偵測模型（VLM） | `app/detect/vlm.py`（介面已備妥，尚未微調） |
| GPU 邊緣推論管線 | 目前為單機同步推論，未接 GPU 批次 |
| 多地盤概覽 | `web/index.html` |
| LLM 報告生成器 | `app/report.py`（線上預覽 + Word，目前為結構化模板，未接 LLM 潤飾） |
| 手機預警 | 未實作 |
| 即時通訊群組收相 | 未實作，改以網頁上載及收件匣資料夾提交 |

原型未涵蓋的部分即申請書中屬於外判開發範圍的項目。

## 已知限制

- mock 偵測器不看影像內容，示範相片中戴了安全帽的工人仍可能被標示為違規。
- 相片一律由人手上載或放入收件匣；申請文稿已標註 WhatsApp Business API 不支援讀取
  群組訊息，自動收相的實際接入方式須另行核實後再實作。
- 尚無使用者登入與權限控制，覆核人姓名為自行填寫，僅適用於內部演示。
- 相片以明文儲存於本機，未做加密；正式部署須按個人資料私隱條例加密及限權查閱。
