---
description: How to deploy to Cloud Run using WSL
---

# WSLでのデプロイ手順

WSL (Windows Subsystem for Linux) 上で `deploy_cloudrun.sh` を実行するための手順です。

## 1. WSLを開き、プロジェクトディレクトリに移動する

Windowsのファイルシステムは `/mnt/c/` 配下にマウントされています。

```bash
# 例: ユーザー名はご自身の環境に合わせてください
cd /mnt/c/Users/keisu/workspace/shadow-director
```

## 2. Windowsの改行コード(CRLF)を修正する

Windowsで作成されたシェルスクリプトは、改行コードが原因でWSL上でエラーになることがあります。以下のコマンドで修正します。

```bash
# 初回のみ実施（またはスクリプトをWindows側で編集するたびに実施）
sed -i 's/\r$//' deploy_cloudrun.sh
chmod +x deploy_cloudrun.sh
```

## 3. Google Cloud SDKの確認

WSL環境内に `gcloud` コマンドがインストールされているか確認してください。Windows側の `gcloud` とは別物です。

```bash
gcloud --version
```

**インストールされていない場合:**
[Google Cloud SDK のインストール手順](https://cloud.google.com/sdk/docs/install?hl=ja#deb) に従ってインストールしてください。

```bash
# 簡易インストール
sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates gnupg
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
sudo apt-get update && sudo apt-get install -y google-cloud-cli
```

## 4. 認証とプロジェクト設定

WSL内で認証を行います。

```bash
gcloud auth login
gcloud config set project zenn-shadow-director
```

## 5. デプロイスクリプトの実行

```bash
./deploy_cloudrun.sh
```
