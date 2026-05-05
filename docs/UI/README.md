# NSMakeFriend Desktop UI

A soft pastel desktop GUI for the NSMakeFriend Switch Drawing Tool, built with [Flet](https://flet.dev).

![UI Screenshot](UI_design.md)

---

## Requirements

| Dependency | Version |
|---|---|
| Python | 3.10 + |
| flet | 0.84.0 + |
| Pillow | any recent |

---

## 安裝依賴 / Install

在 project 根目錄執行：

```bash
pip install flet pillow
```

或者用 `requirements.txt`（如果有）：

```bash
pip install -r requirements.txt
```

---

## 啟動 UI / Launch

**必須從 project 根目錄執行（即 `nsmakefriend/` 那層）**，否則 relative import 會出錯。

```bash
# 確保你在 project 根目錄
cd /workspaces/nsmakefriend

# 啟動 GUI
python -m host.ui_flet
```

視窗會在幾秒內開啟。

---

## UI 結構 / Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  NSMakeFriend  ·  Switch Drawing Tool           Help   Settings     │
├──────────┬───────────────┬──────────────────────┬───────────────────┤
│ 1 IMAGE  │ 2 PARAMETERS  │  3 PREVIEW            │  4 ANALYSIS       │
│          │               │                       │  5 DEVICE         │
│          │               │                       │  6 ACTIONS        │
├──────────┴───────────────┴──────────────────────┴───────────────────┤
│  LOG                                                          Clear  │
├─────────────────────────────────────────────────────────────────────┤
│  NS Controller: Connected                  Firmware · App Version   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 使用流程 / Workflow

```
① Select Image
      ↓
② Adjust Parameters（Mode / Canvas Size / Brush Size / Threshold…）
      ↓
③ Generate Preview（確認效果）
      ↓
④ Dry Run（取得 Command Count 和預計時間）
      ↓
⑤ Check Connection（確認 Switch 已連接）
      ↓
⑥ Start Drawing
```

> **原則：先看 preview，再畫。** 不建議直接 Start Drawing 而不先 Generate Preview。

---

## 各面板說明 / Panel Reference

### 1 · Image

| 元件 | 說明 |
|---|---|
| Select Image | 開啟檔案選擇器，支援 PNG / JPG / JPEG / WEBP |
| 縮圖 | 選圖後自動顯示原圖縮圖 |
| Image Info card | 顯示 Format / 尺寸 / File Size |
| Drag & Drop zone | 點擊亦可開啟檔案選擇器 |

### 2 · Parameters

| 參數 | 對應 CLI | 說明 |
|---|---|---|
| Mode | `--color` | Black & White 或 Color |
| Width / Height | `--width` / `--height` | Canvas 像素大小，用 +/− 調整 |
| Brush Size | `--brush-size` | 1–4，影響最終像素密度 |
| Threshold | `--threshold` | B&W 模式灰階閾值（0–255） |
| Contrast | `--contrast` | 對比度增強（0.5–3.0） |
| Invert | `--invert` | 反轉黑白 |
| Max Colors | `--max-colors` | Color 模式最多用幾種顏色（1–84） |
| BG Threshold | `--bg-threshold` | Color 模式背景色截止值（0–255） |

**Load Preset** 快速套用預設：

| Preset | 特點 |
|---|---|
| Default | 標準設定 |
| Line Art | 高 threshold，輕微增強對比 |
| Photo B&W | 適合相片轉黑白 |
| Pixel Art | Brush Size 2，像素風 |
| Soft Color | 42 色柔和彩色 |
| Full Color | 84 色全彩 |

### 3 · Preview

- **Generate Preview**：呼叫 `host/draw.py` pipeline 生成處理後的圖片
- **Processed Preview** tab：顯示實際會畫出的 bitmap
- **Palette Preview** tab：顯示 Color 模式的調色盤分佈（B&W 模式同樣是 processed view）
- Preview 生成期間會顯示 loading ring，UI 不會卡住

### 4 · Analysis

| 欄位 | 說明 |
|---|---|
| Pixels to Draw | 需要畫的像素數 |
| Command Count | 執行 Dry Run 後得到的指令總數 |
| Estimated Time | 根據 command count 估算繪圖時間 |
| Black Pixels | B&W 模式的黑色像素數及佔比 |
| Color Count | Color 模式使用的顏色數 |
| Palette Usage | Color 模式調色盤摘要 |

Status card 會顯示目前狀態（No Image / Preview Ready / Ready to Draw! / Drawing…）。

### 5 · Device

| 元件 | 說明 |
|---|---|
| Serial Port | 選擇 ESP32 的串口（自動偵測 `/dev/ttyUSB*`, `/dev/ttyACM*`）|
| ↻ 按鈕 | 重新掃描可用串口 |
| Baud Rate | 預設 115200 |
| Check Connection | 檢查 Nintendo Switch 是否已連接 |

### 6 · Actions

| 按鈕 | 說明 |
|---|---|
| Dry Run | 計算指令數但不送出，更新 Analysis 面板 |
| Start Drawing | 正式開始繪圖（需先 Generate Preview） |
| Stop | 中斷繪圖 |

---

## Log 面板

- 顯示帶時間戳的操作紀錄
- 顏色區分：白色 = 一般，綠色 = 成功，紅色 = 錯誤
- 同時捕捉 `host.draw` / `host.image_processor` 等 module 的 logging 輸出
- **Clear** 按鈕清空 log

---

## 輸出檔案 / Output Files

UI 執行時會在 project 根目錄自動建立 `output/` 資料夾：

```
output/
  preview.png          # Generate Preview 產生的處理後圖片
  palette_preview.png  # Color 模式的調色盤預覽
```

---

## 常見問題 / FAQ

**Q: 視窗打不開 / 沒有任何反應**
```bash
# 確認 flet 已安裝
python -m flet --version
```

**Q: `ModuleNotFoundError: No module named 'host'`**

確認你是在 project 根目錄（`nsmakefriend/`）執行，不是在 `host/` 子目錄。

```bash
cd /workspaces/nsmakefriend
python -m host.ui_flet   # ✓ 正確
```

**Q: Serial port 選不到**

點擊 Serial Port 旁的 `↻` 重新掃描，或手動確認 ESP32 已插上：
```bash
ls /dev/ttyUSB* /dev/ttyACM*
```

**Q: 在 Linux 上需要 serial port 權限**
```bash
sudo usermod -aG dialout $USER
# 重新登入後生效
```

**Q: Generate Preview 很慢**

Preview 會執行完整的 image processing pipeline（resize、threshold、path planning），對大圖或高解析度 canvas 會需要數秒，屬正常。

---

## 技術細節 / Tech Notes

- GUI 框架：[Flet](https://flet.dev) 0.84+（Flutter-based Python desktop UI）
- 所有繪圖邏輯都來自 `host/draw.py`，UI 不重複實作 image processing
- Generate Preview / Dry Run / Start Drawing 全部在 background thread 執行，UI 不卡頓
- 從 `host.draw`、`host.image_processor` 等 module 的 Python logging 輸出會自動顯示在 Log 面板
