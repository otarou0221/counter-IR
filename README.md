# Cardboard Counter IR trial

このディレクトリはActive IR＋広角Depthの独立試作版です。起動方法、データ形式、
実機確認項目は [README_IR.md](README_IR.md) を先に確認してください。
以下は元のRGB版の設計資料であり、RGBの記述はIR版の動作を示しません。

現行Cardboard Counterから、床基準ROIをパレット高さ分だけ平行移動する方式だけを切り出した再構築版です。
測定方式は `pallet_plane_2roi` 固定で、旧空Depth画素差、ROI中央値、旧単一ROI平面、
学習モデルによる画像推論は使いません。新方式で得た3D実測体積だけを入力に、OR-Tools CP-SATで
登録した箱クラスの整数個数を求めます。

## 6コンテナ（cameraサービス2台）

| サービス | 責務 | 公開範囲 |
|---|---|---|
| `web` | React静的配信、APIプロキシ | ホスト `${CARDBOARD_V2_PORT:-50062}` |
| `api` | 設定保存、校正・測定の調整、結果・成果物配信 | ホスト `127.0.0.1:${CARDBOARD_API_PORT:-58000}` |
| `camera`（camera-1） | 1台目のOrbbec接続、ライブ映像、RGB-Dバッチ、要求時だけ中央値Depth・XYZ | ホスト `127.0.0.1:${CAMERA_SERVICE_HOST_PORT:-58001}` |
| `camera-2` | 2台目のOrbbec接続。同じcameraイメージを独立実行 | ホスト `127.0.0.1:${CAMERA_2_SERVICE_HOST_PORT:-58003}` |
| `measurement` | 受領XYZの検証、一回性平面校正、高さグリッド、局所突起除外、体積・3D | ホスト `127.0.0.1:${MEASUREMENT_SERVICE_HOST_PORT:-58002}` |
| `postgres` | 箱種類・カメラ・設置・校正・在庫履歴 | ホスト `127.0.0.1:${POSTGRES_HOST_PORT:-55432}` |

Docker定義はサービス名と同じディレクトリへ統一しています。

```text
docker/
├── web/Dockerfile
├── api/
│   ├── Dockerfile
│   └── requirements.txt
├── camera/
│   ├── Dockerfile
│   └── requirements.txt
└── measurement/
    ├── Dockerfile
    └── requirements.txt
```

Pythonソースも、実行するコンテナを最初にたどれる構成です。

```text
src/cardboard_counter_v2/
├── api/
├── camera/                  # カメラ専用
├── measurement/
│   ├── core/                # 3D・平面・高さグリッド
│   └── optimization/        # CP-SAT箱数最適化
└── common/                  # 共有契約・保存形式・汎用Depth集約／投影
```

各Pythonイメージは全ソースをコピーせず、自分のサービスディレクトリと`common`だけを含みます。
`common`はカメラ・API・測定の通信形式と、用途非依存のDepth集約・XYZ投影を共有するため、
特定コンテナの配下には置きません。

カメラ1台につきcameraコンテナを1つ使用します。APIは各カメラの`camera_service_url`を参照して
撮影・状態確認・ライブ映像を専用コンテナへ振り分けます。
各パレットは使用する`camera_id`を持ち、別カメラの撮影・校正データを混在させません。
APIと数値処理からSDK・USB依存を分離しています。
対象はIP接続のネットワークカメラです。
全サービスは `./data` を共有し、撮影・設定・結果をコンテナ再作成後も保持します。
PostgreSQLは`${CARDBOARD_DATA_DIR:-./data}/database`へ保存し、DBへ接続するコンテナは`api`だけです。
既定ではプロジェクト内の`data/database`がPostgreSQLのデータディレクトリになります。
PostgreSQLコンテナの実行UID/GIDは既定で`1000:1000`とし、ホストユーザーから同ディレクトリへ
通常どおりアクセスできます。ホストのUID/GIDが異なる場合は`.env`の`POSTGRES_RUNTIME_UID`と
`POSTGRES_RUNTIME_GID`を`id -u`、`id -g`の値へ変更します。DBファイル自体の手動編集は行わず、
データ変更にはSQLを使います。
開発・保守用として、ホスト自身からは次のアドレスで各サービスへ直接接続できます。

| サービス | ホストからの接続先 |
|---|---|
| Web | `http://localhost:50062` |
| API | `http://localhost:58000` |
| Camera 1 | `http://localhost:58001` |
| Camera 2 | `http://localhost:58003` |
| Measurement | `http://localhost:58002` |
| PostgreSQL | `localhost:55432` |

Web以外のポートは`127.0.0.1`だけにbindし、LANへは公開しません。ポート番号は`.env`の
`CARDBOARD_API_PORT`、`CAMERA_SERVICE_HOST_PORT`、`CAMERA_2_SERVICE_HOST_PORT`、`MEASUREMENT_SERVICE_HOST_PORT`、
`POSTGRES_HOST_PORT`で変更できます。
API、Measurement、PostgreSQLには、それぞれ共有相手のいないホストアクセス専用bridgeを
割り当てています。DB専用networkへ参加するアプリケーションは引き続きAPIだけです。

## 起動

DB構造と旧撮影データはAPI起動時に自動変換しません。初回または更新時は、先に移行コマンドを
明示実行します。

```bash
cp .env.sample .env
docker compose build
docker compose up -d postgres measurement camera camera-2
docker compose run --rm --no-deps api \
  python -m cardboard_counter_v2.api.migration_cli db upgrade
docker compose run --rm --no-deps api \
  python -m cardboard_counter_v2.api.migration_cli data plan
docker compose run --rm --no-deps api \
  python -m cardboard_counter_v2.api.migration_cli data upgrade
docker compose run --rm --no-deps api \
  python -m cardboard_counter_v2.api.migration_cli capture-layout plan
docker compose run --rm --no-deps api \
  python -m cardboard_counter_v2.api.migration_cli capture-layout upgrade
docker compose up -d
docker compose ps
```

ブラウザは `http://localhost:50062` を開きます。

本番運用前に`.env`の`POSTGRES_PASSWORD`を必ず変更してください。コンテナ間では引き続き、
`api`と`postgres`だけが参加するDB専用internal networkで通信します。

## DBを保持したサーバ更新

プログラム更新時は、PostgreSQLのデータを削除せず、次の順番でバックアップ、ビルド、
DBマイグレーション、コンテナ更新を行います。

```bash
cd ~/work/shirair/cardboard-count/cardboard-counter

# 1. 現在のDBをホスト側へバックアップ
mkdir -p data/backups
backup_path="data/backups/pre_deploy_$(date +%Y%m%d_%H%M%S).sql"
docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > "$backup_path"
test -s "$backup_path" && ls -lh "$backup_path"

# 2. 更新するブランチを取得（<ブランチ名>は実際の名前へ置換）
git fetch origin
git switch <ブランチ名>
git pull --ff-only origin <ブランチ名>

# 3. 稼働中のDBを残したまま新しいイメージを作成
docker compose build

# 4. DBへ書き込むサービスを停止してスキーマを更新
docker compose stop api measurement web
docker compose run --rm --no-deps api \
  python -m cardboard_counter_v2.api.migration_cli db upgrade
docker compose run --rm --no-deps api \
  python -m cardboard_counter_v2.api.migration_cli capture-layout plan
docker compose run --rm --no-deps api \
  python -m cardboard_counter_v2.api.migration_cli capture-layout upgrade

# 5. 新しいコンテナを起動して確認
docker compose up -d
docker compose ps
curl -fsS http://127.0.0.1:58000/api/health
curl -I "http://127.0.0.1:${CARDBOARD_V2_PORT:-50062}/"
```

`db upgrade`が失敗した場合は、後続の`docker compose up -d`を実行せず、エラーを確認します。
Captureの`data upgrade`は旧撮影データを一度だけ変換するコマンドであり、通常の更新時には実行しません。
DBを保持する更新では`docker compose down -v`や`data/database`の削除を行いません。
コンテナの再作成やイメージ更新だけでは、`data/database`内のDBデータは消えません。

## 在庫履歴データベース

DB構造はAlembicでバージョン管理します。APIはDBリビジョンがコードと一致しない場合、勝手に列を
追加せず起動を拒否します。`db upgrade`成功後に次の12テーブルを使用し、設定のカメラと
設置・接続情報を同期します。削除されたカメラは`active=false`、設置履歴は終了日時を設定します。

- `box_types`
- `cameras`
- `locations`
- `camera_installations`
- `captures`
- `pallet_slots`
- `pallet_calibrations`
- `measurement_settings`
- `realtime_measurements`
- `inventory_history`
- `factory_maps`
- `pallet_map_placements`

箱種類と外寸は`box_types`を正本とし、`box_type_id`、箱名、幅・奥行・高さを
保存します。従来の`settings.json`がある場合は`data upgrade`で一度だけORM経由で移行し、
DBからの再読込みに成功した後で旧JSONをバックアップへ退避します。DB未設定・接続失敗時はJSONへ自動で
フォールバックせず、APIの起動または読込みをエラーにします。

カメラの管理コード、メーカー、機種、製造番号は`cameras`へ保存します。IP、物理設置、解像度、
XYZ生成に使用した内部・歪みパラメータは`camera_installations`で履歴管理します。IPだけの変更は
同じ設置履歴を更新し、場所・解像度・整列条件など撮影幾何が変わる場合は旧設置を終了して新しい
履歴を作成します。内部パラメータは`fx`、`fy`、`cx`、`cy`だけを保存し、解像度や整列条件を
JSONへ重複保存しません。1カメラ1cameraコンテナの接続先は`camera_service_url`へ保存します。
`captures`は撮影ID、設置履歴ID、用途、撮影時刻、枚数を保存します。解像度・投影条件は紐づく
設置履歴から復元します。ファイルパスはCapture IDから固定ディレクトリと
`rgb.jpg`、`depth.npz`、`xyz.npz`を解決するため、パスを重複保存しません。Capture保存形式は
`captures.storage_version`で管理し、現行はカメラ・用途別配置のバージョン3です。

旧Capture変換は`data plan`で全件を事前検証し、`data upgrade`でDepthからXYZを生成してDBへ
登録します。1件の変換失敗でAPI起動を巻き込まず、失敗元ファイルは残します。成功した旧JSONと
旧形式ファイルは`data/backups/capture_v1/<capture_id>/`へ退避します。同じコマンドを再実行しても
未移行分だけが対象になります。

DB登録済みのバージョン2以前のCaptureは、API・measurementを停止した状態で
`capture-layout plan`により事前検証し、`capture-layout upgrade`でカメラ・用途別構成へ移動します。
ファイル移動後に中断しても再実行でき、DB更新前の移動済みCaptureを自動復旧します。

現在は`camera_1 → http://camera-1:8001`、`camera_2 → http://camera-2:8001`です。
将来増設するときは、手作業でComposeを編集せず、先に追加計画を確認します。

```bash
./tools/camera-service plan camera_3
./tools/camera-service add camera_3
./tools/camera-service validate --compose
```

CLIは空いている既定ホストポートを選び、`deploy/cameras.json`からComposeと`.env.sample`の
管理ブロックを生成します。個別指定する場合は`--host-port 58004`を付けます。
起動が必要な場合だけ`./tools/camera-service start camera_3`を実行します。この起動は`--no-build`で、
全カメラ共通の`CAMERA_IMAGE`を再利用します。カメラ設定のURLはCLIが表示する
`http://camera-3:8001`へ向けます。APIの処理は台数を固定しておらず、URL単位に設定を配布します。

リリースイメージはカメラ台数ではなくアプリのソース変更時だけ作成します。GitLab Container Registryへの
固定タグ保存、digest固定、tarバックアップの手順は
[`docs/CONTAINER_IMAGE_RELEASES.md`](docs/CONTAINER_IMAGE_RELEASES.md)を参照してください。

`pallet_slots`は`camera_installation_id`に直接紐づく固定監視枠を表し、表示名、監視有効状態、
低在庫警告体積、メール再有効化増加量を保存します。警告設定は校正履歴から独立しているため、
同じ設置履歴で再校正しても維持されます。移設・解像度変更などで新しい設置履歴を作成した場合は、
パレット枠も新しく作成し、旧枠と過去の校正・測定履歴を維持します。
DBの`pallet_calibrations`には、対象監視枠、対象設置履歴、校正に使った床撮影の
`calibration_capture_id`、
グリッド幅を通常カラムとして保存します。校正履歴は1監視枠につき1行とし、
そのパレットの床ROI、床平面、パレット高さ、周辺余白は`calibration_data`へ保存します。校正manifestとNPZマスクは
作成しません。APIがDBから最小校正定義を読み、Measurementが原点・U/V基底・外周・
グリッド・マスクと箱推定用の固定計画を監視開始前に1回だけ再構築してメモリへキャッシュします。

測定結果は`realtime_measurements`へ保存します。成功・失敗とも対象パレットごとに1行を作成し、
必須の`pallet_calibration_id`からパレット枠、設置履歴、カメラを特定します。失敗時はCapture IDと
在庫値をNULLにしてエラー概要を保存します。カメラ全体の取得に失敗した場合は、そのカメラで
測定しようとした有効パレット校正ごとに失敗行を作成します。
測定全体・カメラ別のIDと、実行元を表す`source`は持ちません。
在庫数はCP-SAT最良候補の箱種類別個数合計を正式値とし、`box_counts`はJSONBで保存します。
低在庫は実測体積が`pallet_slots.low_stock_threshold_liters`以下かで判定し、
`realtime_measurements.is_low_stock`へ保存します。独立した警告履歴テーブルは使用しません。
各成功測定値は`pallet_calibration_id + finished_at`で識別します。パレット番号、設置場所、カメラは
パレット校正履歴から辿ります。測定時のCaptureは`measurement_capture_id`で参照します。
`inventory_history`は在庫変化の長期保存用で、パレット校正ID、測定Capture ID、測定日時、在庫数、
体積、箱内訳、低在庫状態と閾値だけを持ちます。測定保存と同じトランザクションで、同じ設置場所・
パレット番号の直前累積値から在庫数が変化した場合だけ追加します。リアルタイム成功・失敗履歴は
測定完了から7日間保持し、当該カメラの次回測定保存時に7日より古い行を削除します。
累積履歴は6か月を超えた行をAPIの定期整理（既定1日1回）で削除します。判定時の警告体積とメール再有効化増加量は、
リアルタイム・累積履歴にもスナップショット保存します。

### 低在庫メール

低在庫警告はUI表示とメール送信を分離しています。UIは
`volume_liters <= low_stock_threshold_liters`の間、常に警告を表示します。
メールは監視開始後の最初の測定では送らず、最初の体積がしきい値より大きい場合だけ有効状態で
開始します。送信後は`low_stock_threshold_liters + email_rearm_margin_liters`まで回復するまで
再送しません。SMTP送信は専用キューで行うため測定周期を止めません。送信に失敗した場合は
メールを無効化せず、次の正常測定で再試行します。
送信成功時刻は該当する`realtime_measurements.email_sent_at`と、同時刻の累積行がある場合は
`inventory_history.email_sent_at`へ保存します。

SMTP認証情報と宛先はDBへ保存せず、`.env`へ設定します。

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-user
SMTP_PASSWORD=your-password
SMTP_FROM=cardboard-counter@example.com
SMTP_SECURITY=starttls
SMTP_TIMEOUT_SECONDS=10
LOW_STOCK_EMAIL_TO=materials@example.com,manager@example.com
```

`SMTP_SECURITY`は`starttls`、`ssl`、`none`のいずれかです。必須項目が未設定の場合も測定は継続し、
現場UIへ「SMTP未設定」と表示します。測定失敗時は直前の正常結果と低在庫表示を維持し、
その測定ではメール状態を変更しません。

`measurement_settings`は1行だけを持ち、測定間隔、正式測定のDepth枚数、同時測定数を保存します。
初期値は600秒、1枚、3台です。
`factory_maps`は工場名・建物／工場棟名・フロア名とPNG画像本体を保持し、`pallet_map_placements`はパレットごとの
マップIDと0～1の相対X・Y座標を保持します。マップ削除時は画像と配置だけを削除し、カメラ、
パレット、測定履歴は維持します。マップ・配置の永続JSONファイルは作りません。
新しいマップの登録時は、表示名、工場名、建物／工場棟名、フロア名、PNG画像をすべて必須とします。
DB障害時に測定結果をJSONへ退避する経路は持ちません。障害を隠さず、接続状態は
`GET /api/status`と`GET /api/health`で確認できます。

Orbbec SDKはGit管理外です。元プロジェクトと同様に次を配置してください。

```text
third_party/orbbec_sdk/SDK/include
third_party/orbbec_sdk/SDK/lib
```

OrbbecはネットワークカメラでもSDK内部でlibusbを初期化します。そのため`camera`コンテナには
ホストの`/dev/bus/usb`を読み取り専用でマウントします。実際の映像通信は引き続きEthernet経由です。

## 操作順

画面上部で「工場マップ」「現場用」「設定」「保守・診断」を切り替えます。
どの画面でも測定方式は `pallet_plane_2roi` 固定です。
現場用の工場マップは`/field/map`、カメラ詳細は`/field/camera/<camera_id>`です。
「現場用」は選択中カメラを表示し、そのカメラ選択を設定・保守診断でも共通して使用します。
各URLは直接開くことができ、ブラウザの戻る・進むと再読み込みにも対応します。

1. 設定画面の最上部で設定対象カメラを選択
2. カメラ接続先、箱クラスと寸法など、必要な詳細設定を保存
3. パレットを置かずに「床画像を撮影」を押すか、同じカメラの保存済み床撮影を選ぶ
4. 画像上でパレット定位置を周辺余白込みでドラッグ選択し、「ROI設定を保存して校正」を押す
   - 画面下部の「設定を保存して校正」でも、設定保存後に床画像を選択済みの有効カメラを校正する
5. ROI保存後に床平面を推定し、床上の3D外周を設定したパレット高さ分だけ平行移動する
6. 現場用画面で工場マップPNGを登録し、「配置を編集」で未配置カメラを図面へドラッグして保存
7. 箱を積載して、現場用画面から「常時監視を開始」を押す
8. マーカーの緑・赤・グレーを確認し、クリックして対象カメラのライブ映像・測定値を確認

工場マップは`react-konva`で描画します。通常時のマーカーは固定され、配置編集モードの間だけ
ドラッグできます。マーカーは正常が緑、低在庫が赤、測定エラー・切断・未測定・監視停止・
更新遅延がグレーです。1台のカメラに複数パレットがある場合はツールチップへ個別状態を表示し、
測定エラー時は直前結果にかかわらずカメラ全体をグレーにします。
マップ下部には同じダッシュボード応答から作るカメラ・パレット状態一覧を表示します。
追加のAPI取得は行わず、一覧はTabキーで選択してEnterまたはSpaceキーでカメラ詳細を開けます。
初回取得中、未登録、初回通信失敗を別の状態として表示します。一度取得した後の更新に失敗した場合は、
最後の正常なマップを残したまま更新失敗を通知し、画面上から再読込みできます。
全画面共通のステータスバーで監視状態と操作結果を表示し、成功・警告・失敗を色分けします。
監視詳細ではカメラ別エラーを原因・対応方法・発生日時に分け、生のログは折りたたんだ
「技術的な詳細」へ表示します。問題に応じて現場用、設定、保守・診断画面へ直接移動できます。

設定画面は登録カメラを選択し、選択中の1台と、そのカメラに属するパレットだけを表示します。
カメラ機器情報は常時表示し、必須の設置場所設定は初期状態で開きます。実験用の測定処理詳細だけは
折りたたみ、上部のカメラ選択欄が画面外へ出ると「設定画面の上部へ戻る」を表示します。
床基準撮影はカメラごとに新しい順で最大5件を保持します。新規撮影または保存撮影の選択が
成功した後だけ、現在使用中の撮影を保護して、超過した未使用の古い撮影から削除します。
箱寸法は共通カタログで一度だけ管理し、実際に測定する箱クラスはカメラ配下の各パレットで選択します。
共通箱カタログの「箱を追加」で箱名と外寸を登録できます。設定は項目別フォームだけで編集し、
設定オブジェクト全体のJSON編集欄は持ちません。
「カメラを追加」は設定オブジェクトを作るだけで、設定保存まではカメラ接続を生成しません。
接続先IPはIPv4専用の4分割入力で、各区画を0〜255に制限します。`.`による次区画への移動、
Backspaceによる前区画への移動、完全なIPv4アドレスの貼り付けに対応します。
API・cameraサービス共通の契約でもIPv4を検証し、不正な値はカメラ反映やDB保存より前に拒否します。
未保存設定がある状態でブラウザの再読み込みや画面離脱を行う場合は確認を表示します。
未保存判定は入力操作の有無ではなく、現在値と最後に保存・読込みした設定の値差分で行うため、
文字入力やチェックボックスを元の値へ戻した場合は保存を要求しません。
入力エラーは保存バーに件数と一覧を表示します。エラーを選ぶと対象カメラへ切り替え、必要な詳細欄を
開いてから該当項目へスクロール・フォーカスします。無効な主要操作は待機カーソルを使わず、
禁止カーソルと操作できない理由を表示します。

## 保存データの再解析

「保守・診断」では、最初に診断・再解析するカメラを選びます。現在撮影と保存済み撮影の選択は
このカメラで統一され、床基準撮影と積載後撮影に別カメラのデータが混ざりません。
積載後撮影には通常監視と診断撮影の両方を新しい順に表示し、表示上も区別します。
最初の50件だけを取得し、必要な場合に50件ずつ追加で読み込みます。DBテーブルは追加せず、
既存のCapture台帳にある`retention`で撮影元を区別します。

保存済みの床基準撮影と積載後撮影を手動選択すると、カメラに再接続せず新方式を再実行します。
再解析には保存Captureと現在保存されている同じカメラのパレット・ROI設定を使用します。
現場用の校正IDと最終測定結果は変更しません。
生点群、現在フレーム候補、側面除外・平面投影・外周制限、高さグリッド、局所突起除外、
最終体積の6段階を1つの3D診断で切り替えられます。
各段階は「高さカラーマップ」とPotreeの「ポイントクラウド」を切り替えられます。点群表示では、
その段階まで残った点だけを実写RGBで見る表示と、周辺背景を実写RGBで残しながら処理対象を赤く強調する表示を
選べます。色と背景は診断表示専用で、点の採否や体積値には影響しません。
段階4〜6ではさらに「表面点群／立体充填」を切り替えられます。立体充填は設定したグリッドのセル中心を校正済み
パレット面から上面まで基本20mm間隔で埋め、代表上面点のRGBを縦方向へ複製します。段階4は補正前、
段階5・6は局所突起補正後の高さを使用し、段階5・6のPotreeデータは共有します。
最終3D HTMLでは、Plotlyによる高さグリッドの柱状体積、パレット周辺を実画像色で残しつつ体積採用領域だけを
高さ色にしたPotree点群、採用セルをパレット面から測定高まで埋めた高さ充填ポイントクラウドを切り替えられます。
周辺付き点群の色上限は採用セル高さの98パーセンタイルを使い、孤立高点は赤へ丸めて段差の視認性を保ちます。
充填表示は高さごとに灰色→橙→赤で色分けし、基本20mm間隔、100万点を超える場合は表示間隔を
自動調整します。いずれも表示専用で、体積計算結果には影響しません。Potree側では回転・ズームに加えて、
距離・高さ・断面などの点群用ツールを使えます。点群は成果物生成時だけ標準LAS（座標単位m、Z-up）へ
書き出してPotree形式へ変換します。常時監視ではRGB読込み、LAS出力、Potree変換を行いません。

ROI選択はボタン操作で保存した床のRGB静止画、または同じカメラの保存済み床RGB上で行い、
保存値はRGBと位置合わせされたDepthへ測定側が自動変換します。
保存するROIは床上のパレット定位置です。床平面上で3D外周を確定してから、同じ画素視線へ
再投影せず、床法線のカメラ側へ`pallet_height_mm`だけ平行移動してパレット上面を作ります。
`pallet_roi_margin_mm`は外周から内側へ除外し、周辺障害物を体積へ含めません。
積載後は画像上のROIで切らず、現在フレームをパレット面へ投影した後に、校正済みの物理外周内だけを採用します。
このため、斜め視点で箱が床ROIの画像範囲から見かけ上はみ出しても、3D上で測定外周内なら失われません。
未保存の設定がある間は、異なるROIで撮影しないように校正・測定・常時監視を開始できません。

単発測定の代わりに「常時監視を開始」を押すと、現在Depthの撮影と新方式測定を
繰り返します。`monitor_interval_seconds` は既定600秒で、各周期の開始時刻から次の周期開始までの
間隔です。全カメラを周期ごとにジョブ化し、`measurement_concurrency`（既定3）以下の台数だけを
同時実行します。1台が失敗しても他カメラの測定とDB保存は継続し、失敗したカメラだけの履歴を
保存します。処理時間が周期を超えた場合は、前周期完了後すぐ次を開始し、周期同士は重複させません。
「常時監視を停止」を押した場合、実行中の1回を完了してから停止します。
監視中は設定変更と床基準再撮影を行えません。
ただし、低在庫警告体積とメール再有効化増加量だけは監視中も変更でき、次の測定周期から反映します。

ライブ映像と測定撮影は、各cameraコンテナが所有する1本のOrbbec接続を共有します。
測定のために別の接続を開かず、各カメラは同じ連続ストリームからRGB、未加工Depth群、
内部パラメータ、各フレーム時刻を保存します。汎用カメラAPIの既定値ではここまでとし、
`include_xyz=true`の要求時だけ、ゼロを除外した時間中央値Depthと画素対応XYZを各1回生成します。
CardboardのAPIワークフローはこの任意出力を要求し、`measurement`は受領XYZを再計算せず使用します。
ブラウザへの配信形式はMJPEGです。
C++カメラサブプロセスは各cameraコンテナのFastAPI設定時に開始し、コンテナ停止時に終了します。
ブラウザの表示・非表示では物理カメラ接続を切り替えません。通信断が発生した場合は、
FastAPIが動作している限り3秒間隔でSDKサブプロセスを再生成して自動再接続します。
カメラ側はDepthフィルタを適用せず、未加工Depthを保存します。
新方式のROIはRGB上で選択するため、`align_depth_to_color=true`は必須です。
RGB/Depth形状と整列結果は撮影台帳へ保存し、未整列Depthは測定前に拒否します。

汎用カメラAPIのフレーム群要求は、必要な利用者だけXYZを追加できます。

```json
{
  "frame_count": 1,
  "warmup_frames": 5,
  "include_xyz": true,
  "include_raw_frames": false
}
```

`include_xyz=true`では`median_depth_path`、`xyz_path`、
`xyz_source=temporal_median_ignore_zero`を一時manifestへ返します。CardboardのAPIは常にXYZを要求しますが、
通常監視では`include_raw_frames=false`として、同じDepth群をNPZへ二重保存しません。
カメラサービス自体は生フレーム保存を既定で維持するため、別用途の利用者は従来どおり取得できます。

床基準ROI用の撮影は床平面校正にも同じデータを使います。現在測定はフレーム全体から候補点を取得し、
パレット面へ投影後に校正済みの物理外周で制限します。
床平面・パレット上面座標・外周マスクはカメラごとの床撮影時に一度だけ計算し、
通常測定では校正IDごとにメモリへキャッシュして再利用します。
床校正は既定30枚、正式測定は既定1枚を使います。1枚の場合は中央値演算を省略します。
集約DepthとXYZはカメラごとの撮影1回につき各1回だけ生成し、固定の画素光線はカメラ内部パラメータと
Depth形状ごとにキャッシュします。`measurement`は受領XYZから局所法線を測定1回だけ計算し、
同じカメラに属する有効パレットで共有します。別カメラの撮影は並列に取得します。
新方式のCaptureは中央値DepthとXYZを必須とし、XYZを持たない旧Captureを測定側で復元しません。
常時監視は初期値で3D HTML・高さ配列を作らず、
デバッグ画面の診断時だけ成果物を保存します。PotreeConverterもこの成果物生成経路だけで短時間起動し、
常駐プロセスや監視ループにはしません。
校正・設定が同じ間は、Depth座標へ変換済みの床ROIと箱体積も
`MeasurementPlan` として校正ランタイム内で再利用します。校正キャッシュが破棄されると
実行計画も一緒に破棄されます。Depth群は最初から連続配列へ格納し、RGBは最後の1枚だけ複製します。
監視開始時にAPIがMeasurementへ校正定義と箱設定を登録して`runtime_id`を受け取り、通常周期は
`runtime_id`と現在Captureだけを送ります。Measurement再起動でキャッシュが消えた場合は自動再登録して1回再試行します。
局所法線は高さ制限を設けずに箱が写り得る保守的な画像範囲だけで計算し、同じカメラの2パレットで共有します。

箱寸法は全パレット共通の箱カタログへ一度だけ登録します。パレットごとに単品で置かれる箱と、
複数種類が同時に存在できる混在グループ、局所突起判定の基準箱を選びます。
箱寸法の検証、選択クラスの解決、体積の整数単位化などの固定情報は`MeasurementPlan`作成時に1回だけ準備し、
各許可ルールを別々にCP-SATで解いてから、3D実測体積との差が最小になる候補を選びます。
設定していない箱同士は組み合わせません。目的関数は次です。

```text
|3D実測体積 - Σ(箱クラスの整数個数 × 幅 × 奥行 × 高さ)|
```

画像検出による確定箱は使いません。体積が同じまたは近い複数の内訳がある場合は、最良候補に加えて
代替候補と「あいまい」判定を結果へ残します。`volume_liters`は整数化前の3D実測値を維持します。

通常の常時監視では生Depth群の一時NPZを作らず、集約後の一時FrameBatchだけを削除します。Captureは
RGB・Depth・XYZだけを残し、撮影条件はDB台帳で一元管理します。手動デバッグ撮影も合わせて
カメラごとに新しい順で最大500件を保持し、DB台帳とファイルを同時に整理します。
床基準撮影はカメラごとに最大5件を保持し、使用中の撮影は削除しません。両方の上限値は
`common/capture_policy.py`へ集約しています。
通常監視は測定ディレクトリや最新結果JSONを作らず、正式な測定履歴をPostgreSQLへ保存します。
床基準撮影はこの上限に含めません。生バッチの異常終了残骸は既定24時間後に整理します。

同じ空撮影、有効パレット、平面ROI、グリッド幅のデバッグ再解析は保存済み校正を再利用し、
RANSAC平面推定を繰り返しません。

カメラは `driver` 名とフレームソース登録で切り替えられ、既定は
`orbbec_network` です。Cardboard測定ロジックを変更せず別のRGB-D入力を追加できます。
カメラ一覧は設定保存時だけcameraサービスへ反映し、監視ループでは再設定・再接続を行いません。

APIの撮影・校正・測定処理は、`CaptureService`、`CalibrationService`、
`MeasurementJobRunner`、`CaptureRetentionService`へ分離しています。
`MeasurementWorkflow`は既存ルーターとの互換入口だけを担当します。DBアクセスも
`SettingsRepository`、`CaptureRepository`、`CalibrationRepository`、
`MeasurementRepository`、`InventoryHistoryRepository`へ分離し、複数テーブルを同時更新する
校正保存・測定保存では同じSQLAlchemyトランザクションを共有します。

## テスト

```bash
python -m pytest -q
cd frontend && npm ci && npm test && npm run build
docker compose config
```

Potree 1.8.2とPotreeConverter 2.1.3はDockerビルド時に公式配布元から固定バージョンを取得し、
SHA-256を検証します。どちらも登録やライセンスキーを必要としないBSD 2-Clauseの
オープンソースです。詳細と同梱場所は[サードパーティライセンス](docs/THIRD_PARTY.md)を参照してください。
