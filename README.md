# Rance Wiki mirror

このリポジトリは、`rance-world-note` 配下の静的ミラーを Vercel に載せるための構成です。

## 追加した内容

- `middleware.mjs`
  `/rance-world-note/*` と `/assets/*` に BASIC 認証をかけ、Wiki の見た目URLを実ファイルへ内部リライトします。
- `vercel.json`
  Vercel を `Other` として扱い、`public/` を配信物として使うよう固定しています。
- `scripts/prepare_vercel_static.mjs`
  デプロイ前に `rance-world-note/` を `public/rance-world-note/` へコピーします。
- `vercel-routes.json`
  Vercel 用のルート表です。`scripts/build_rance_mirror.py` を再実行すると更新されます。

## 必要な環境変数

`.env.example` を参考に、Vercel 側で次の2つを設定してください。

- `BASIC_AUTH_USERNAME`
- `BASIC_AUTH_PASSWORD`

## Vercel への投入

1. `npm install`
2. Vercel プロジェクトをこのリポジトリに接続
3. 環境変数 `BASIC_AUTH_USERNAME` と `BASIC_AUTH_PASSWORD` を Preview / Production に設定
4. デプロイ

`vercel.json` で `framework: "other"`、`buildCommand: "npm run build"`、`outputDirectory: "public"` を固定しているので、追加設定は基本不要です。

## ローカル確認

- ミラーの中身確認: `python scripts/serve_rance_mirror.py`
- Vercel 相当の確認: `npx vercel@latest dev`
