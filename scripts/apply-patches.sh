#!/usr/bin/env bash
# 稳健地将 unlock 补丁应用到思源源码树，缓解上游发版导致的补丁上下文漂移。
#
# 用法: apply-patches.sh <siyuan 源码目录> [补丁目录]
#   补丁目录默认为本脚本 ../patches/siyuan，目录内所有 *.patch 按文件名顺序应用。
#
# 每个补丁的应用策略:
#   1. 严格匹配: git apply --ignore-whitespace（完整上下文校验）
#   2. 宽松匹配: git apply --ignore-whitespace -C1（上游在补丁上下文处有漂移时,
#      仍要求至少 1 行上下文 + 被修改行本身完全一致, 不会盲目套用）
#   3. 幂等跳过: 反向校验发现补丁已应用
#   4. 失败: 打印详细诊断并以非零退出——说明补丁的目标代码行本身被上游修改,
#      需要人工更新补丁。
#
# 注意: 不要放宽到 -C0/--unidiff-zero。纯插入型 hunk 没有删除行可锚定,
# -C0 会把代码插到错误的顶层位置（实验验证会产生无法编译的代码）。

set -uo pipefail

TARGET="${1:?用法: apply-patches.sh <siyuan源码目录> [补丁目录]}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_DIR="${2:-$SCRIPT_DIR/../patches/siyuan}"

if [ ! -d "$PATCH_DIR" ]; then
  echo "[patches] ERROR: 补丁目录不存在: $PATCH_DIR" >&2
  exit 1
fi

cd "$TARGET" || { echo "[patches] ERROR: 无法进入源码目录: $TARGET" >&2; exit 1; }

shopt -s nullglob
patches=("$PATCH_DIR"/*.patch)
if [ ${#patches[@]} -eq 0 ]; then
  echo "[patches] ERROR: $PATCH_DIR 中没有补丁文件" >&2
  exit 1
fi

fail=0
applied=0
for p in "${patches[@]}"; do
  name="$(basename "$p")"
  if git apply --ignore-whitespace "$p" 2>/dev/null; then
    echo "[patches] $name 已应用 (严格匹配)"
    applied=$((applied + 1))
  elif git apply --ignore-whitespace -C1 "$p" 2>/dev/null; then
    echo "[patches] $name 已应用 (宽松匹配: 上游代码在补丁上下文处有漂移)"
    applied=$((applied + 1))
  elif git apply --ignore-whitespace --check --reverse "$p" 2>/dev/null \
    || git apply --ignore-whitespace -C1 --check --reverse "$p" 2>/dev/null; then
    echo "[patches] $name 已应用过, 跳过"
  else
    echo "[patches] ERROR: $name 无法应用" >&2
    echo "  补丁的目标代码行已被上游修改, 需要人工更新补丁后重试:" >&2
    git apply --ignore-whitespace "$p" 2>&1 | sed 's/^/    /' >&2
    fail=1
  fi
done

echo "[patches] 完成: $applied/${#patches[@]} 个补丁生效"
if [ $fail -ne 0 ]; then
  echo "[patches] 存在无法应用的补丁, 构建终止" >&2
  exit 1
fi
