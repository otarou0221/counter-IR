# サードパーティライセンス

点群表示機能は、登録・アカウント・ライセンスキーを必要としないオープンソースだけで構成します。

| ソフトウェア | 固定バージョン | 用途 | ライセンス |
|---|---:|---|---|
| [Potree](https://github.com/potree/potree) | 1.8.2 | ブラウザ点群ビューア | BSD 2-Clause |
| [PotreeConverter](https://github.com/potree/PotreeConverter) | 2.1.3 | LASからPotree 2形式への変換 | BSD 2-Clause |
| [Konva](https://konvajs.org/) | 10.3.2 | 工場マップとカメラマーカーのCanvas描画 | MIT |
| [react-konva](https://konvajs.org/docs/react/) | 19.2.5 | KonvaのReact連携 | MIT |

Dockerビルドでは公式配布物をHTTPSで取得し、Dockerfileに固定したSHA-256と照合します。
PotreeのライセンスはWebイメージの`/usr/share/nginx/html/vendor/potree/LICENSE`へ、
PotreeConverterと同梱依存関係（LASzip、Brotli、nlohmann/json）の通知はmeasurementイメージの
`/usr/share/licenses/potree-converter/`へ保存します。

PotreeのJavaScript/CSSと必要ライブラリはWebイメージへ同梱されるため、稼働中はCDNや外部サービスへ
接続しません。PotreeConverterはLinux用公式バイナリが配布されていないため、公式ソースから
Dockerのビルド段階でコンパイルし、実行用イメージへ必要な成果物だけをコピーします。
Konvaとreact-konvaもnpm依存関係としてWebイメージへ組み込み、稼働中にCDNへ接続しません。
