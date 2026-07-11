# 學校端 Worker 啟動流程

給各合作學校 SCHOOL_ADMIN 使用。本文件假設中央控制端 (central plane)
已經由 HCIS-Lab 佈署完成，你這邊只需要把一台或多台 GPU 主機接進來。

**架構概念一句話：**
中央負責收學生上傳、排隊、記錄結果；你們的 worker 只負責跑 Isaac Sim
和把結果回報。中央永遠不會主動打你們的 API——是 worker 自己每隔
10 秒去中央 long-poll 拉工作 (`POST /api/workers/next-job`)。所以
你們**不需要在學校端多裝任何 backend / dispatcher / 排班程式**。

---

## 0. 事前準備 (host 端一次性)

| 需求 | 說明 |
|------|------|
| OS | Ubuntu 20.04 / 22.04 (其他發行版理論上也行，尚未測試) |
| CPU/RAM | 4 core / 8 GB 以上 |
| GPU | 每個 worker 一張卡；mock 模式不需要 GPU |
| NVIDIA Driver | 535+ (Isaac Sim 需求) |
| Docker Engine | 20.10+ |
| Docker Compose plugin | v2 (`docker compose version` 看得到即可) |
| nvidia-container-toolkit | 只有 `EVAL_MODE=real` 才需要 |
| 對外可達 URL | 給學生瀏覽器 upload 用；HTTPS 反向代理到 worker 的 host port |
| 對外埠 | 預設 8081 起跳，一個 worker 佔一個 port |
| 磁碟 | 每個 worker 至少 30 GB — Isaac Sim 的 Omniverse 資產 cache (`/root/.cache/ov`) 會長到 10-20 GB，加上學生 zip + 錄影 |

檢查腳本會在 `./setup.sh` 開頭跑一次，缺什麼會直接告訴你。

**Isaac Sim 資產 cache**：worker container 掛了一個 docker volume
`worker_ov_cache` 到 `/root/.cache/ov`。第一次跑 real 模式時 Isaac Sim
會從 S3 拉多 GB 的 USD 資產，之後這些資產都會存在這個 volume 裡；container 重啟不會清掉。**只有** `docker compose down -v` 才會把它一起清掉，之後下次 real 評估又要從頭下載一次（在較慢的網路上可能會失敗）。所以請不要沒事就 `-v`。

---

## 1. 跟中央要 join token

1. 用 `SCHOOL_ADMIN` 帳號登入 central：
   `https://leaderboard.hcislab.tw/admin/dashboard`
2. 切到 **Workers** tab (若沒看到，代表你不是 SCHOOL_ADMIN — 聯絡我們)
3. 點右上角 **+ Issue Join Token**
4. 填欄位：

   | 欄位 | 建議值 |
   |------|--------|
   | **TTL (minutes)** | 30 (夠你打完所有 setup.sh) |
   | **Max uses** | 該台主機打算跑幾個 worker (= GPU 數) |
   | **Note** | 隨便寫，會出現在 audit log |

5. 送出後**只會顯示一次**，馬上複製起來。裡面同時會顯示：
   - `Uses left: N / N` — 這個 token 可以再 redeem 幾次
   - `Expires at: ...` — 過期後不能再 redeem，但已經註冊的 worker 不受影響
     (worker 註冊完會拿到一個獨立的 machine JWT，跟這個 token 就沒關係了)

> **一個 token 對應一台主機。** 想在兩台主機各跑 worker，請發兩個 token。
> 想在同一台跑 3 個 worker (三張 GPU)，就發一個 `max_uses=3` 的 token。

---

## 2. Clone worker repo 並執行 setup

```bash
git clone https://github.com/HCIS-Lab/aicapstone-worker.git worker-gpu0
cd worker-gpu0
./setup.sh
```

`setup.sh` 會互動式問四件事：
- **Central plane URL** — 直接 Enter 用預設 `https://leaderboard.hcislab.tw`
- **Worker name** — 顯示在 Observability tab 的名字，例如 `nthu-gpu0`
- **Join token** — 貼上剛剛拿到的
- **Worker public URL** — 學生瀏覽器要能打到的 URL (例：`https://gpu-01.your-school.edu.tw`)
- **Eval mode** — 剛開始請填 `mock` 跑通後再改 `real`

自動偵測項：
- **GPU_ID** — 掃 `nvidia-smi` + 其他 worker container 已佔用的卡，挑第一張沒人用的
- **Host port** — 從 8081 往上找第一個沒被綁的
- **Container name** — 自動變成 `worker-agent-<port>`，多個 worker 不會撞名

不想手動打，可以一次到位：

```bash
./setup.sh --yes \
  --token=<JOIN_TOKEN> \
  --public-url=https://gpu-01.your-school.edu.tw \
  --name=gpu-01 \
  --mode=mock
```

腳本跑完會等 `/health` 200，接著 tail log 直到看見
`registered as worker <id>` 才算完成。回到 central 的 **Observability**
tab 應該可以在 30 秒內看到這個 worker 顯示為 `ONLINE`。

---

## 3. 一台主機跑多個 worker

假設主機上有兩張 GPU，你在第 1 步 issue 了 `max_uses=2` 的 token：

```bash
# 第一個 worker
git clone https://github.com/HCIS-Lab/aicapstone-worker.git worker-gpu0
cd worker-gpu0 && ./setup.sh          # 自動挑 GPU 0、port 8081
cd ..

# 第二個 worker (同一台主機、同一個 token)
git clone https://github.com/HCIS-Lab/aicapstone-worker.git worker-gpu1
cd worker-gpu1 && ./setup.sh          # 自動挑 GPU 1、port 8082
```

兩份 clone 用同一個 join token 註冊。**每個 worker 各自的 `.env` 和 state
volume 都是獨立的**，所以刪掉其中一個不會影響另一個。

第三次執行 setup.sh 用同一個 token 會被中央拒絕 (`409 join token
already exhausted`) — token 只能被 redeem `max_uses` 次。

---

## 4. 日常操作

在任何一個 worker clone 的目錄裡：

```bash
./setup.sh --status              # 一鍵看狀態 (docker ps + 最近 log + /health)
docker compose logs -f           # 即時 log
docker compose restart           # 重啟 (改設定後用)
docker compose down              # 停掉 (不會刪 volume)
docker compose down -v           # 停掉 + 刪 storage/state/Isaac Sim cache
                                 # 三個 volume — 下次 real 評估要重下多 GB 資產
./setup.sh --reset --yes         # = 上面 + 重跑 setup 從零註冊
```

三個 docker volume：
| Volume | 用途 | 清了之後會怎樣 |
|---|---|---|
| `worker_storage` | 學生 zip、staged workdir、錄影 | 進行中的 eval 檔案沒了；已回報的分數不影響 (中央存 DB) |
| `worker_state` | machine JWT、worker id | 得重跑 `setup.sh --reset` 用新 join token 重新註冊 |
| `worker_ov_cache` | Isaac Sim 從 S3 抓下來的 USD 資產 | 下次跑 real 模式要花時間 (甚至 30+ min) 重下 |

**改設定的正確流程**：
1. 直接改 clone 目錄下的 `.env`
2. `docker compose restart`

不要手動改 container 內的檔案，重啟就沒了。

---

## 5. Central 端 Observability

登入 SCHOOL_ADMIN → **Observability** tab，看到的就只有你們學校的資料 (SUPERUSER 才看得到跨校)：

- **Workers** 卡片：每台 worker 的狀態、GPU 編號、心跳延遲、正在跑什麼
- **Queued**：學生上傳但還沒 worker 拿去跑的 submissions
- **Running now**：正在跑的 submissions + 是哪個 worker 在跑
- **Recent outcomes (24h)**：成功/失敗清單，失敗會顯示 error message

如果 worker 卡在 OFFLINE：
- 檢查 `docker compose logs -f` 有沒有連不到 central 的錯誤
- 檢查 host 到 `CENTRAL_API_URL` 的網路
- 檢查 machine JWT 有沒有被 revoke (SCHOOL_ADMIN 或 SUPERUSER 可以在
  Workers tab 手動把 worker 設成 REVOKED，之後只能重跑 `./setup.sh --reset`
  用新 token 重新註冊)

---

## 6. 學生瀏覽器 → worker 的網路

中央會發 presigned URL 給學生瀏覽器，形式是
`{WORKER_PUBLIC_URL}/upload/{token}`。所以 `WORKER_PUBLIC_URL` **必須**
是學生電腦打得到的位置：

- 通常用學校的反向代理 (nginx / Caddy) 把
  `https://gpu-01.your-school.edu.tw` 轉到 host 上的 `WORKER_HOST_PORT`
- 或直接對外開 host 的 port (不建議，缺 HTTPS)

`setup.sh` 會自動把 `WORKER_PUBLIC_URL` 的 port 對齊到實際被挑到的
host port，所以你只要提供 hostname 就好。

---

## 7. 資料流 (學生上傳 → 你們的 worker 拿到 zip)

```
學生瀏覽器 ────► central: POST /api/submissions  (拿到 presigned URL)
      │
      ▼ (跟中央拿到的 URL)
你們的 worker: POST /upload/{token}   ← 學生 zip 直接進來，不經過中央
      │
      ▼
中央: notify submission ready
      │
      ▼ (worker long-poll 拉)
你們的 worker: POST /api/workers/next-job → 拿到工作 → 跑 Isaac Sim → 回報結果
      │
      ▼
中央更新 leaderboard，顯示於各學校的 Observability
```

**重點：** 學生的 zip bytes 不會通過中央，隱私跟頻寬都由學校自己負責。

---

## 8. Troubleshooting

| 症狀 | 可能原因 | 處理 |
|------|----------|------|
| `join token expired` (410) | 超過 TTL | 回 central 再 issue 一個 |
| `join token already exhausted` (409) | Redeem 次數用完 | 再 issue 一個 (或 issue 一個 max_uses 更大的) |
| `unknown or invalid join token` (401) | 貼錯字或該 token 已被撤 | 重新 copy |
| Worker 註冊成功但一直 OFFLINE | 心跳打不到中央 | 檢查 `CENTRAL_API_URL` 及網路 |
| 學生 upload timeout | `WORKER_PUBLIC_URL` 不對或防火牆擋住 | 從別的網路 curl `${WORKER_PUBLIC_URL}/health` 測試 |
| Isaac Sim 起不來 (real 模式) | 沒有 nvidia-container-toolkit | 主機層安裝 + 重啟 docker daemon |
| 兩個 worker 撞 port | `.env` 手動改過導致衝突 | 讓 setup.sh 自動選；或 `./setup.sh --reset` |

需要更詳細的排錯，`docker compose logs -f` 是第一站。

---

## 9. 需要跟中央溝通的時機

- 一開始要拿到 SCHOOL_ADMIN 帳號 → 給 HCIS-Lab 一個聯絡 email
- Isaac Sim 版本 / task config 有更新 → 中央會統一佈署，你們不用做事
- Worker 硬體要下線退役 → 在 Workers tab 把它設成 REVOKED，之後可以 delete
- 學生反應 upload 一直失敗 → 你們先看 Observability + logs；查不出再找我們

**平台端的東西 (contest 時間、task 定義、evaluation script) 都由 HCIS-Lab
統一管，SCHOOL_ADMIN 看不到那些 tab 也不需要。**
