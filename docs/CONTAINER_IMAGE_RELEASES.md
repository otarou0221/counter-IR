# コンテナイメージの保存と再利用

## 基本方針

Dockerイメージはアプリのリリース単位で作り、カメラの台数単位では作りません。
`camera_1`、`camera_2`、将来の`camera_3`は、同じ`CAMERA_IMAGE`から別コンテナとして起動します。
カメラ追加CLIは`--no-build`で起動するため、カメラ増設だけでPython、Orbbec SDK、依存ライブラリを
再構築しません。

イメージを更新するのは、対象サービスのソース、Dockerfile、依存パッケージ、Orbbec SDKなどを
変更したリリース時だけです。Dockerfileの公式ベースイメージはタグとdigestを併記し、将来の
再ビルドで同じ土台を取得できるようにします。依存更新時はdigestも意図的に更新してテストします。

## GitLab Container Registryへ保存する

Registryの実際のhost/pathはGitLab管理画面で確認します。URLには`https://`を付けません。
次の例の値は仮のため、そのままpushしないでください。

```bash
REGISTRY_PATH=registry.example/group/cardboard-counter
RELEASE_VERSION=v1.0.0

./tools/release-images plan \
  --registry "$REGISTRY_PATH" \
  --version "$RELEASE_VERSION"
```

計画を確認したあと、ビルドとローカルタグ付けを行います。

```bash
./tools/release-images build \
  --registry "$REGISTRY_PATH" \
  --version "$RELEASE_VERSION"
```

GitLabへログインし、外部書込みを明示確認してpushします。

```bash
docker login <GitLab Registry host>
./tools/release-images push \
  --registry "$REGISTRY_PATH" \
  --version "$RELEASE_VERSION" \
  --confirm-push "$RELEASE_VERSION"
```

`latest`は固定リリースとして使用できません。`v1.0.0`などの上書きしないタグを使用し、GitLab側で
`^v.*`を保護タグにします。cleanup policyは一時的な開発タグだけを対象にし、本番・ロールバック用の
リリースタグを削除しません。

## 本番をdigestで固定する

push後、Registryが返したdigestを使うCompose環境ファイルを生成します。

```bash
./tools/release-images lock \
  --registry "$REGISTRY_PATH" \
  --version "$RELEASE_VERSION" \
  --output deploy/images.env

docker compose --env-file deploy/images.env config --quiet
docker compose --env-file deploy/images.env pull
docker compose --env-file deploy/images.env up -d --no-build
```

`deploy/images.env`は環境固有のためGit管理しません。形式例は`deploy/images.env.example`にあります。
リリース記録には、使用したGit commit、固定タグ、生成した`@sha256`の5イメージを残します。

## Registry障害に備えてtar保存する

Registryとは別のNAS・バックアップ媒体へ、リリース一式を保存します。既存ファイルは上書きしません。

```bash
./tools/release-images export \
  --registry "$REGISTRY_PATH" \
  --version "$RELEASE_VERSION" \
  --output "deploy/image-backups/cardboard-counter-${RELEASE_VERSION}.tar"
```

復旧時は`docker image load --input <tar>`で戻せます。ソース、DBバックアップ、Orbbec SDKの利用条件も
別途維持します。コンテナはホストのLinux kernelを使うため、将来別CPUアーキテクチャへ移す場合は
Orbbec SDKを含む対応可否を事前に確認します。
