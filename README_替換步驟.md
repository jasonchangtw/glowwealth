# GlowWealth 現價修復套件

這是可直接替換的完整程式，不是簡化示範版。基於 GitHub `main` 的 `f6918b01abee4bdf679829dea7154c4259ad8a53` 製作；原本 Google Drive、GitHub Gist、JSON 匯入／匯出、記帳、配息與帳務計算程式保留。

採用免費公開行情，不需要申請行情 API key。台股用證交所 MIS，官方上市／上櫃收盤價作備援；美股用 Yahoo chart。GitHub Actions 每 30 分鐘收集一次，將行情與網頁一起發布到原本的 GitHub Pages。頁面每 5 分鐘讀取已發布行情，也可按原本的「刷新現價」。它不是每秒即時看盤服務。

## GitHub 要放入的五個檔案

請保留以下路徑；不要把整個解壓縮資料夾當成 repository 的下一層資料夾。

```text
glowwealth/
├── index.html                         ← 替換現有完整網頁
├── quotes.json                        ← 初始公開行情，首次部署即可讀取
├── quote-symbols.json                 ← 要查盤中行情的公開代號清單
├── scripts/
│   └── update_quotes.py               ← 免費行情抓取程式
└── .github/
    └── workflows/
        └── update-quotes.yml          ← 定時收集與發布
```

README、驗證紀錄、patch、tests 不必上傳才能運作。`quotes.json` 只有公開行情，沒有你的交易、股數、資產或登入資訊。

## 用 GitHub 網頁替換

1. 先在原 dashboard「同步」頁匯出 JSON，保留一份自己的交易備份；這份備份不要上傳公開 repository。
2. 在 `jasonchangtw/glowwealth` 的 `main`，以套件內的完整 `index.html` 替換原檔。
3. 新增根目錄 `quotes.json`、`quote-symbols.json`，以及 `scripts/update_quotes.py`。
4. 點 **Add file → Create new file**，檔名完整輸入 **`.github/workflows/update-quotes.yml`**，貼上套件內該檔完整內容。macOS 的 `.github` 是隱藏資料夾，可用 ⌘⇧. 顯示；也可直接依此路徑在 GitHub 建立。
5. 到 repository **Settings → Pages → Build and deployment → Source**，選 **GitHub Actions**。這是必要的一次設定；只替換 HTML 不會啟用定時抓價。
6. 到 **Actions → Update public quotes and deploy dashboard → Run workflow**，選 `main`，執行第一次更新。確認 `build`、`deploy` 都是綠色，再打開原網址：`https://jasonchangtw.github.io/glowwealth/`。

不用新增行情帳號，不用新增個人 Token，不用修改 Google Client ID／Gist ID。workflow 使用 GitHub 自動提供的部署權限，沒有讀寫家庭 Gist 或 Google Drive 的權限；也不會把行情自動 commit 回主分支。

只要繼續使用原網址、原瀏覽器，既有本機交易資料與同步設定仍使用原來的儲存 key。不要建立新 repository 或改網址來替換這個版本。

## 如何判斷現價正常

- 「行情已讀」：目前持股都取得有效、近期收集的行情。這不表示每檔都是當刻盤中成交。
- 「部分備援」：至少一檔只有舊行情或交易價備援；移到現價欄位可查看原因與日期。
- 「讀取失敗」：網頁未成功取得行情檔；保留上次行情，有交易但從未取得行情者沿用交易價估算。
- 「範例」：沒有目前持股，仍顯示原本的固定範例，不代表範例數字會隨行情改變。
- 現價小標籤「成交」／「收盤」／「舊價」／「備援」區分來源。滑鼠停在現價上可查看行情時間、抓取時間與來源；表格、卡片與同步頁的樣式及欄位保持原樣。

「舊價」包括來源更新失敗、抓取時間超過 90 分鐘，或行情時間超過四天。這是保守提示，長假也可能被標成舊價。GitHub 排程可能延遲，所以按刷新不會強制上游產生新行情。

## 新增標的

既有美股清單為 QQQ、VOO、VT、TSLA、NVDA。若新增 AAPL 等美股，在 `quote-symbols.json` 的 `us` 陣列加入代號，commit 後 workflow 會更新。使用 Yahoo 的代號形式；例如特殊股票的代號需要先核對，不是所有市場代號都可直接照抄。這份清單只有公開代號，請勿放持股數或交易內容。

台股收盤行情檔涵蓋官方回傳的有效代號；新台股可先取得收盤資料。若也要優先查最新成交價，在 `tw` 陣列加入代號。台股清單目前為原程式內的 25 檔。原程式的市場判定邏輯保留，因此特殊尾碼或特殊代號仍需另行驗證；本次已驗證的字母尾碼是 A。

新增標的不需要改表格、不需要改同步 payload，也不會自動公開你的個人交易清單。

## 頻率、費用與服務邊界

預設 UTC 每小時第 17、47 分鐘執行，約每 30 分鐘一次；實際啟動時間由 GitHub 排程決定。公開 repository 使用標準 GitHub-hosted runner 的執行時間免費；本套件不使用 larger runner、付費行情或額外行情帳號。Pages artifact 使用 GitHub 的標準發布流程與預設保留政策，仍受帳戶及服務配額限制。

免費公開端點可能限流、改格式或停止提供。抓價程式會驗證狀態、價格、代號、幣別與日期；對來源失敗保留最近一次發布的有效價格，不把錯誤回應當成行情。若全部來源失效且沒有任何備援行情，拒絕發布空檔。

公開 repository 排程若長期無活動，可能被 GitHub 自動停用；看到舊價時先到 Actions 檢查，必要時 Enable workflow 或手動 Run workflow。

## 若第一次執行失敗

- `Configure Pages` 失敗：確認 Settings → Pages 的 Source 已選 GitHub Actions，且 workflow 執行分支為 `main`。
- 部署被環境規則擋住：到 Settings → Environments → github-pages，確認原本的部署規則允許 `main`；不要擅自放寬其他安全規則。
- 個別來源回 429／逾時：查看行情時間。下次排程會再嘗試；已有價格會保留並標記，避免密集連續執行。
- 同時有其他 Pages 部署 workflow：本套件是原單檔 repository 的完整發布流程。需避免兩套 workflow 交替發布不同版本。

本次尚未替你上傳或執行 GitHub workflow，所以第一次雲端部署是最後的驗收步驟。

## 回復原版

在 Actions 停用 `Update public quotes and deploy dashboard`；從 GitHub 歷史版本恢復原 `index.html`；Settings → Pages 恢復原本的發布來源。不要清除瀏覽器資料或改動交易／配息 key。

## 本機測試（可選）

```sh
python3 -m unittest discover -s tests -v
node tests/quotes_frontend.cjs
node tests/sync_contract.cjs
python3 scripts/update_quotes.py
python3 -m http.server 8000
```

在本機網址測試不會讀到原 GitHub Pages 的本機交易；兩者是不同網站來源。

## 官方參考

- [證交所 OpenAPI](https://openapi.twse.com.tw/)
- [GitHub Pages 自訂部署流程](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [GitHub Actions 免費使用規則](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [排程限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [停用及啟用 workflow](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)
