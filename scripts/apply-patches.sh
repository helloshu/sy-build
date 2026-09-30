#!/usr/bin/env bash
# 稳健地将 unlock 补丁应用到思源源码树，缓解上游发版导致的补丁上下文漂移。
#
# 用法: apply-patches.sh <siyuan 源码目录> [补丁目录]
#   补丁目录默认为本脚本 ../patches/siyuan，目录内所有 *.patch 按文件名顺序应用。
#   按精确标签、默认补丁、其他版本覆盖的顺序寻找兼容补丁，不要求为每个上游版本建立目录。
#
# 每个补丁的应用策略:
#   所有 git apply 调用都使用 --recount，根据补丁正文重算 hunk 行数，避免过时的行数头静默遗漏尾部变更。
#   1. 先对所有候选反向校验，避免重复应用其他版本的等价补丁
#   2. 严格匹配所有候选: git apply --ignore-whitespace（完整上下文校验）
#   3. 宽松匹配所有候选: git apply --ignore-whitespace -C1（上游在补丁上下文处有漂移时,
#      仍要求至少 1 行上下文 + 被修改行本身完全一致, 不会盲目套用）
#   4. 失败: 打印详细诊断并以非零退出——说明补丁的目标代码行本身被上游修改,
#      需要人工更新补丁。
#
# 注意: 不要放宽到 -C0/--unidiff-zero。纯插入型 hunk 没有删除行可锚定,
# -C0 会把代码插到错误的顶层位置（实验验证会产生无法编译的代码）。

set -euo pipefail

TARGET="${1:?用法: apply-patches.sh <siyuan源码目录> [补丁目录]}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_DIR="${2:-$SCRIPT_DIR/../patches/siyuan}"

if [ ! -d "$PATCH_DIR" ]; then
  echo "[patches] ERROR: 补丁目录不存在: $PATCH_DIR" >&2
  exit 1
fi

PATCH_DIR="$(cd "$PATCH_DIR" && pwd)"

cd "$TARGET" || { echo "[patches] ERROR: 无法进入源码目录: $TARGET" >&2; exit 1; }

shopt -s nullglob
patches=("$PATCH_DIR"/*.patch)
if [ ${#patches[@]} -eq 0 ]; then
  echo "[patches] ERROR: $PATCH_DIR 中没有补丁文件" >&2
  exit 1
fi

upstream_tag="$(git describe --tags --exact-match HEAD 2>/dev/null || true)"
if [ -n "$upstream_tag" ] && [ -d "$PATCH_DIR/versions/$upstream_tag" ]; then
  echo "[patches] 检测到上游标签 ${upstream_tag}，使用对应的版本覆盖补丁"
fi

applied=0
skipped=0
for p in "${patches[@]}"; do
  name="$(basename "$p")"
  candidates=()
  exact="$PATCH_DIR/versions/$upstream_tag/$name"
  if [ -n "$upstream_tag" ] && [ -f "$exact" ]; then
    candidates+=("$exact")
  fi
  candidates+=("$p")
  for candidate in "$PATCH_DIR"/versions/*/"$name"; do
    if [ "$candidate" != "$exact" ]; then
      candidates+=("$candidate")
    fi
  done

  # 先检查所有候选的已应用状态，再考虑任何正向变更。
  matched=false
  for candidate in "${candidates[@]}"; do
    if git apply --recount --ignore-whitespace --check --reverse "$candidate" 2>/dev/null \
      || git apply --recount --ignore-whitespace -C1 --check --reverse "$candidate" 2>/dev/null; then
      echo "[patches] $name 已应用过, 跳过 (${candidate#"$PATCH_DIR/"})"
      skipped=$((skipped + 1))
      matched=true
      break
    fi
  done
  if [ "$matched" = true ]; then
    continue
  fi

  # 完整上下文匹配优先于所有候选的宽松匹配；不使用 -C0。
  for mode in strict relaxed; do
    context=(--ignore-whitespace)
    if [ "$mode" = relaxed ]; then
      context+=( -C1 )
    fi
    for candidate in "${candidates[@]}"; do
      if git apply --recount "${context[@]}" --check "$candidate" 2>/dev/null; then
        git apply --recount "${context[@]}" "$candidate"
        echo "[patches] $name 已应用 ($mode, ${candidate#"$PATCH_DIR/"})"
        applied=$((applied + 1))
        matched=true
        break
      fi
    done
    if [ "$matched" = true ]; then
      break
    fi
  done
  if [ "$matched" = false ]; then
    echo "[patches] ERROR: $name 的所有候选均不兼容上游 ${upstream_tag:-HEAD}" >&2
    for candidate in "${candidates[@]}"; do
      echo "  候选: ${candidate#"$PATCH_DIR/"}" >&2
      git apply --recount --ignore-whitespace --check "$candidate" 2>&1 | sed 's/^/    /' >&2 || true
    done
    echo "[patches] 构建终止：需要更新该补丁，后续依赖补丁未执行" >&2
    exit 1
  fi
done

# macOS Bash 3.2 可能把紧邻变量的非 ASCII 字节计入变量名，显式限定变量边界。
echo "[patches] 完成: 新应用 ${applied}，已应用 ${skipped}，共 ${#patches[@]} 个补丁"
