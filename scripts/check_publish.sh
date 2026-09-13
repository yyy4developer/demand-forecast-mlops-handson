#!/usr/bin/env bash
# =============================================================================
# 公開前チェック（汎用）
# =============================================================================
# 公開リポジトリに入ってはいけない一般的なものを検出する。
#
#   1. 認証情報               — トークン・API キー
#   2. 環境固有の識別子       — ワークスペース URL・アクセストークン風の文字列
#   3. ノートブックの実行出力 — 実データが残っている可能性がある
#   4. サンプルデータの再現性 — 生成物が仕様と一致しているか
#
# ⚠️ 案件固有の語句（組織名・個人名・実在する製品型番など）の検査は、
#    その語句自体をこのファイルに書くと公開時に漏れてしまうため、ここには含めない。
#    リポジトリ外の非公開スクリプトで別途チェックすること。
#
# 使い方:  bash scripts/check_publish.sh
# 終了コード: 0 = 問題なし / 1 = 検出あり
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

FAIL=0
EXCLUDES=(--exclude-dir=.git --exclude-dir=.venv --exclude-dir=.uv --exclude-dir=node_modules)

check() {
  local label="$1" pattern="$2"
  local hits count
  hits=$(grep -rInE "${EXCLUDES[@]}" -- "$pattern" . 2>/dev/null | grep -v '^./scripts/check_publish.sh:' || true)
  count=$(printf '%s' "$hits" | grep -c . || true)
  if [ "$count" -gt 0 ]; then
    printf '❌ %-30s %s 件\n' "$label" "$count"
    printf '%s\n' "$hits" | head -20 | sed 's/^/     /'
    FAIL=1
  else
    printf '✅ %-30s 0 件\n' "$label"
  fi
}

echo "=================================================="
echo "  公開前チェック（汎用）"
echo "=================================================="

check "認証情報" '(dapi|sk-|ghp_|github_pat_|xoxb-|xoxp-|AKIA|ASIA)[A-Za-z0-9_]{20,}'
check "ワークスペース URL" '(adb-[0-9]{10,}|dbc-[0-9a-f]{8})[.-]'
check "ノートブックの実行出力" '"output_type":\s*"(execute_result|display_data|stream)"'

# サンプルデータが仕様から再現できるか
printf '\n[サンプルデータの再現性]\n'
if command -v uv >/dev/null 2>&1; then
  if uv run src/setup/generate_sample_data.py >/dev/null 2>&1; then
    if git diff --quiet -- data/ 2>/dev/null; then
      printf '✅ %-30s 差分なし\n' "再生成しても同一"
    else
      printf '❌ %-30s 差分あり（git diff data/ を確認）\n' "再生成すると差分が出る"
      FAIL=1
    fi
  else
    printf '⚠️  %-30s 生成スクリプトが失敗\n' "再現性チェック"
    FAIL=1
  fi
else
  printf '⏭  %-30s uv が無いためスキップ\n' "再現性チェック"
fi

echo "=================================================="
if [ "$FAIL" -eq 0 ]; then
  echo "  ✅ 汎用チェックは通りました"
  echo "  ⚠️ 案件固有の語句チェックは別途（非公開スクリプト）で実施すること"
else
  echo "  ❌ 検出されました。公開前に修正してください"
fi
echo "=================================================="
exit "$FAIL"
