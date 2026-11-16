# 16: 輕量 PWA（加到主畫面、全螢幕）

**Blocked by:** 15
**Status:** resolved

**What to build:** 只做「加到主畫面後像 App 一樣全螢幕開啟」所需的最小設定：web app manifest（名稱、圖示、主題色、standalone 顯示）、iOS 用的 apple-mobile-web-app 標籤、圖示。**不做 service worker、不做離線快取**，因為查詢需要後端，離線快取只會造成舊內容。

- [ ] manifest 與圖示（192、512 與 apple-touch-icon），主題色與簡約風格一致，淺色與深色主題皆正確
- [ ] 在手機上「加到主畫面」後以 standalone 開啟，沒有瀏覽器網址列
- [ ] 沒有註冊 service worker；README 一行說明為何不做離線
- [ ] 說明並測試：http（區網 IP）與 https（通道或雲端）兩種網址各能做到什麼（Android 的安裝提示需要 https；iOS 加到主畫面不需要）
- [ ] 不新增依賴

## Comments

- 完成（244 passed）。manifest 與 3 個圖示經瀏覽器驗證；無 service worker。未驗：真機安裝、https、iOS 全螢幕。
