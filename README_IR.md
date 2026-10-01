# Active IR＋広角Depth 試作版

この版は既存の `cardboard-counter-v2` と同じ6コンテナ構成、API、画面、
体積計算・箱数推定を使います。カメラ取得、ROI画像、投影条件だけを
Femto MegaのActive IR＋未整列の広角Depthへ切り替えています。
元のディレクトリやデータベースをコピーして使う設計ではありません。

## データの流れ

1. `native/orbbec_ir_depth_stream.cpp` は同じFrameSetのIRとDepthを取得します。
   既定は512×512、15fpsです。RGBストリームもD2C位置合わせも有効にしません。
2. `camera/source.py` の取得契約は16 bit IR、ミリメートル単位Depth、
   両者の内部パラメータです。`camera/stream.py` は1台に1接続を維持します。
3. ライブ閲覧中だけIRを8 bit JPEGへ変換します。フレームバッチ保存時には
   16 bitの `ir.npz` とROI表示用の `rgb.jpg` を1回作成します。
   `rgb.jpg` にRGB撮影結果は入っていません。
4. `common/ir_depth.py` はIR/Depthの画素数と投影条件を照合します。
   `common/depth_projection.py` は歪み補正済みの視線表をカメラ条件ごとに
   一度作り、複数のDepthへ再利用します。
5. ROIはIR画像上で設定し、XYZは同じ画素のDepthから計算します。
   平面・パレット外周・測定計画は校正時に準備し、監視の反復内で再計算しません。

外部のプログラムはcameraサービスの `/v1/cameras/{camera_id}/frame-batches` を
利用できます。返るmanifestには `ir_path`、`depth_frames_path`、
`intrinsics` が含まれます。`intrinsics.ir` と `intrinsics.depth` に
各センサーの内部パラメータが入ります。`preview_path` と
`reference_shape` は表示用IR画像を表します。`include_xyz=true` の場合だけ中央値Depthと
XYZも作ります。パレット固有の処理はcameraサービスに含めていません。
RGBカメラを使わないため、`intrinsics.color` は `null` です。

## 元の版と同じサーバーで起動する

カメラへ到達できるサーバー上で、元のディレクトリと同じ階層に配置します。
`data/`、`.env`、`.git/`、`.venv/`、`frontend/node_modules/` を
元の版からコピーしないでください。`third_party/orbbec_sdk/SDK/` と同梱ライセンスはこのリポジトリに含まれ、
カメラのビルドに使います。SDKの利用条件は `third_party/orbbec_sdk/LICENSE.txt` を確認してください。
IR版の `camera` を起動する前に、元の版で対象カメラの監視を止め、
元の版の該当 `camera` サービスを停止してください。

```bash
cd /path/to/cardboard-counter-ir
cp .env.sample .env
# .env のPOSTGRES_PASSWORD、必要ならPOSTGRES_RUNTIME_UID/GIDを設定
docker compose config --quiet
docker compose build
docker compose up -d postgres measurement camera camera-2
docker compose run --rm --no-deps api \
  python -m cardboard_counter_v2.api.migration_cli db upgrade
docker compose up -d
```

Compose名は `cardboard-counter-ir`、Webは50072、APIは58100、
cameraは58101と58103、measurementは58102、PostgreSQLは55532です。
元の版とはコンテナ名、ポート、イメージ名、`./data` が分かれます。
ポートはサーバーで空いている値に `.env` で変更できます。

同じ物理Femto Megaへ2つのcameraサービスを同時接続できるとは限りません。
実機試験では、対象カメラを使う元の `camera` サービスを停止し、
監視ジョブを止めてからIR版を接続してください。試験終了後はIR版の
`camera` を停止し、元の `camera` を再開します。もう一台を試す場合も
対応するサービスだけを切り替えます。

## 現場で最初に確認すること

- Active IRとDepthが同じ512×512で連続取得できるか。
- パレット位置の床と積載箱でDepthが0にならず、床平面校正が成立するか。
- ROIを置き、校正後に一度測定できるか。元の版のROIや床校正は流用しません。

Femto MegaのWFOVは公称120°×120°ですが、512×512の公称距離上限は
2.88mです。過去のRGB版撮影には床と思われる箇所が約3.1mの例があります。
画面にIRの床が見えても、Depthが0ならその場所は測定できません。
また、広角の外周は円形の無効領域を含むため、120°×120°の矩形全体を
測定可能範囲とは扱わないでください。

仕様: https://doc.orbbec.com/documentation/Orbbec%20Femto%20Mega%20Documentation/Femto%20Mega%20Hardware%20Specifications

DepthとIR: https://doc.orbbec.com/documentation/Orbbec%20Femto%20Mega%20Documentation/Depth%20Camera%20%28Femto%20Mega%29

## 互換キーと制約

既存のAPI・DB・画面を維持するため、`rgb_path`、`rgb.jpg`、`color_shape`、
`align_depth_to_color` という古い名前が残ります。この版では順に
IRプレビューの場所、IRプレビュー画像、IR画像の画素数、常にfalseを意味します。
16 bit IRの生値は `ir.npz` に保存します。測定値の算出はIR輝度ではなく
Depth/XYZで行います。点群成果物のRGBチャンネルにはIRの同じ濃淡値が入ります。

実機での同時ストリーム、距離、ROI有効点数、歪み係数の精度は
このPCからは確認できていません。現場サーバーで初回撮影を行い、
無効Depthの分布と既知寸法の箱の測定結果を照合してください。
